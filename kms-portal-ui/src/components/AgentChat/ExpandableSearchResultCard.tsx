/**
 * ExpandableSearchResultCard Component
 * Displays individual search results in expandable card format.
 * Each card shows: title, content (text), images, tables, and source info.
 */

import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  Table2,
} from 'lucide-react';
import { MessageContent } from './MessageContent';
import type { ExpandableSearchResult } from './types';

interface ExpandableSearchResultCardProps {
  result: ExpandableSearchResult;
  defaultExpanded?: boolean;
}

/**
 * Individual expandable search result card
 */
export const ExpandableSearchResultCard: React.FC<ExpandableSearchResultCardProps> = ({
  result,
  defaultExpanded = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [activeTab, setActiveTab] = useState<'content' | 'images' | 'tables'>('content');

  const hasImages = result.images && result.images.length > 0;
  const hasTables = result.tables && result.tables.length > 0;
  const scorePercent = result.score ? Math.round(result.score * 100) : null;

  // Format page display
  const formatPageRange = () => {
    const { pageStart, pageEnd } = result.source;
    if (!pageStart) return null;
    if (pageStart === pageEnd) return `p.${pageStart}`;
    return `p.${pageStart}-${pageEnd}`;
  };

  return (
    <div className={`search-result-card ${isExpanded ? 'expanded' : 'collapsed'}`}>
      {/* Card Header - Always visible */}
      <button
        className="search-result-card-header"
        onClick={() => setIsExpanded(!isExpanded)}
        type="button"
      >
        <span className="search-result-toggle">
          {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>

        <span className="search-result-index">#{result.index}</span>

        <span className="search-result-title">
          {result.title || result.source.documentName}
        </span>

        {/* Badge indicators */}
        <div className="search-result-badges">
          {hasImages && (
            <span className="search-result-badge images">
              <ImageIcon size={10} />
              {result.images.length}
            </span>
          )}
          {hasTables && (
            <span className="search-result-badge tables">
              <Table2 size={10} />
              {result.tables.length}
            </span>
          )}
        </div>

        {/* Relevance score */}
        {scorePercent !== null && (
          <span className="search-result-score">{scorePercent}%</span>
        )}
      </button>

      {/* Card Body - Expandable */}
      {isExpanded && (
        <div className="search-result-card-body">
          {/* Tabs for content/images/tables */}
          {(hasImages || hasTables) && (
            <div className="search-result-tabs">
              <button
                className={`search-result-tab ${activeTab === 'content' ? 'active' : ''}`}
                onClick={() => setActiveTab('content')}
                type="button"
              >
                <FileText size={12} />
                텍스트
              </button>
              {hasImages && (
                <button
                  className={`search-result-tab ${activeTab === 'images' ? 'active' : ''}`}
                  onClick={() => setActiveTab('images')}
                  type="button"
                >
                  <ImageIcon size={12} />
                  이미지 ({result.images.length})
                </button>
              )}
              {hasTables && (
                <button
                  className={`search-result-tab ${activeTab === 'tables' ? 'active' : ''}`}
                  onClick={() => setActiveTab('tables')}
                  type="button"
                >
                  <Table2 size={12} />
                  표 ({result.tables.length})
                </button>
              )}
            </div>
          )}

          {/* Tab Content */}
          <div className="search-result-tab-content">
            {/* Text Content */}
            {activeTab === 'content' && (
              <div className="search-result-text">
                <MessageContent content={result.content} />
              </div>
            )}

            {/* Images */}
            {activeTab === 'images' && hasImages && (
              <div className="search-result-images">
                {result.images.map((img, idx) => (
                  <div key={idx} className="search-result-image-item">
                    <img
                      src={img.url}
                      alt={`Result image ${idx + 1}`}
                      loading="lazy"
                      className="search-result-image"
                    />
                    {img.pageNumber && (
                      <span className="search-result-image-page">p.{img.pageNumber}</span>
                    )}
                    {img.similarity && (
                      <span className="search-result-image-score">
                        {Math.round(img.similarity * 100)}%
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Tables */}
            {activeTab === 'tables' && hasTables && (
              <div className="search-result-tables">
                {result.tables.map((table, idx) => (
                  <div key={idx} className="search-result-table-item">
                    <MessageContent content={table.markdown} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Source Info */}
          <div className="search-result-source">
            <FileText size={12} />
            <span className="search-result-source-name">
              {result.source.documentName}
            </span>
            {formatPageRange() && (
              <span className="search-result-source-page">
                {formatPageRange()}
              </span>
            )}
            {result.source.sectionTitle && (
              <span className="search-result-source-section">
                § {result.source.sectionTitle}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

/**
 * Container for multiple search result cards
 */
interface SearchResultCardsProps {
  results: ExpandableSearchResult[];
  title?: string;
}

export const SearchResultCards: React.FC<SearchResultCardsProps> = ({
  results,
  title = '검색 결과',
}) => {
  const [allExpanded, setAllExpanded] = useState(false);

  if (!results || results.length === 0) return null;

  return (
    <div className="search-result-cards-container">
      <div className="search-result-cards-header">
        <span className="search-result-cards-title">
          {title} ({results.length})
        </span>
        <button
          className="search-result-expand-all"
          onClick={() => setAllExpanded(!allExpanded)}
          type="button"
        >
          {allExpanded ? '모두 접기' : '모두 펼치기'}
          {allExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>
      <div className="search-result-cards-list">
        {results.map((result, idx) => (
          <ExpandableSearchResultCard
            key={result.chunkId || idx}
            result={result}
            defaultExpanded={allExpanded}
          />
        ))}
      </div>
    </div>
  );
};

export default SearchResultCards;
