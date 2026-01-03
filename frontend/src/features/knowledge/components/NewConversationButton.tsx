/**
 * NewConversationButton Component
 *
 * Prominent "New Chat" button with loading state and keyboard accessibility.
 *
 * Responsibilities:
 * - Render prominent "New Chat" button with icon
 * - Show loading spinner during conversation creation
 * - Display in ChatHeader next to title
 * - Keyboard accessible (Enter/Space activation)
 * - Tooltip on hover for clarity
 *
 * Design:
 * - Primary button styling (uses themeColors.accent)
 * - Icon: ➕ emoji or custom SVG
 * - Loading state with spinner animation
 * - Hover effects with themeColors.accentHover
 */

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import './NewConversationButton.css';

interface NewConversationButtonProps {
  /** Click handler to create new conversation */
  onClick: () => void;
  /** Loading state during conversation creation */
  isLoading: boolean;
  /** Theme colors for styling (deprecated - uses CSS variables) */
  themeColors?: ThemeColors;
  /** Translation function */
  t: TranslateFunction;
  /** Optional custom label (defaults to translation key) */
  label?: string;
  /** Show icon alongside text */
  showIcon?: boolean;
}

export const NewConversationButton: React.FC<NewConversationButtonProps> = ({
  onClick,
  isLoading,
  themeColors,
  t,
  label,
  showIcon = true
}) => {
  const buttonLabel = label || t('knowledge.chat.newChat.button');
  const tooltipText = t('knowledge.chat.newChat.tooltip');

  return (
    <motion.button
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      disabled={isLoading}
      aria-label={tooltipText}
      title={tooltipText}
      aria-busy={isLoading}
      className="new-conversation-btn"
    >
      {isLoading ? (
        <>
          {/* Loading Spinner */}
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="new-conversation-spinner"
          >
            <circle
              cx="8"
              cy="8"
              r="6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray="30 10"
            />
          </svg>
          <span>{t('knowledge.chat.newChat.creating')}</span>
        </>
      ) : (
        <>
          {showIcon && <span className="new-conversation-icon">➕</span>}
          <span>{buttonLabel}</span>
        </>
      )}
    </motion.button>
  );
};
