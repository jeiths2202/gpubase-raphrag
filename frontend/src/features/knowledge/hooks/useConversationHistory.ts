/**
 * useConversationHistory Hook
 *
 * Manages conversation history state and operations with workspace store integration.
 *
 * Features:
 * - Load recent conversations from workspaceStore (max 30)
 * - Create new conversation with auto-generated title
 * - Switch active conversation and load messages
 * - Manage loading states during async operations
 * - Provide extension points for future filtering/search
 *
 * Business Rules:
 * - Conversations sorted by updated_at DESC (most recent first)
 * - Max 30 conversations displayed (configurable constant)
 * - Active conversation highlighted in list
 * - Auto-select newest conversation on first load if none active
 *
 * Future Extensions:
 * - deleteConversation: Soft delete with trash bin
 * - archiveConversation: Move to archive view
 * - searchConversations: Filter by title or content
 */

import { useState, useEffect, useCallback } from 'react';
import { useWorkspaceStore } from '../../../store/workspaceStore';

interface Conversation {
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

interface UseConversationHistoryOptions {
  /** Maximum number of conversations to display */
  maxConversations?: number;
  /** Auto-select first conversation on mount if none active */
  autoSelectFirst?: boolean;
}

interface UseConversationHistoryReturn {
  /** Array of recent conversations (sorted by updated_at DESC) */
  conversations: Conversation[];
  /** Currently active conversation ID */
  activeConversationId: string | null;
  /** Loading state for conversation list fetch */
  isLoading: boolean;
  /** Loading state for conversation creation */
  isCreating: boolean;
  /** Create new conversation with optional title */
  createNewConversation: (title?: string) => Promise<Conversation | null>;
  /** Select conversation and load its messages */
  selectConversation: (id: string) => Promise<void>;
  /** Reload conversation list from backend */
  refreshConversations: () => Promise<void>;
  /** Delete conversation (future implementation) */
  deleteConversation?: (id: string) => Promise<void>;
  /** Archive conversation (future implementation) */
  archiveConversation?: (id: string) => Promise<void>;
  /** Search conversations by query (future implementation) */
  searchConversations?: (query: string) => void;
}

const MAX_CONVERSATIONS = 30;

export function useConversationHistory({
  maxConversations = MAX_CONVERSATIONS,
  autoSelectFirst = true
}: UseConversationHistoryOptions = {}): UseConversationHistoryReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [isCreating, setIsCreating] = useState(false);

  // Access workspace store
  const workspaceStore = useWorkspaceStore();
  const conversations = workspaceStore.recentConversations.slice(0, maxConversations);
  const activeConversationId = workspaceStore.menuStates.chat?.activeConversationId || null;

  /**
   * Load conversations from backend
   */
  const refreshConversations = useCallback(async () => {
    setIsLoading(true);
    try {
      await workspaceStore.loadRecentConversations();
      console.log(`✅ Loaded ${conversations.length} conversations`);
    } catch (error) {
      console.error('❌ Failed to load conversations:', error);
      // TODO: Show toast notification with retry action
    } finally {
      setIsLoading(false);
    }
  }, [workspaceStore]);

  /**
   * Create new conversation with auto-generated title
   */
  const createNewConversation = useCallback(async (title?: string): Promise<Conversation | null> => {
    setIsCreating(true);
    try {
      // Generate title with timestamp if not provided
      const conversationTitle = title || `New Conversation ${new Date().toLocaleString()}`;

      console.log(`🔨 Creating conversation: "${conversationTitle}"`);
      const newConversation = await workspaceStore.createConversation(conversationTitle);

      console.log(`✅ Conversation created with ID: ${newConversation.id}`);

      // Auto-select newly created conversation
      await workspaceStore.setActiveConversation(newConversation.id);

      return newConversation;
    } catch (error) {
      console.error('❌ Failed to create conversation:', error);
      // TODO: Show toast notification with error message
      return null;
    } finally {
      setIsCreating(false);
    }
  }, [workspaceStore]);

  /**
   * Select conversation and load its messages
   */
  const selectConversation = useCallback(async (id: string) => {
    if (id === activeConversationId) {
      console.log(`ℹ️ Conversation ${id} is already active`);
      return;
    }

    try {
      console.log(`🔄 Switching to conversation: ${id}`);
      await workspaceStore.setActiveConversation(id);
      console.log(`✅ Switched to conversation: ${id}`);
    } catch (error) {
      console.error(`❌ Failed to switch conversation: ${id}`, error);
      // TODO: Show toast notification with error message
    }
  }, [activeConversationId, workspaceStore]);

  /**
   * Delete conversation
   */
  const deleteConversation = useCallback(async (id: string) => {
    try {
      console.log(`🗑️ Deleting conversation: ${id}`);
      await workspaceStore.deleteConversation(id);
      console.log(`✅ Conversation deleted: ${id}`);
    } catch (error) {
      console.error(`❌ Failed to delete conversation: ${id}`, error);
      throw error; // Re-throw to allow UI to handle error
    }
  }, [workspaceStore]);

  /**
   * Initialize: Load conversations on mount
   */
  useEffect(() => {
    const initialize = async () => {
      await refreshConversations();

      // Auto-select first conversation if none active
      // Must get fresh conversations from store AFTER refreshConversations completes
      const freshConversations = workspaceStore.recentConversations.slice(0, maxConversations);

      if (autoSelectFirst && !activeConversationId && freshConversations.length > 0) {
        const firstConversation = freshConversations[0];
        console.log(`ℹ️ Auto-selecting first conversation: ${firstConversation.id}`);
        await selectConversation(firstConversation.id);
      }
    };

    initialize();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount - refreshConversations, workspaceStore are stable

  return {
    conversations,
    activeConversationId,
    isLoading,
    isCreating,
    createNewConversation,
    selectConversation,
    refreshConversations,
    deleteConversation
    // Future extensions:
    // archiveConversation,
    // searchConversations
  };
}
