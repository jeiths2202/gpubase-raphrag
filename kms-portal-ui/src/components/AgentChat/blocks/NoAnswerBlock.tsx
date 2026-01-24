/**
 * NoAnswerBlock Component
 * Renders a "no relevant information found" message
 */
import React from 'react';
import { AlertCircle } from 'lucide-react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface NoAnswerBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const NoAnswerBlock: React.FC<NoAnswerBlockProps> = ({ block, className }) => {
  const defaultMessage = 'No relevant information found. Try searching with different keywords.';

  return (
    <div className={`answer-block answer-block-no-answer ${className || ''}`}>
      <AlertCircle size={20} className="no-answer-icon" />
      <p>{block.content || defaultMessage}</p>
    </div>
  );
};

export default NoAnswerBlock;
