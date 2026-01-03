/**
 * ConversationList Component
 *
 * Scrollable list of conversations with metadata display and active highlighting.
 *
 * Responsibilities:
 * - Render list of ConversationListItem components
 * - Conversation item click handler
 * - Hover states with action buttons (future: delete icon)
 * - Loading skeleton during API fetch
 * - Empty state when no conversations
 * - Keyboard navigation support (arrow keys)
 *
 * Performance:
 * - Simple list rendering for ≤30 conversations (no virtualization needed)
 * - React.memo optimization on list items to prevent re-renders
 * - Future: If >100 conversations, integrate react-window for virtualization
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ConversationListItem } from './ConversationListItem';
import type { ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import './ConversationList.css';

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

interface ConversationListProps {
  /** Array of conversations to display */
  conversations: Conversation[];
  /** Currently active conversation ID */
  activeConversationId: string | null;
  /** Click handler for conversation selection */
  onSelectConversation: (conversationId: string) => void;
  /** Loading state during conversation fetch */
  isLoading: boolean;
  /** Theme colors for styling (deprecated - uses CSS variables) */
  themeColors?: ThemeColors;
  /** Translation function */
  t: TranslateFunction;
  /** Show action buttons on hover (delete, archive - future) */
  showActions?: boolean;
  /** Delete handler for conversation deletion */
  onDeleteConversation?: (conversationId: string) => void;
}

/**
 * Loading Skeleton Component
 */
const LoadingSkeleton: React.FC<{ themeColors?: ThemeColors }> = () => (
  <div className="conversation-loading-skeleton">
    {[1, 2, 3, 4, 5].map((i) => (
      <div key={i} className="conversation-skeleton-item" />
    ))}
  </div>
);

/**
 * Empty State Component
 */
const EmptyState: React.FC<{ themeColors?: ThemeColors; t: TranslateFunction }> = ({ t }) => (
  <div className="conversation-empty-state">
    <div className="conversation-empty-icon">💬</div>
    <p className="conversation-empty-text">
      {t('knowledge.chat.history.empty')}
    </p>
    <p className="conversation-empty-hint">
      {t('knowledge.chat.history.emptyHint')}
    </p>
  </div>
);

export const ConversationList: React.FC<ConversationListProps> = ({
  conversations,
  activeConversationId,
  onSelectConversation,
  isLoading,
  themeColors,
  t,
  showActions = false,
  onDeleteConversation
}) => {
  // Loading State
  if (isLoading) {
    return <LoadingSkeleton themeColors={themeColors} />;
  }

  // Empty State
  if (conversations.length === 0) {
    return <EmptyState themeColors={themeColors} t={t} />;
  }

  // Conversation List
  return (
    <div
      role="list"
      aria-label={t('knowledge.chat.history.title')}
      className="conversation-list"
    >
      <AnimatePresence>
        {conversations.map((conversation, index) => (
          <motion.div
            key={conversation.id}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ delay: index * 0.05 }}
          >
            <ConversationListItem
              conversation={conversation}
              isActive={conversation.id === activeConversationId}
              onClick={() => onSelectConversation(conversation.id)}
              themeColors={themeColors}
              t={t}
              showActions={showActions}
              onDelete={onDeleteConversation}
            />
          </motion.div>
        ))}
      </AnimatePresence>

      {/* Conversation Count Indicator */}
      {conversations.length > 0 && (
        <div className="conversation-count-indicator">
          {t('knowledge.chat.history.conversationCount', { count: conversations.length })}
        </div>
      )}
    </div>
  );
};
