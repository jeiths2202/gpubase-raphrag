/**
 * QuoteBlock Component
 * Renders quoted/blockquote content
 */
import React from 'react';
import { Quote } from 'lucide-react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface QuoteBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const QuoteBlock: React.FC<QuoteBlockProps> = ({ block, className }) => {
  if (!block.content) return null;

  return (
    <blockquote className={`answer-block answer-block-quote ${className || ''}`}>
      <Quote size={16} className="quote-icon" />
      <p>{block.content}</p>
    </blockquote>
  );
};

export default QuoteBlock;
