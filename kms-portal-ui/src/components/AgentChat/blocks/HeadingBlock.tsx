/**
 * HeadingBlock Component
 * Renders heading text with configurable level (h1-h4)
 */
import React from 'react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface HeadingBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const HeadingBlock: React.FC<HeadingBlockProps> = ({ block, className }) => {
  if (!block.content) return null;

  const level = block.level || 2;
  const Tag = `h${level}` as keyof JSX.IntrinsicElements;

  return (
    <Tag className={`answer-block answer-block-heading level-${level} ${className || ''}`}>
      {block.content}
    </Tag>
  );
};

export default HeadingBlock;
