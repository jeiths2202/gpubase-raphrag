/**
 * Workspace State Persistence Store
 *
 * Centralized state management for persistent AI workspace.
 * Handles automatic state persistence, restoration, and synchronization.
 *
 * Architecture Pattern: Zustand Store with Auto-Save
 * - Single source of truth for workspace state
 * - Automatic debounced persistence to backend
 * - Optimistic updates with error recovery
 * - Multi-menu state isolation
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';

// ============================================================================
// TYPES
// ============================================================================

export type MenuType =
  | 'chat'
  | 'documents'
  | 'web_sources'
  | 'notes'
  | 'ai_content'
  | 'projects'
  | 'mindmap'
  | 'knowledge_graph'
  | 'knowledge_base';

export type GraphType = 'mindmap' | 'knowledge_graph';

export interface WorkspacePreferences {
  theme: 'light' | 'dark' | 'auto';
  language: 'en' | 'ko' | 'ja';
  notifications: boolean;
  layout: 'comfortable' | 'compact';
  auto_save_interval: number; // milliseconds
}

export interface Conversation {
  id: string;
  title: string | null;
  message_count: number;
  total_tokens?: number;
  is_archived?: boolean;
  is_starred?: boolean;
  strategy?: string;
  language?: string;
  created_at: string;
  updated_at: string;
  first_message_preview?: string | null;
  last_message_preview?: string | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  token_count?: number;
  context_documents?: any[];
  retrieval_strategy?: string;
}

export interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  type: string;
  metadata?: Record<string, any>;
}

export interface GraphEdge {
  source: string;
  target: string;
  label?: string;
  weight?: number;
}

export interface GraphState {
  id: string;
  user_id: string;
  graph_type: GraphType;
  graph_name: string;
  state: {
    nodes: GraphNode[];
    edges: GraphEdge[];
    viewport: {
      zoom: number;
      center_x: number;
      center_y: number;
    };
    selected_nodes: string[];
    layout: 'force-directed' | 'hierarchical' | 'manual';
  };
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceSession {
  id: string;
  user_id: string;
  last_active_menu: MenuType;
  last_conversation_id: string | null;
  preferences: WorkspacePreferences;
  last_activity_at: string;
}

// Menu-specific state types
export interface ChatMenuState {
  activeConversationId: string | null;
  messages: Message[];
  isLoadingMessages: boolean;
  scrollPosition: number;
  filterSettings: {
    archived: boolean;
    dateRange: string;
  };
  viewMode: 'list' | 'grid';
}

export interface DocumentsMenuState {
  selectedDocuments: string[];
  filterSettings: {
    type: string;
    tags: string[];
    favorite: boolean;
  };
  sortBy: 'title' | 'date' | 'relevance';
  viewMode: 'list' | 'grid';
}

export interface MindmapMenuState {
  activeGraphId: string | null;
  viewportState: {
    zoom: number;
    centerX: number;
    centerY: number;
  };
  selectedNodes: string[];
  editMode: boolean;
}

// Union type for all menu states
export type MenuState =
  | ChatMenuState
  | DocumentsMenuState
  | MindmapMenuState
  | Record<string, any>; // Fallback for other menu types

// ============================================================================
// STORE STATE INTERFACE
// ============================================================================

interface WorkspaceState {
  // Loading states
  isLoading: boolean;
  isRestoring: boolean;
  lastSyncTime: Date | null;

  // Workspace session
  session: WorkspaceSession | null;
  activeMenu: MenuType;

  // Menu states (keyed by menu type)
  menuStates: Record<MenuType, MenuState>;

  // Graph states (keyed by graph type)
  graphStates: {
    mindmap: GraphState[];
    knowledge_graph: GraphState[];
  };

  // Recent conversations
  recentConversations: Conversation[];

  // Auto-save configuration
  autoSaveEnabled: boolean;
  autoSaveInterval: number; // milliseconds
  pendingSaves: Set<MenuType>; // Track menus with unsaved changes

  // ========================================================================
  // ACTIONS
  // ========================================================================

  // Initialize workspace (called on app mount/login)
  initializeWorkspace: () => Promise<void>;

  // Menu state management
  setMenuState: (menuType: MenuType, state: Partial<MenuState>) => void;
  getMenuState: (menuType: MenuType) => MenuState;
  saveMenuState: (menuType: MenuType) => Promise<void>;
  saveAllMenuStates: () => Promise<void>;

  // Graph state management
  saveGraphState: (
    graphType: GraphType,
    graphName: string,
    state: GraphState['state']
  ) => Promise<void>;
  loadGraphStates: (graphType: GraphType) => Promise<void>;

  // Session management
  setActiveMenu: (menuType: MenuType) => void;
  updatePreferences: (preferences: Partial<WorkspacePreferences>) => Promise<void>;
  updateSession: (updates: Partial<WorkspaceSession>) => Promise<void>;

  // Conversation management
  loadRecentConversations: () => Promise<void>;
  createConversation: (title?: string) => Promise<Conversation>;
  deleteConversation: (conversationId: string, hardDelete?: boolean) => Promise<boolean>;
  setActiveConversation: (conversationId: string) => void;

  // Message management
  loadConversationMessages: (conversationId: string) => Promise<void>;
  addMessageToConversation: (conversationId: string, role: 'user' | 'assistant' | 'system', content: string, metadata?: any) => Promise<Message>;
  clearMessagesCache: () => void;

  // Utility actions
  clearWorkspace: () => void;
  enableAutoSave: () => void;
  disableAutoSave: () => void;
}

// ============================================================================
// API CLIENT
// ============================================================================

const API_BASE = '/api/v1/workspace';

const workspaceApi = {
  // Load complete workspace state
  loadWorkspace: async (): Promise<any> => {
    const response = await fetch(`${API_BASE}/state/load`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to load workspace state');
    const result = await response.json();
    return result.data;
  },

  // Save menu state
  saveMenuState: async (menuType: MenuType, state: MenuState): Promise<void> => {
    const response = await fetch(`${API_BASE}/state/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ menu_type: menuType, state })
    });
    if (!response.ok) throw new Error(`Failed to save ${menuType} state`);
  },

  // Save graph state
  saveGraphState: async (
    graphType: GraphType,
    graphName: string,
    state: any
  ): Promise<void> => {
    const response = await fetch(`${API_BASE}/graph/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ graph_type: graphType, graph_name: graphName, state })
    });
    if (!response.ok) throw new Error('Failed to save graph state');
  },

  // Update workspace session
  updateSession: async (updates: Partial<WorkspaceSession>): Promise<void> => {
    const response = await fetch(`${API_BASE}/session`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(updates)
    });
    if (!response.ok) throw new Error('Failed to update session');
  },

  // Load recent conversations
  loadConversations: async (limit: number = 20): Promise<Conversation[]> => {
    const response = await fetch(`${API_BASE}/conversations/recent?limit=${limit}`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to load conversations');
    const result = await response.json();
    return result.data;
  },

  // Create conversation
  createConversation: async (title: string): Promise<Conversation> => {
    const response = await fetch(`${API_BASE}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ title })
    });
    if (!response.ok) throw new Error('Failed to create conversation');
    const result = await response.json();
    return result.data;
  },

  // Load messages for a conversation
  loadConversationMessages: async (conversationId: string): Promise<Message[]> => {
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/messages`, {
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to load messages');
    const result = await response.json();
    return result.data || [];
  },

  // Add message to conversation
  addMessage: async (conversationId: string, role: 'user' | 'assistant' | 'system', content: string, metadata?: any): Promise<Message> => {
    const response = await fetch(`${API_BASE}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        conversation_id: conversationId,
        role,
        content,
        ...metadata
      })
    });
    if (!response.ok) throw new Error('Failed to add message');
    const result = await response.json();
    return result.data;
  },

  // Delete conversation
  deleteConversation: async (conversationId: string, hardDelete: boolean = false): Promise<boolean> => {
    const response = await fetch(`/api/v1/conversations/${conversationId}?hard_delete=${hardDelete}`, {
      method: 'DELETE',
      credentials: 'include'
    });
    if (!response.ok) throw new Error('Failed to delete conversation');
    const result = await response.json();
    return result.data.deleted;
  }
};

// ============================================================================
// DEBOUNCE UTILITY
// ============================================================================

const debounceTimers: Record<string, ReturnType<typeof setTimeout>> = {};

function debounce(key: string, fn: () => void, delay: number) {
  if (debounceTimers[key]) {
    clearTimeout(debounceTimers[key]);
  }
  debounceTimers[key] = setTimeout(fn, delay);
}

// ============================================================================
// ZUSTAND STORE
// ============================================================================

export const useWorkspaceStore = create<WorkspaceState>()(
  devtools(
    (set, get) => ({
      // Initial state
      isLoading: false,
      isRestoring: false,
      lastSyncTime: null,
      session: null,
      activeMenu: 'chat',
      menuStates: {} as Record<MenuType, MenuState>,
      graphStates: {
        mindmap: [],
        knowledge_graph: []
      },
      recentConversations: [],
      autoSaveEnabled: true,
      autoSaveInterval: 5000, // 5 seconds
      pendingSaves: new Set(),

      // ======================================================================
      // INITIALIZE WORKSPACE (PRIMARY ENTRY POINT)
      // ======================================================================

      initializeWorkspace: async () => {
        set({ isRestoring: true, isLoading: true });

        try {
          console.log('🔄 Loading workspace state from backend...');

          const workspaceState = await workspaceApi.loadWorkspace();

          console.log('✅ Workspace state loaded:', workspaceState);

          // Restore menu states
          const menuStates: Record<MenuType, MenuState> = {} as Record<MenuType, MenuState>;
          Object.entries(workspaceState.menu_states || {}).forEach(
            ([menuType, state]) => {
              menuStates[menuType as MenuType] = state as MenuState;
            }
          );

          // Restore graph states
          const graphStates = {
            mindmap: workspaceState.graph_states?.mindmap || [],
            knowledge_graph: workspaceState.graph_states?.knowledge_graph || []
          };

          set({
            session: workspaceState.session,
            activeMenu: workspaceState.last_active_menu || 'chat',
            menuStates,
            graphStates,
            recentConversations: workspaceState.recent_conversations || [],
            isRestoring: false,
            isLoading: false,
            lastSyncTime: new Date()
          });

          console.log('✅ Workspace restored successfully');
        } catch (error) {
          console.error('❌ Failed to restore workspace:', error);
          set({ isRestoring: false, isLoading: false });
        }
      },

      // ======================================================================
      // MENU STATE MANAGEMENT
      // ======================================================================

      setMenuState: (menuType: MenuType, stateUpdates: Partial<MenuState>) => {
        set((state) => {
          const currentState = state.menuStates[menuType] || {};
          const newState = { ...currentState, ...stateUpdates };

          const newMenuStates = { ...state.menuStates, [menuType]: newState };
          const newPendingSaves = new Set(state.pendingSaves).add(menuType);

          // Auto-save with debounce
          if (state.autoSaveEnabled) {
            debounce(
              `menu-${menuType}`,
              () => get().saveMenuState(menuType),
              state.autoSaveInterval
            );
          }

          return {
            menuStates: newMenuStates,
            pendingSaves: newPendingSaves
          };
        });
      },

      getMenuState: (menuType: MenuType) => {
        return get().menuStates[menuType] || {};
      },

      saveMenuState: async (menuType: MenuType) => {
        const state = get().menuStates[menuType];
        if (!state) return;

        try {
          console.log(`💾 Saving ${menuType} state...`);
          await workspaceApi.saveMenuState(menuType, state);

          set((current) => {
            const newPendingSaves = new Set(current.pendingSaves);
            newPendingSaves.delete(menuType);
            return {
              pendingSaves: newPendingSaves,
              lastSyncTime: new Date()
            };
          });

          console.log(`✅ ${menuType} state saved`);
        } catch (error) {
          console.error(`❌ Failed to save ${menuType} state:`, error);
        }
      },

      saveAllMenuStates: async () => {
        const { menuStates } = get();
        const promises = Object.entries(menuStates).map(([menuType, state]) =>
          workspaceApi.saveMenuState(menuType as MenuType, state)
        );

        try {
          await Promise.all(promises);
          set({ pendingSaves: new Set(), lastSyncTime: new Date() });
          console.log('✅ All menu states saved');
        } catch (error) {
          console.error('❌ Failed to save all menu states:', error);
        }
      },

      // ======================================================================
      // GRAPH STATE MANAGEMENT
      // ======================================================================

      saveGraphState: async (
        graphType: GraphType,
        graphName: string,
        state: GraphState['state']
      ) => {
        try {
          console.log(`💾 Saving ${graphType} "${graphName}"...`);
          await workspaceApi.saveGraphState(graphType, graphName, state);
          console.log(`✅ ${graphType} "${graphName}" saved`);

          // Reload graph states to get updated metadata
          await get().loadGraphStates(graphType);
        } catch (error) {
          console.error(`❌ Failed to save ${graphType}:`, error);
        }
      },

      loadGraphStates: async (graphType: GraphType) => {
        // Implementation would call API to load graph states
        // For now, this is a placeholder
        console.log(`Loading ${graphType} states...`);
      },

      // ======================================================================
      // SESSION MANAGEMENT
      // ======================================================================

      setActiveMenu: (menuType: MenuType) => {
        set({ activeMenu: menuType });

        // Update session on backend
        workspaceApi.updateSession({ last_active_menu: menuType }).catch((error) => {
          console.error('Failed to update active menu:', error);
        });
      },

      updatePreferences: async (preferences: Partial<WorkspacePreferences>) => {
        const { session } = get();
        if (!session) return;

        const newPreferences = { ...session.preferences, ...preferences };
        const updatedSession = { ...session, preferences: newPreferences };

        set({ session: updatedSession });

        try {
          await workspaceApi.updateSession({ preferences: newPreferences });
          console.log('✅ Preferences updated');
        } catch (error) {
          console.error('❌ Failed to update preferences:', error);
        }
      },

      updateSession: async (updates: Partial<WorkspaceSession>) => {
        try {
          await workspaceApi.updateSession(updates);
          const { session } = get();
          if (session) {
            set({ session: { ...session, ...updates } });
          }
        } catch (error) {
          console.error('❌ Failed to update session:', error);
        }
      },

      // ======================================================================
      // CONVERSATION MANAGEMENT
      // ======================================================================

      loadRecentConversations: async () => {
        try {
          const MAX_CONVERSATIONS = parseInt(import.meta.env.VITE_MAX_CHAT_HISTORY || '30', 10);
          const conversations = await workspaceApi.loadConversations(MAX_CONVERSATIONS);
          set({ recentConversations: conversations.slice(0, MAX_CONVERSATIONS) });
        } catch (error) {
          console.error('❌ Failed to load conversations:', error);
        }
      },

      createConversation: async (title: string = 'New Conversation') => {
        try {
          const MAX_CONVERSATIONS = parseInt(import.meta.env.VITE_MAX_CHAT_HISTORY || '30', 10);
          console.log(`🔨 Creating conversation: "${title}"...`);
          const conversation = await workspaceApi.createConversation(title);
          console.log(`✅ Conversation created with ID: ${conversation.id}`);
          set((state) => ({
            recentConversations: [conversation, ...state.recentConversations].slice(0, MAX_CONVERSATIONS)
          }));
          return conversation;
        } catch (error) {
          console.error('❌ Failed to create conversation:', error);
          throw error;
        }
      },

      deleteConversation: async (conversationId: string, hardDelete: boolean = false) => {
        try {
          console.log(`🗑️ Deleting conversation: ${conversationId} (hard=${hardDelete})...`);
          const deleted = await workspaceApi.deleteConversation(conversationId, hardDelete);
          if (deleted) {
            console.log(`✅ Conversation deleted successfully`);
            // Remove from recent conversations list
            set((state) => ({
              recentConversations: state.recentConversations.filter(c => c.id !== conversationId)
            }));

            // If this was the active conversation, clear it
            const chatState = get().menuStates.chat as ChatMenuState | undefined;
            if (chatState?.activeConversationId === conversationId) {
              get().setMenuState('chat', {
                activeConversationId: null,
                messages: [],
                isLoadingMessages: false
              });
            }
          }
          return deleted;
        } catch (error) {
          console.error('❌ Failed to delete conversation:', error);
          throw error;
        }
      },

      setActiveConversation: (conversationId: string) => {
        // Update chat menu state with both activeConversationId and loading state
        // This prevents race condition between setMenuState calls
        get().setMenuState('chat', {
          activeConversationId: conversationId,
          isLoadingMessages: true,
          messages: [] // Clear previous messages immediately
        });

        // Update session
        workspaceApi
          .updateSession({ last_conversation_id: conversationId })
          .catch((error) => {
            console.error('Failed to update active conversation:', error);
          });

        // Load messages for this conversation
        get().loadConversationMessages(conversationId);
      },

      // ======================================================================
      // MESSAGE MANAGEMENT
      // ======================================================================

      loadConversationMessages: async (conversationId: string) => {
        // Set loading state
        get().setMenuState('chat', { isLoadingMessages: true });

        try {
          console.log(`🔄 Loading messages for conversation ${conversationId}...`);
          const messages = await workspaceApi.loadConversationMessages(conversationId);

          // Update chat state with loaded messages
          get().setMenuState('chat', {
            messages,
            isLoadingMessages: false
          });

          console.log(`✅ Loaded ${messages.length} messages`);
        } catch (error) {
          console.error('❌ Failed to load messages:', error);
          get().setMenuState('chat', {
            messages: [],
            isLoadingMessages: false
          });
          // Rethrow error so caller knows loading failed
          throw error;
        }
      },

      addMessageToConversation: async (
        conversationId: string,
        role: 'user' | 'assistant' | 'system',
        content: string,
        metadata?: any
      ) => {
        try {
          console.log(`💬 Adding message to conversation ${conversationId}: "${content.substring(0, 50)}..."`);

          // Optimistic update: add message to UI immediately
          const tempMessage: Message = {
            id: `temp-${Date.now()}`,
            conversation_id: conversationId,
            role,
            content,
            created_at: new Date().toISOString(),
            ...metadata
          };

          const chatState = get().menuStates['chat'] as ChatMenuState;
          const currentMessages = chatState?.messages || [];
          get().setMenuState('chat', {
            activeConversationId: conversationId,  // Save conversation ID for persistence
            messages: [...currentMessages, tempMessage]
          });

          // Persist to backend
          const savedMessage = await workspaceApi.addMessage(
            conversationId,
            role,
            content,
            metadata
          );

          // Replace temp message with real one
          const updatedMessages = currentMessages
            .filter((msg) => msg.id !== tempMessage.id)
            .concat(savedMessage);

          get().setMenuState('chat', {
            activeConversationId: conversationId,  // Ensure conversation ID persists
            messages: updatedMessages
          });

          console.log('✅ Message added and persisted');
          return savedMessage;
        } catch (error) {
          console.error('❌ Failed to add message:', error);
          // Remove optimistic message on error
          const chatState = get().menuStates['chat'] as ChatMenuState;
          const currentMessages = chatState?.messages || [];
          get().setMenuState('chat', {
            messages: currentMessages.filter((msg) => !msg.id.startsWith('temp-'))
          });
          throw error;
        }
      },

      clearMessagesCache: () => {
        get().setMenuState('chat', {
          messages: [],
          isLoadingMessages: false
        });
        console.log('✅ Messages cache cleared');
      },

      // ======================================================================
      // UTILITY ACTIONS
      // ======================================================================

      clearWorkspace: () => {
        set({
          session: null,
          activeMenu: 'chat',
          menuStates: {} as Record<MenuType, MenuState>,
          graphStates: { mindmap: [], knowledge_graph: [] },
          recentConversations: [],
          pendingSaves: new Set(),
          lastSyncTime: null
        });
      },

      enableAutoSave: () => {
        set({ autoSaveEnabled: true });
        console.log('✅ Auto-save enabled');
      },

      disableAutoSave: () => {
        set({ autoSaveEnabled: false });
        console.log('⏸️ Auto-save disabled');
      }
    }),
    { name: 'WorkspaceStore' }
  )
);

// ============================================================================
// CONVENIENCE HOOKS
// ============================================================================

/**
 * Hook to get menu state for a specific menu type
 */
export const useMenuState = <T extends MenuState = MenuState>(menuType: MenuType): T => {
  return useWorkspaceStore((state) => state.menuStates[menuType] as T) || ({} as T);
};

/**
 * Hook to set menu state for a specific menu type
 */
export const useSetMenuState = (menuType: MenuType) => {
  return useWorkspaceStore((state) => (updates: Partial<MenuState>) =>
    state.setMenuState(menuType, updates)
  );
};

/**
 * Hook to get active conversation ID
 */
export const useActiveConversation = (): string | null => {
  const chatState = useMenuState<ChatMenuState>('chat');
  return chatState.activeConversationId || null;
};

/**
 * Hook to get messages for active conversation
 */
export const useChatMessages = (): Message[] => {
  const chatState = useMenuState<ChatMenuState>('chat');
  return chatState.messages || [];
};

/**
 * Hook to get message loading state
 */
export const useMessagesLoading = (): boolean => {
  const chatState = useMenuState<ChatMenuState>('chat');
  return chatState.isLoadingMessages || false;
};
