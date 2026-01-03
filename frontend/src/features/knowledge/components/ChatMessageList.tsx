/**
 * ChatMessageList Component
 *
 * Pure presentational component for rendering scrollable chat message list
 * with auto-scroll behavior and custom scrollbar styling.
 *
 * Extracted from ChatTab.tsx (lines 160-240) to enable:
 * - Separation of concerns (message rendering vs chat orchestration)
 * - Reusable scroll behavior via useChatScroll hook
 * - Custom scrollbar styling matching MainDashboard pattern
 * - "Scroll to bottom" floating button when user scrolls up
 *
 * Responsibilities:
 * - Render scrollable message container with custom scrollbar
 * - Auto-scroll to bottom when new messages arrive
 * - Preserve scroll position when user manually scrolls up
 * - Handle loading indicator placement
 * - Display empty state with quick prompt suggestions
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useChatScroll } from '../hooks/useChatScroll';
import type { ChatMessage, ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import './ChatMessageList.css';

interface ChatMessageListProps {
  /** Array of chat messages to render */
  messages: ChatMessage[];
  /** Loading state for AI response generation */
  isLoading: boolean;
  /** Theme colors for styling (deprecated - uses CSS variables) */
  themeColors?: ThemeColors;
  /** Callback when user clicks a source citation */
  onSelectSource: (source: any) => void;
  /** Callback when user saves response to notes */
  onSaveResponse: (messageId: string) => void;
  /** Callback to set input message for quick prompts */
  onSetInputMessage: (message: string) => void;
  /** Translation function */
  t: TranslateFunction;
  /** Card styling object (deprecated - uses CSS classes) */
  cardStyle?: React.CSSProperties;
  /** Tab styling function (deprecated - uses CSS classes) */
  tabStyle?: (active: boolean) => React.CSSProperties;
  /** Initial scroll position to restore */
  initialScrollPosition?: number;
  /** Callback to persist scroll position */
  onScrollPositionChange?: (scrollTop: number) => void;
}

export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  isLoading,
  themeColors,
  onSelectSource,
  onSaveResponse,
  onSetInputMessage,
  t,
  cardStyle,
  tabStyle,
  initialScrollPosition,
  onScrollPositionChange
}) => {
  const { containerRef, isAtBottom, scrollToBottom, handleScroll } = useChatScroll({
    messages,
    bottomThreshold: 100,
    persistScrollPosition: true,
    onScrollPositionChange,
    initialScrollPosition
  });

  // Viewport-based layout: Use remaining space and scroll when needed
  // Container takes all available space (flex: 1) and scrolls if content exceeds viewport
  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={`chat-message-list ${messages.length === 0 ? 'chat-message-list-empty' : ''}`}
    >
      {/* Empty State - Compact */}
      {messages.length === 0 ? (
        <div className="chat-empty-state">
          <p className="chat-empty-state-prompt">{t('knowledge.chat.startPrompt')}</p>
          <div className="chat-empty-state-actions">
            {[
              { key: 'summarize', label: t('knowledge.chat.quickPrompts.summarize') },
              { key: 'keyConcepts', label: t('knowledge.chat.quickPrompts.keyConcepts') },
              { key: 'showExamples', label: t('knowledge.chat.quickPrompts.showExamples') }
            ].map((q) => (
              <button
                key={q.key}
                onClick={() => onSetInputMessage(q.label)}
                className="chat-quick-prompt"
              >
                {q.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          {/* Message List */}
          {messages.map(msg => (
            <div
              key={msg.id}
              className={`chat-message ${msg.role === 'user' ? 'chat-message-user' : 'chat-message-assistant'}`}
            >
              {/* Message Content */}
              <div className="chat-message-content">{msg.content}</div>

              {/* Sources (Citations) - Compact */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="chat-message-sources">
                  <div className="chat-message-sources-header">
                    {t('knowledge.sources')} ({msg.sources.length}):
                  </div>
                  {msg.sources.map((source, idx) => (
                    <div
                      key={idx}
                      onClick={() => onSelectSource(source)}
                      className="chat-message-source-item"
                    >
                      <span className="chat-message-source-number">[{idx + 1}]</span> {source.doc_name} ({t('knowledge.chat.confidence')}: {(source.score * 100).toFixed(0)}%)
                    </div>
                  ))}
                </div>
              )}

              {/* Save to Note Button (for assistant messages) - Compact */}
              {msg.role === 'assistant' && (
                <button
                  onClick={() => onSaveResponse(msg.id)}
                  className="chat-save-note-btn"
                >
                  📝 {t('knowledge.chat.saveAsNote')}
                </button>
              )}
            </div>
          ))}

          {/* Loading Indicator - Compact */}
          {isLoading && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="chat-loading"
            >
              <div className="chat-loading-content">
                <div className="chat-loading-dots">
                  <span>•</span>
                  <span>•</span>
                  <span>•</span>
                </div>
                <span>{t('knowledge.chat.generating')}</span>
              </div>
            </motion.div>
          )}
        </>
      )}

      {/* Scroll to Bottom Button (floating) - Compact */}
      <AnimatePresence>
        {!isAtBottom && messages.length > 0 && (
          <motion.button
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            onClick={() => scrollToBottom('smooth')}
            className="chat-scroll-to-bottom"
            aria-label={t('knowledge.chat.scroll.scrollToBottom')}
            title={t('knowledge.chat.scroll.scrollToBottom')}
          >
            ↓
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
};
