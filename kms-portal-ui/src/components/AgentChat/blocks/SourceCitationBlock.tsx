/**
 * SourceCitationBlock Component
 * Renders source citations with hover preview functionality
 */
import React, { useState } from 'react';
import { FileText, ExternalLink } from 'lucide-react';
import type { AnswerBlock, BaseBlockProps, SourceCitationInfo } from './types';

interface SourceCitationBlockProps extends BaseBlockProps {
  block: AnswerBlock;
  onClick?: (source: SourceCitationInfo) => void;
}

export const SourceCitationBlock: React.FC<SourceCitationBlockProps> = ({
  block,
  className,
  onClick,
}) => {
  const [isHovered, setIsHovered] = useState(false);

  if (!block.doc_name) return null;

  const handleClick = () => {
    if (onClick) {
      onClick({
        doc_name: block.doc_name || '',
        page: block.page,
        chunk_id: block.chunk_id,
        score: block.score,
      });
    }
  };

  const scorePercent = block.score
    ? Math.round(block.score * 100)
    : null;

  return (
    <div
      className={`answer-block answer-block-source-citation ${className || ''}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <button
        className="source-citation-btn"
        onClick={handleClick}
        type="button"
      >
        <FileText size={14} className="source-icon" />
        <span className="source-name">{block.doc_name}</span>
        {block.page && (
          <span className="source-page">(p.{block.page})</span>
        )}
        {scorePercent !== null && (
          <span className={`source-score ${scorePercent >= 70 ? 'high' : scorePercent >= 40 ? 'medium' : 'low'}`}>
            {scorePercent}%
          </span>
        )}
        <ExternalLink size={12} className="source-link-icon" />
      </button>

      {/* Hover preview tooltip */}
      {isHovered && block.chunk_id && (
        <div className="source-preview-tooltip">
          <div className="tooltip-header">
            <FileText size={12} />
            <span>{block.doc_name}</span>
          </div>
          <div className="tooltip-info">
            {block.page && <span>Page: {block.page}</span>}
            {scorePercent && <span>Relevance: {scorePercent}%</span>}
          </div>
        </div>
      )}
    </div>
  );
};

export default SourceCitationBlock;
