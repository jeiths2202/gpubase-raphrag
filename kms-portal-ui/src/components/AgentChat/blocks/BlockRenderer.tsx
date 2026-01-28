/**
 * BlockRenderer Component
 * Main component that routes blocks to appropriate renderers
 *
 * This is the entry point for rendering ChatGPT-style structured answers.
 */
import React from 'react';
import type { BlockRendererProps, AnswerBlock, SourceCitationInfo } from './types';

import { TextBlock } from './TextBlock';
import { HeadingBlock } from './HeadingBlock';
import { ListBlock } from './ListBlock';
import { CodeBlock } from './CodeBlock';
import { TableBlock } from './TableBlock';
import { QuoteBlock } from './QuoteBlock';
import { ImageBlock } from './ImageBlock';
import { SourceCitationBlock } from './SourceCitationBlock';
import { NoAnswerBlock } from './NoAnswerBlock';
import { SkeletonBlock } from './SkeletonBlock';
import { ProductVersionBlock } from './ProductVersionBlock';

/**
 * Renders a single block based on its type
 */
const renderBlock = (
  block: AnswerBlock,
  index: number,
  onSourceClick?: (source: SourceCitationInfo) => void
): React.ReactNode => {
  const key = `block-${index}-${block.type}`;

  switch (block.type) {
    case 'text':
      return <TextBlock key={key} block={block} />;

    case 'heading':
      return <HeadingBlock key={key} block={block} />;

    case 'list':
      return <ListBlock key={key} block={block} />;

    case 'code':
      return <CodeBlock key={key} block={block} />;

    case 'table':
      return <TableBlock key={key} block={block} />;

    case 'quote':
      return <QuoteBlock key={key} block={block} />;

    case 'image':
      return <ImageBlock key={key} block={block} />;

    case 'source_citation':
      return (
        <SourceCitationBlock
          key={key}
          block={block}
          onClick={onSourceClick}
        />
      );

    case 'no_answer':
      return <NoAnswerBlock key={key} block={block} />;

    case 'product_version':
      return <ProductVersionBlock key={key} block={block} />;

    default:
      // Fallback: render as text
      console.warn(`Unknown block type: ${block.type}`);
      return <TextBlock key={key} block={block} />;
  }
};

/**
 * BlockRenderer - Main component for rendering structured answers
 *
 * @param blocks - Array of AnswerBlock objects to render
 * @param isStreaming - Whether answer is still being streamed
 * @param onSourceClick - Callback when a source citation is clicked
 */
export const BlockRenderer: React.FC<BlockRendererProps> = ({
  blocks,
  isStreaming = false,
  onSourceClick,
}) => {
  if (!blocks || blocks.length === 0) {
    if (isStreaming) {
      return (
        <div className="block-renderer streaming">
          <SkeletonBlock />
        </div>
      );
    }
    return null;
  }

  // Separate content blocks from citation blocks for layout
  const contentBlocks = blocks.filter(b => b.type !== 'source_citation');
  const citationBlocks = blocks.filter(b => b.type === 'source_citation');

  return (
    <div className={`block-renderer ${isStreaming ? 'streaming' : ''}`}>
      {/* Content blocks */}
      <div className="block-content">
        {contentBlocks.map((block, index) => renderBlock(block, index, onSourceClick))}

        {/* Show skeleton while streaming */}
        {isStreaming && <SkeletonBlock />}
      </div>

      {/* Source citations in a separate section */}
      {citationBlocks.length > 0 && (
        <div className="block-citations">
          <div className="citations-header">
            <span className="citations-label">Sources</span>
            <span className="citations-count">{citationBlocks.length}</span>
          </div>
          <div className="citations-list">
            {citationBlocks.map((block, index) => (
              renderBlock(block, contentBlocks.length + index, onSourceClick)
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default BlockRenderer;
