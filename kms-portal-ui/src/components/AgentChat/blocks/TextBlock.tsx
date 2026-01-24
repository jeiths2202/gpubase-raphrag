/**
 * TextBlock Component
 * Renders plain text content with markdown support
 */
import React from 'react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface TextBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const TextBlock: React.FC<TextBlockProps> = ({ block, className }) => {
  if (!block.content) return null;

  return (
    <div className={`answer-block answer-block-text ${className || ''}`}>
      <p>{block.content}</p>
    </div>
  );
};

export default TextBlock;
