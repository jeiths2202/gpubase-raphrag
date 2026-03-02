/**
 * TypingCursor Component
 * Displays a blinking cursor during streaming to create a typing effect
 */

import React from 'react';

interface TypingCursorProps {
  /** Whether streaming is currently active */
  isStreaming: boolean;
  /** Custom class name */
  className?: string;
}

export const TypingCursor: React.FC<TypingCursorProps> = ({
  isStreaming,
  className = '',
}) => {
  if (!isStreaming) return null;

  return (
    <span
      className={`typing-cursor ${className}`}
      aria-hidden="true"
      role="presentation"
    >
      ▌
    </span>
  );
};

export default TypingCursor;
