/**
 * ConversationListItem Component
 *
 * Individual conversation item in the history sidebar with metadata display.
 *
 * Responsibilities:
 * - Render conversation metadata (title, message count, timestamp)
 * - Active conversation highlighting
 * - Hover states with action buttons (delete icon - future)
 * - Keyboard navigation support
 * - Click handler for conversation selection
 *
 * Display Format:
 * ┌─────────────────────────────┐
 * │ Conversation Title          │
 * │ 5 messages • 2 hours ago    │
 * └─────────────────────────────┘
 */

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import './ConversationListItem.css';

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

interface ConversationListItemProps {
  /** Conversation data to display */
  conversation: Conversation;
  /** Whether this conversation is currently active */
  isActive: boolean;
  /** Click handler for conversation selection */
  onClick: () => void;
  /** Theme colors for styling (deprecated - uses CSS variables) */
  themeColors?: ThemeColors;
  /** Translation function */
  t: TranslateFunction;
  /** Optional custom style override (deprecated - uses CSS classes) */
  style?: React.CSSProperties;
  /** Show action buttons on hover (delete, archive - future) */
  showActions?: boolean;
  /** Delete handler for conversation deletion */
  onDelete?: (conversationId: string) => void;
}

/**
 * Format relative timestamp (e.g., "2 hours ago", "Yesterday")
 */
function formatRelativeTime(timestamp: string | undefined, t: TranslateFunction): string {
  if (!timestamp) return t('knowledge.chat.history.noActivity');

  const now = new Date();
  const date = new Date(timestamp);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return t('knowledge.chat.history.justNow');
  if (diffMins < 60) return t('knowledge.chat.history.minutesAgo', { count: diffMins });
  if (diffHours < 24) return t('knowledge.chat.history.hoursAgo', { count: diffHours });
  if (diffDays === 1) return t('knowledge.chat.history.yesterday');
  if (diffDays < 7) return t('knowledge.chat.history.daysAgo', { count: diffDays });

  // Fall back to formatted date
  return date.toLocaleDateString();
}

export const ConversationListItem: React.FC<ConversationListItemProps> = ({
  conversation,
  isActive,
  onClick,
  themeColors,
  t,
  style,
  showActions = false,
  onDelete
}) => {
  const [isHovered, setIsHovered] = React.useState(false);
  const [isDeleting, setIsDeleting] = React.useState(false);

  const relativeTime = formatRelativeTime(conversation.updated_at, t);
  const messageCount = conversation.message_count || 0;

  // Generate title from first message preview if no title exists
  const displayTitle = conversation.title ||
    (conversation.first_message_preview
      ? conversation.first_message_preview.substring(0, 50) + (conversation.first_message_preview.length > 50 ? '...' : '')
      : t('knowledge.chat.newChat.button'));

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent conversation selection

    // Confirm deletion
    if (window.confirm(t('knowledge.chat.history.delete.confirmMessage'))) {
      setIsDeleting(true);
      try {
        if (onDelete) {
          await onDelete(conversation.id);
        }
      } catch (error) {
        console.error('Failed to delete conversation:', error);
        alert(t('knowledge.chat.history.delete.failed'));
      } finally {
        setIsDeleting(false);
      }
    }
  };

  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      role="button"
      tabIndex={0}
      aria-current={isActive ? 'true' : undefined}
      aria-label={`${displayTitle}, ${messageCount} ${messageCount === 1 ? t('knowledge.chat.history.message') : t('knowledge.chat.history.messages')}, ${relativeTime}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      className={`conversation-item ${isActive ? 'conversation-item-active' : ''}`}
      style={style}
    >
      {/* Conversation Title */}
      <div className="conversation-item-title">
        {displayTitle}
      </div>

      {/* Metadata: Message Count + Timestamp */}
      <div className="conversation-item-metadata">
        <span>
          {messageCount} {messageCount === 1
            ? t('knowledge.chat.history.message')
            : t('knowledge.chat.history.messages')}
        </span>
        <span>•</span>
        <span>{relativeTime}</span>
      </div>

      {/* Action Buttons (Delete) on Hover */}
      {showActions && isHovered && !isDeleting && onDelete && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="conversation-item-actions"
        >
          <button
            onClick={handleDelete}
            disabled={isDeleting}
            aria-label={t('knowledge.chat.history.delete.button')}
            title={t('knowledge.chat.history.delete.button')}
            className="conversation-delete-btn"
          >
            🗑️
          </button>
        </motion.div>
      )}

      {/* Deleting Indicator */}
      {isDeleting && (
        <div className="conversation-deleting-indicator">
          {t('knowledge.chat.history.delete.deleting')}
        </div>
      )}
    </motion.div>
  );
};
