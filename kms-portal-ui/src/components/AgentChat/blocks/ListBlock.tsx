/**
 * ListBlock Component
 * Renders ordered or unordered lists
 */
import React from 'react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface ListBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const ListBlock: React.FC<ListBlockProps> = ({ block, className }) => {
  if (!block.items || block.items.length === 0) return null;

  const ListTag = block.ordered ? 'ol' : 'ul';

  return (
    <ListTag className={`answer-block answer-block-list ${block.ordered ? 'ordered' : 'unordered'} ${className || ''}`}>
      {block.items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ListTag>
  );
};

export default ListBlock;
