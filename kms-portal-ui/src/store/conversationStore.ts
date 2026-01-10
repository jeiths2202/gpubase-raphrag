/**
 * Conversation Store
 *
 * Manages conversation state for the AI Agent chat.
 * Features:
 * - Per-agent-type conversation lists
 * - Active conversation tracking
 * - Auto-save on message addition
 * - Message history management
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { AgentType } from '../api/agent.api';
import {
  conversationApi,
  type ConversationListItem,
  type ConversationDetail,
  type ConversationMessage,
} from '../api/conversation.api';

// =============================================================================
// Types
// =============================================================================

/**
 * Local message for UI (may not be persisted yet)
 */
export interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isPersisted: boolean;
}

/**
 * Conversation state per agent type
 */
interface AgentConversationState {
  conversations: ConversationListItem[];
  activeConversationId: string | null;
  isLoading: boolean;
  error: string | null;
}

/**
 * Store state
 */
interface ConversationState {
  // State per agent type
  agentStates: Record<AgentType, AgentConversationState>;

  // Current conversation detail (cached)
  currentConversation: ConversationDetail | null;

  // Local messages (for current session before persistence)
  localMessages: LocalMessage[];

  // Global loading state
  isCreating: boolean;
  isDeleting: boolean;

  // Actions - Conversations
  loadConversations: (agentType: AgentType) => Promise<void>;
  createConversation: (agentType: AgentType, title?: string) => Promise<ConversationDetail>;
  selectConversation: (agentType: AgentType, conversationId: string) => Promise<void>;
  deleteConversation: (agentType: AgentType, conversationId: string) => Promise<void>;
  updateConversationTitle: (conversationId: string, title: string) => Promise<void>;

  // Actions - Messages
  addLocalMessage: (message: Omit<LocalMessage, 'id' | 'timestamp' | 'isPersisted'>) => void;
  persistMessages: (conversationId: string) => Promise<void>;
  clearLocalMessages: () => void;

  // Actions - New Conversation
  startNewConversation: (agentType: AgentType) => void;

  // Getters
  getConversations: (agentType: AgentType) => ConversationListItem[];
  getActiveConversationId: (agentType: AgentType) => string | null;
  isLoading: (agentType: AgentType) => boolean;
}

// =============================================================================
// Initial State
// =============================================================================

const createInitialAgentState = (): AgentConversationState => ({
  conversations: [],
  activeConversationId: null,
  isLoading: false,
  error: null,
});

const initialAgentStates: Record<AgentType, AgentConversationState> = {
  auto: createInitialAgentState(),
  rag: createInitialAgentState(),
  ims: createInitialAgentState(),
  vision: createInitialAgentState(),
  code: createInitialAgentState(),
  planner: createInitialAgentState(),
};

// =============================================================================
// Store
// =============================================================================

export const useConversationStore = create<ConversationState>()(
  persist(
    (set, get) => ({
      // Initial state
      agentStates: initialAgentStates,
      currentConversation: null,
      localMessages: [],
      isCreating: false,
      isDeleting: false,

      // Load conversations for an agent type
      loadConversations: async (agentType: AgentType) => {
        set((state) => ({
          agentStates: {
            ...state.agentStates,
            [agentType]: {
              ...state.agentStates[agentType],
              isLoading: true,
              error: null,
            },
          },
        }));

        try {
          const { conversations } = await conversationApi.list({
            agent_type: agentType,
            limit: 50,
          });

          set((state) => ({
            agentStates: {
              ...state.agentStates,
              [agentType]: {
                ...state.agentStates[agentType],
                conversations,
                isLoading: false,
              },
            },
          }));
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to load conversations';
          set((state) => ({
            agentStates: {
              ...state.agentStates,
              [agentType]: {
                ...state.agentStates[agentType],
                isLoading: false,
                error: message,
              },
            },
          }));
        }
      },

      // Create a new conversation
      createConversation: async (agentType: AgentType, title?: string) => {
        set({ isCreating: true });

        try {
          const conversation = await conversationApi.create({
            agent_type: agentType,
            title: title || undefined,
          });

          set((state) => ({
            isCreating: false,
            currentConversation: conversation,
            localMessages: [],
            agentStates: {
              ...state.agentStates,
              [agentType]: {
                ...state.agentStates[agentType],
                conversations: [
                  {
                    id: conversation.id,
                    title: conversation.title,
                    message_count: conversation.message_count,
                    total_tokens: conversation.total_tokens,
                    is_archived: conversation.is_archived,
                    is_starred: conversation.is_starred,
                    strategy: conversation.strategy,
                    language: conversation.language,
                    agent_type: conversation.agent_type,
                    created_at: conversation.created_at,
                    updated_at: conversation.updated_at,
                  },
                  ...state.agentStates[agentType].conversations,
                ],
                activeConversationId: conversation.id,
              },
            },
          }));

          return conversation;
        } catch (error) {
          set({ isCreating: false });
          throw error;
        }
      },

      // Select a conversation
      selectConversation: async (agentType: AgentType, conversationId: string) => {
        set((state) => ({
          agentStates: {
            ...state.agentStates,
            [agentType]: {
              ...state.agentStates[agentType],
              activeConversationId: conversationId,
              isLoading: true,
            },
          },
        }));

        try {
          const conversation = await conversationApi.get(conversationId, true);

          set((state) => ({
            currentConversation: conversation,
            localMessages: [],
            agentStates: {
              ...state.agentStates,
              [agentType]: {
                ...state.agentStates[agentType],
                isLoading: false,
              },
            },
          }));
        } catch (error) {
          set((state) => ({
            agentStates: {
              ...state.agentStates,
              [agentType]: {
                ...state.agentStates[agentType],
                isLoading: false,
                error: error instanceof Error ? error.message : 'Failed to load conversation',
              },
            },
          }));
        }
      },

      // Delete a conversation
      deleteConversation: async (agentType: AgentType, conversationId: string) => {
        set({ isDeleting: true });

        try {
          await conversationApi.delete(conversationId, false);

          set((state) => {
            const conversations = state.agentStates[agentType].conversations.filter(
              (c) => c.id !== conversationId
            );
            const isActive = state.agentStates[agentType].activeConversationId === conversationId;

            return {
              isDeleting: false,
              currentConversation: isActive ? null : state.currentConversation,
              localMessages: isActive ? [] : state.localMessages,
              agentStates: {
                ...state.agentStates,
                [agentType]: {
                  ...state.agentStates[agentType],
                  conversations,
                  activeConversationId: isActive
                    ? conversations[0]?.id || null
                    : state.agentStates[agentType].activeConversationId,
                },
              },
            };
          });
        } catch (error) {
          set({ isDeleting: false });
          throw error;
        }
      },

      // Update conversation title
      updateConversationTitle: async (conversationId: string, title: string) => {
        try {
          await conversationApi.update(conversationId, { title });

          set((state) => {
            // Update in all agent states
            const newAgentStates = { ...state.agentStates };
            for (const agentType of Object.keys(newAgentStates) as AgentType[]) {
              newAgentStates[agentType] = {
                ...newAgentStates[agentType],
                conversations: newAgentStates[agentType].conversations.map((c) =>
                  c.id === conversationId ? { ...c, title } : c
                ),
              };
            }

            return {
              agentStates: newAgentStates,
              currentConversation:
                state.currentConversation?.id === conversationId
                  ? { ...state.currentConversation, title }
                  : state.currentConversation,
            };
          });
        } catch (error) {
          throw error;
        }
      },

      // Add a local message (not yet persisted)
      addLocalMessage: (message) => {
        const localMessage: LocalMessage = {
          id: `local_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          ...message,
          timestamp: new Date(),
          isPersisted: false,
        };

        set((state) => ({
          localMessages: [...state.localMessages, localMessage],
        }));
      },

      // Persist local messages to the server
      persistMessages: async (conversationId: string) => {
        const { localMessages } = get();
        const unpersisted = localMessages.filter((m) => !m.isPersisted);

        for (const message of unpersisted) {
          try {
            await conversationApi.addMessage(conversationId, {
              role: message.role,
              content: message.content,
            });

            set((state) => ({
              localMessages: state.localMessages.map((m) =>
                m.id === message.id ? { ...m, isPersisted: true } : m
              ),
            }));
          } catch (error) {
            console.error('Failed to persist message:', error);
          }
        }
      },

      // Clear local messages
      clearLocalMessages: () => {
        set({ localMessages: [] });
      },

      // Start a new conversation (clear current state)
      startNewConversation: (agentType: AgentType) => {
        set((state) => ({
          currentConversation: null,
          localMessages: [],
          agentStates: {
            ...state.agentStates,
            [agentType]: {
              ...state.agentStates[agentType],
              activeConversationId: null,
            },
          },
        }));
      },

      // Getters
      getConversations: (agentType: AgentType) => {
        return get().agentStates[agentType].conversations;
      },

      getActiveConversationId: (agentType: AgentType) => {
        return get().agentStates[agentType].activeConversationId;
      },

      isLoading: (agentType: AgentType) => {
        return get().agentStates[agentType].isLoading;
      },
    }),
    {
      name: 'conversation-storage',
      storage: createJSONStorage(() => localStorage),
      // Only persist active conversation IDs (not full conversations)
      partialize: (state) => ({
        agentStates: Object.fromEntries(
          Object.entries(state.agentStates).map(([key, value]) => [
            key,
            { activeConversationId: value.activeConversationId },
          ])
        ),
      }),
    }
  )
);

export default useConversationStore;
