/**
 * ConversationHistorySidebar Component
 *
 * Slide-in sidebar panel displaying conversation history with max 30 sessions.
 *
 * Responsibilities:
 * - Render slide-in panel (right side, 320px width on desktop)
 * - List of conversations with metadata (title, message count, timestamp)
 * - Active conversation highlighting
 * - Empty state with illustration + CTA
 * - Close button with keyboard shortcut (Escape)
 * - Responsive behavior (full-screen on mobile)
 *
 * Layout:
 * ┌──────────────────────────┐
 * │  Conversations      [✕]  │
 * ├──────────────────────────┤
 * │  [Search bar - future]   │
 * ├──────────────────────────┤
 * │  Conversation 1   ●      │
 * │  5 messages • 2h ago     │
 * ├──────────────────────────┤
 * │  Conversation 2          │
 * │  12 messages • 1d ago    │
 * └──────────────────────────┘
 */

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ConversationList } from './ConversationList';
import { useConversationHistory } from '../hooks/useConversationHistory';
import type { ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import './ConversationHistorySidebar.css';

interface ConversationHistorySidebarProps {
  /** Whether sidebar is open/visible */
  isOpen: boolean;
  /** Close handler */
  onClose: () => void;
  /** Theme colors for styling (deprecated - uses CSS variables) */
  themeColors?: ThemeColors;
  /** Translation function */
  t: TranslateFunction;
  /** Card styling object (deprecated - uses CSS classes) */
  cardStyle?: React.CSSProperties;
  /** Maximum conversations to display (default: 30) */
  maxConversations?: number;
}

export const ConversationHistorySidebar: React.FC<ConversationHistorySidebarProps> = ({
  isOpen,
  onClose,
  themeColors,
  t,
  cardStyle,
  maxConversations = 30
}) => {
  const {
    conversations,
    activeConversationId,
    isLoading,
    selectConversation,
    refreshConversations,
    deleteConversation
  } = useConversationHistory({ maxConversations, autoSelectFirst: false });

  /**
   * Handle Escape key to close sidebar
   */
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  /**
   * Prevent body scroll when sidebar is open
   */
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'auto';
    }

    return () => {
      document.body.style.overflow = 'auto';
    };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="conversation-sidebar-backdrop"
          />

          {/* Sidebar Panel */}
          <motion.div
            initial={{ opacity: 0, x: 320 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 320 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="conversation-sidebar-panel"
          >
            {/* Header */}
            <div className="conversation-sidebar-header">
              <h3 className="conversation-sidebar-title">
                {t('knowledge.chat.history.title')}
              </h3>

              {/* Close Button */}
              <button
                onClick={onClose}
                aria-label={t('knowledge.common.close')}
                className="conversation-sidebar-close-btn"
              >
                ✕
              </button>
            </div>

            {/* Future: Search Bar */}
            {/*
            <div style={{ padding: '12px 20px' }}>
              <ConversationSearchBar ... />
            </div>
            */}

            {/* Conversation List (Scrollable) */}
            <div className="conversation-list-scroll">
              <ConversationList
                conversations={conversations}
                activeConversationId={activeConversationId}
                onSelectConversation={async (id) => {
                  await selectConversation(id);
                  onClose(); // Close sidebar after selection (mobile UX)
                }}
                isLoading={isLoading}
                themeColors={themeColors}
                t={t}
                showActions={true}
                onDeleteConversation={deleteConversation}
              />
            </div>

            {/* Footer: Refresh Button */}
            <div className="conversation-sidebar-footer">
              <button
                onClick={refreshConversations}
                disabled={isLoading}
                className="conversation-refresh-btn"
              >
                🔄 {t('knowledge.chat.history.refresh')}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};
