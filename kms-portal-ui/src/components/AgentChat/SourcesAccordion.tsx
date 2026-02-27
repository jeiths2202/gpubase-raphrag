/**
 * SourcesAccordion Component
 * Collapsible section for displaying RAG source documents
 */

import React, { useState } from 'react';
import { ChevronRight, FileText } from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';

export interface RAGSource {
  title: string;
  content: string;
  score: number;
  product?: string;
  document?: string;
  page?: number;
}

interface SourcesAccordionProps {
  /** Array of RAG source documents */
  sources: RAGSource[];
  /** Whether the accordion should be open by default */
  defaultOpen?: boolean;
  /** Custom class name */
  className?: string;
}

interface SourceCardProps {
  source: RAGSource;
}

const SourceCard: React.FC<SourceCardProps> = ({ source }) => {
  return (
    <div className="source-card">
      <div className="source-card-title">
        <FileText size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
        {source.title || source.document || 'Source Document'}
      </div>
      {source.content && (
        <div className="source-card-content">
          {source.content}
        </div>
      )}
      <div className="source-card-meta">
        {source.score !== undefined && (
          <span className="source-card-score">
            Score: {Math.round(source.score * 100)}%
          </span>
        )}
        {source.product && (
          <span>Product: {source.product}</span>
        )}
        {source.page !== undefined && (
          <span>Page: {source.page}</span>
        )}
      </div>
    </div>
  );
};

export const SourcesAccordion: React.FC<SourcesAccordionProps> = ({
  sources,
  defaultOpen = false,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const { t } = useTranslation();

  if (!sources || sources.length === 0) return null;

  const handleToggle = () => {
    setIsOpen(!isOpen);
  };

  return (
    <div className={`sources-accordion ${className}`}>
      <button
        className="sources-accordion-header"
        onClick={handleToggle}
        aria-expanded={isOpen}
        type="button"
      >
        <ChevronRight
          size={16}
          style={{
            transform: isOpen ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s ease',
          }}
        />
        <span>
          {t('openframeRag.sources', { defaultValue: 'Sources' })} ({sources.length})
        </span>
      </button>

      {isOpen && (
        <div className="sources-accordion-content">
          {sources.map((source, index) => (
            <SourceCard key={index} source={source} />
          ))}
        </div>
      )}
    </div>
  );
};

export default SourcesAccordion;
