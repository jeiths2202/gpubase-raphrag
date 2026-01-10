/**
 * ConversationSidebar Component
 *
 * Displays conversation history for the current agent type.
 * Features:
 * - New conversation button
 * - Conversation list with selection
 * - Delete functionality
 * - Auto-load on agent type change
 */

import { useEffect, useState, useCallback } from 'react';
import {
  Plus,
  MessageSquare,
  Trash2,
  ChevronLeft,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import { useConversationStore } from '../store/conversationStore';
import type { AgentType } from '../api/agent.api';
import type { ConversationListItem } from '../api/conversation.api';
import './ConversationSidebar.css';

// =============================================================================
// Types
// =============================================================================

interface ConversationSidebarProps {
  agentType: AgentType;
  isOpen: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Format relative time
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

/**
 * Get agent type display name
 */
function getAgentDisplayName(agentType: AgentType): string {
  const names: Record<AgentType, string> = {
    auto: 'Auto',
    rag: 'RAG',
    ims: 'IMS',
    vision: 'Vision',
    code: 'Code',
    planner: 'Planner',
  };
  return names[agentType];
}

// =============================================================================
// Component
// =============================================================================

export function ConversationSidebar({
  agentType,
  isOpen,
  onToggle,
  onNewConversation,
  onSelectConversation,
}: ConversationSidebarProps) {
  // Use explicit selectors to ensure re-render on state changes
  const loadConversations = useConversationStore((state) => state.loadConversations);
  const deleteConversation = useConversationStore((state) => state.deleteConversation);
  const isDeleting = useConversationStore((state) => state.isDeleting);

  // Get ALL agent states and derive the current agent's state
  // This ensures proper re-rendering when any agent state changes
  const agentStates = useConversationStore((state) => state.agentStates);
  const agentState = agentStates[agentType];

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const conversations = agentState?.conversations || [];
  const activeConversationId = agentState?.activeConversationId || null;
  const isLoading = agentState?.isLoading || false;
  const error = agentState?.error || null;

  // Debug logging
  console.log('[ConversationSidebar] agentType:', agentType, 'conversations:', conversations.length, 'agentState:', agentState);

  // Load conversations when agent type changes
  useEffect(() => {
    console.log('[ConversationSidebar] Loading conversations for:', agentType);
    loadConversations(agentType);
  }, [agentType, loadConversations]);

  // Handle delete
  const handleDelete = useCallback(
    async (e: React.MouseEvent, conversationId: string) => {
      e.stopPropagation();
      if (isDeleting) return;

      if (window.confirm('Delete this conversation?')) {
        setDeletingId(conversationId);
        try {
          await deleteConversation(agentType, conversationId);
        } catch (error) {
          console.error('Failed to delete conversation:', error);
        } finally {
          setDeletingId(null);
        }
      }
    },
    [agentType, deleteConversation, isDeleting]
  );

  // Render conversation item
  const renderConversationItem = (conversation: ConversationListItem) => {
    const isActive = conversation.id === activeConversationId;
    const isDeleting = deletingId === conversation.id;
    const title = conversation.title || 'Untitled Conversation';
    const preview = conversation.first_message_preview || '';

    return (
      <div
        key={conversation.id}
        className={`conversation-item ${isActive ? 'active' : ''} ${isDeleting ? 'deleting' : ''}`}
        onClick={() => onSelectConversation(conversation.id)}
      >
        <div className="conversation-item-icon">
          <MessageSquare size={16} />
        </div>
        <div className="conversation-item-content">
          <div className="conversation-item-title">{title}</div>
          {preview && (
            <div className="conversation-item-preview">{preview}</div>
          )}
          <div className="conversation-item-meta">
            <span className="conversation-item-count">
              {conversation.message_count} messages
            </span>
            <span className="conversation-item-time">
              {formatRelativeTime(conversation.updated_at)}
            </span>
          </div>
        </div>
        <button
          className="conversation-item-delete"
          onClick={(e) => handleDelete(e, conversation.id)}
          disabled={isDeleting}
          title="Delete conversation"
        >
          {isDeleting ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
        </button>
      </div>
    );
  };

  return (
    <>
      {/* Sidebar */}
      <div className={`conversation-sidebar ${isOpen ? 'open' : 'closed'}`}>
        {/* Header */}
        <div className="conversation-sidebar-header">
          <div className="conversation-sidebar-title">
            <span>{getAgentDisplayName(agentType)} Conversations</span>
          </div>
          <button
            className="conversation-sidebar-collapse"
            onClick={onToggle}
            title="Collapse sidebar"
          >
            <ChevronLeft size={18} />
          </button>
        </div>

        {/* New Conversation Button */}
        <button className="new-conversation-btn" onClick={onNewConversation}>
          <Plus size={18} />
          <span>New Conversation</span>
        </button>

        {/* Conversation List */}
        <div className="conversation-list">
          {isLoading && conversations.length === 0 ? (
            <div className="conversation-list-loading">
              <Loader2 size={24} className="spin" />
              <span>Loading...</span>
            </div>
          ) : error ? (
            <div className="conversation-list-error">
              <AlertCircle size={20} />
              <span>{error}</span>
            </div>
          ) : conversations.length === 0 ? (
            <div className="conversation-list-empty">
              <MessageSquare size={32} />
              <span>No conversations yet</span>
              <span className="conversation-list-empty-hint">
                Start a new conversation to begin
              </span>
            </div>
          ) : (
            conversations.map(renderConversationItem)
          )}
        </div>
      </div>
    </>
  );
}

export default ConversationSidebar;
