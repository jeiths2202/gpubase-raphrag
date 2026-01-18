/**
 * SearchProgressModal
 * Visual modal to display RAG knowledge search progress and results.
 * Shows 5 sections: Query Analysis, Chunk Structure, Embedding Info, Tool Progress, Generation
 */
import React, { useState, useCallback, useMemo } from 'react';
import {
  X,
  ChevronDown,
  ChevronRight,
  Search,
  Database,
  Network,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Zap,
  Tag,
  Layers,
  Cpu,
  MessageSquare,
  BarChart3,
} from 'lucide-react';
import type {
  SearchToolResult,
  SearchResultItem,
  RagAnalysis,
  ChunkStructure,
  EmbeddingInfo,
  GenerationProgress
} from './types';

// Re-export types for consumers
export type { SearchToolResult, SearchResultItem };

interface RagProgressData {
  ragAnalysis: RagAnalysis | null;
  chunkStructures: ChunkStructure[];
  embeddingInfos: EmbeddingInfo[];
  generationProgress: GenerationProgress | null;
  isGenerating: boolean;
}

interface SearchProgressModalProps {
  isOpen: boolean;
  onClose: () => void;
  query: string;
  toolResults: SearchToolResult[];
  isSearching: boolean;
  ragProgress?: RagProgressData;
  totalTime?: number;
  t: (key: string) => string;
}

// Tool name to icon mapping
const TOOL_ICONS: Record<string, React.ReactNode> = {
  adaptive_search: <Database size={18} />,
  vector_search: <Search size={18} />,
  graph_query: <Network size={18} />,
  document_read: <FileText size={18} />,
};

// Status indicator component
const StatusIndicator: React.FC<{ status: SearchToolResult['status'] }> = ({ status }) => {
  switch (status) {
    case 'pending':
      return <Clock size={16} className="search-status-icon pending" />;
    case 'running':
      return <Loader2 size={16} className="search-status-icon running spinning" />;
    case 'success':
      return <CheckCircle2 size={16} className="search-status-icon success" />;
    case 'error':
      return <XCircle size={16} className="search-status-icon error" />;
    default:
      return null;
  }
};

// Generic collapsible section component
const CollapsibleSection: React.FC<{
  title: string;
  icon: React.ReactNode;
  badge?: React.ReactNode;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  className?: string;
}> = ({ title, icon, badge, isExpanded, onToggle, children, className = '' }) => {
  return (
    <div className={`search-section ${className}`}>
      <div className="search-section-header" onClick={onToggle}>
        <div className="search-section-left">
          <span className="search-section-toggle">
            {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </span>
          <span className="search-section-icon">{icon}</span>
          <span className="search-section-title">{title}</span>
        </div>
        <div className="search-section-right">
          {badge}
        </div>
      </div>
      {isExpanded && (
        <div className="search-section-content">
          {children}
        </div>
      )}
    </div>
  );
};

// 1. Query Analysis Section
const QueryAnalysisSection: React.FC<{
  analysis: RagAnalysis | null;
  isExpanded: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}> = ({ analysis, isExpanded, onToggle, t }) => {
  if (!analysis) return null;

  return (
    <CollapsibleSection
      title={t('common.ragProgress.queryAnalysis') || '키워드 분석'}
      icon={<Tag size={18} />}
      badge={
        <span className="search-badge info">
          {analysis.keywords.length} {t('common.ragProgress.keywords') || '키워드'}
        </span>
      }
      isExpanded={isExpanded}
      onToggle={onToggle}
      className="query-analysis"
    >
      <div className="rag-analysis-content">
        <div className="rag-analysis-row">
          <span className="rag-label">{t('common.ragProgress.intent') || '의도'}:</span>
          <span className="rag-value intent-badge">{analysis.intent}</span>
        </div>
        <div className="rag-analysis-row">
          <span className="rag-label">{t('common.ragProgress.extractedKeywords') || '추출된 키워드'}:</span>
          <div className="rag-keywords">
            {analysis.keywords.map((kw, idx) => (
              <span key={idx} className="rag-keyword">{kw}</span>
            ))}
          </div>
        </div>
        <div className="rag-analysis-row">
          <span className="rag-label">{t('common.ragProgress.searchStrategy') || '검색 전략'}:</span>
          <div className="rag-strategies">
            {analysis.search_strategy.map((s, idx) => (
              <span key={idx} className="rag-strategy">{s}</span>
            ))}
          </div>
        </div>
        <div className="rag-analysis-row">
          <span className="rag-label">{t('common.ragProgress.tokenCount') || '토큰 수'}:</span>
          <span className="rag-value">{analysis.token_count}</span>
        </div>
      </div>
    </CollapsibleSection>
  );
};

// 2. Chunk Structure Section
const ChunkStructureSection: React.FC<{
  structures: ChunkStructure[];
  isExpanded: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}> = ({ structures, isExpanded, onToggle, t }) => {
  if (structures.length === 0) return null;

  const totalChunks = structures.reduce((sum, s) => sum + s.total_chunks, 0);

  return (
    <CollapsibleSection
      title={t('common.ragProgress.chunkStructure') || '문서 청킹 구조'}
      icon={<Layers size={18} />}
      badge={
        <span className="search-badge success">
          {totalChunks} {t('common.ragProgress.chunks') || '청크'}
        </span>
      }
      isExpanded={isExpanded}
      onToggle={onToggle}
      className="chunk-structure"
    >
      {structures.map((structure, idx) => (
        <div key={idx} className="chunk-structure-item">
          <div className="chunk-structure-header">
            <span className="chunk-tool-name">{structure.tool_name}</span>
            <span className="chunk-total">{structure.total_chunks} 청크</span>
          </div>

          {/* Chunk types */}
          <div className="chunk-types">
            <span className="chunk-label">{t('common.ragProgress.chunkTypes') || '청크 타입'}:</span>
            {Object.entries(structure.chunk_types).map(([type, count]) => (
              <span key={type} className="chunk-type-badge">
                {type}: {count}
              </span>
            ))}
          </div>

          {/* Page distribution */}
          {Object.keys(structure.page_distribution).length > 0 && (
            <div className="chunk-pages">
              <span className="chunk-label">{t('common.ragProgress.pageDistribution') || '페이지 분포'}:</span>
              {Object.entries(structure.page_distribution).slice(0, 5).map(([page, count]) => (
                <span key={page} className="chunk-page-badge">
                  p.{page}: {count}
                </span>
              ))}
            </div>
          )}

          {/* Avg chunk size */}
          <div className="chunk-avg-size">
            <span className="chunk-label">{t('common.ragProgress.avgChunkSize') || '평균 청크 크기'}:</span>
            <span className="chunk-size-value">{structure.avg_chunk_size} chars</span>
          </div>

          {/* Preview */}
          {structure.chunks_preview.length > 0 && (
            <div className="chunk-previews">
              <span className="chunk-label">{t('common.ragProgress.preview') || '미리보기'}:</span>
              {structure.chunks_preview.slice(0, 3).map((preview, pIdx) => (
                <div key={pIdx} className="chunk-preview-item">
                  <div className="chunk-preview-meta">
                    <span className="preview-index">#{preview.index}</span>
                    <span className="preview-type">{preview.type}</span>
                    {preview.page > 0 && <span className="preview-page">p.{preview.page}</span>}
                    <span className="preview-similarity">{(preview.similarity * 100).toFixed(1)}%</span>
                  </div>
                  <div className="chunk-preview-text">{preview.preview}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </CollapsibleSection>
  );
};

// 3. Embedding Info Section
const EmbeddingInfoSection: React.FC<{
  embeddings: EmbeddingInfo[];
  isExpanded: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}> = ({ embeddings, isExpanded, onToggle, t }) => {
  if (embeddings.length === 0) return null;

  return (
    <CollapsibleSection
      title={t('common.ragProgress.embeddingInfo') || '임베딩 정보'}
      icon={<Cpu size={18} />}
      badge={
        <span className="search-badge primary">
          {embeddings[0]?.model || 'Embedding'}
        </span>
      }
      isExpanded={isExpanded}
      onToggle={onToggle}
      className="embedding-info"
    >
      {embeddings.map((embedding, idx) => (
        <div key={idx} className="embedding-info-item">
          <div className="embedding-header">
            <span className="embedding-tool">{embedding.tool_name}</span>
            <span className="embedding-model">{embedding.model}</span>
          </div>

          {/* Score distribution */}
          <div className="embedding-distribution">
            <span className="embedding-label">{t('common.ragProgress.scoreDistribution') || '점수 분포'}:</span>
            <div className="score-bars">
              <div className="score-bar-item excellent">
                <span className="score-bar-label">Excellent (≥80%)</span>
                <div className="score-bar">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${(embedding.score_distribution.excellent / (embedding.similarity_scores.length || 1)) * 100}%` }}
                  />
                </div>
                <span className="score-bar-count">{embedding.score_distribution.excellent}</span>
              </div>
              <div className="score-bar-item good">
                <span className="score-bar-label">Good (≥60%)</span>
                <div className="score-bar">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${(embedding.score_distribution.good / (embedding.similarity_scores.length || 1)) * 100}%` }}
                  />
                </div>
                <span className="score-bar-count">{embedding.score_distribution.good}</span>
              </div>
              <div className="score-bar-item fair">
                <span className="score-bar-label">Fair (≥40%)</span>
                <div className="score-bar">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${(embedding.score_distribution.fair / (embedding.similarity_scores.length || 1)) * 100}%` }}
                  />
                </div>
                <span className="score-bar-count">{embedding.score_distribution.fair}</span>
              </div>
              <div className="score-bar-item low">
                <span className="score-bar-label">Low (&lt;40%)</span>
                <div className="score-bar">
                  <div
                    className="score-bar-fill"
                    style={{ width: `${(embedding.score_distribution.low / (embedding.similarity_scores.length || 1)) * 100}%` }}
                  />
                </div>
                <span className="score-bar-count">{embedding.score_distribution.low}</span>
              </div>
            </div>
          </div>

          {/* Top matches */}
          {embedding.top_matches.length > 0 && (
            <div className="embedding-top-matches">
              <span className="embedding-label">{t('common.ragProgress.topMatches') || '상위 매치'}:</span>
              <div className="top-matches-list">
                {embedding.top_matches.map((match, mIdx) => (
                  <div key={mIdx} className="top-match-item">
                    <span className="match-rank">#{match.rank}</span>
                    <span className="match-source" title={match.source}>
                      {match.source.length > 30 ? match.source.slice(0, 30) + '...' : match.source}
                    </span>
                    <span className={`match-score ${match.score >= 0.7 ? 'high' : match.score >= 0.4 ? 'medium' : 'low'}`}>
                      {match.score_pct}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}
    </CollapsibleSection>
  );
};

// 4. Tool Progress Section
const ToolProgressSection: React.FC<{
  toolResults: SearchToolResult[];
  isExpanded: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}> = ({ toolResults, isExpanded, onToggle, t }) => {
  const completed = toolResults.filter(t => t.status === 'success' || t.status === 'error').length;
  const totalResults = toolResults.reduce((sum, tr) => sum + (tr.resultCount || 0), 0);

  return (
    <CollapsibleSection
      title={t('common.ragProgress.toolProgress') || 'Tool 처리과정'}
      icon={<BarChart3 size={18} />}
      badge={
        <span className="search-badge">
          {completed}/{toolResults.length} | {totalResults} {t('common.searchProgress.results') || 'results'}
        </span>
      }
      isExpanded={isExpanded}
      onToggle={onToggle}
      className="tool-progress"
    >
      <div className="tool-results-list">
        {toolResults.map(toolResult => {
          const duration = toolResult.startTime && toolResult.endTime
            ? toolResult.endTime - toolResult.startTime
            : undefined;

          return (
            <div key={toolResult.toolName} className={`tool-result-item ${toolResult.status}`}>
              <div className="tool-result-header">
                <span className="tool-icon">
                  {TOOL_ICONS[toolResult.toolName] || <Search size={16} />}
                </span>
                <span className="tool-name">
                  {t(`searchProgress.tools.${toolResult.toolName}`) || toolResult.toolName}
                </span>
                <div className="tool-meta">
                  {toolResult.resultCount !== undefined && toolResult.status === 'success' && (
                    <span className="tool-count">{toolResult.resultCount}건</span>
                  )}
                  {duration !== undefined && (
                    <span className="tool-duration">{duration}ms</span>
                  )}
                  <StatusIndicator status={toolResult.status} />
                </div>
              </div>

              {/* Query correction notice */}
              {toolResult.queryCorrected && (
                <div className="tool-query-correction">
                  <AlertCircle size={12} />
                  <span><code>{toolResult.originalQuery}</code> → <code>{toolResult.correctedQuery}</code></span>
                </div>
              )}

              {/* Status content */}
              {toolResult.status === 'running' && (
                <div className="tool-running">
                  <Loader2 size={14} className="spinning" />
                  <span>{t('common.searchProgress.running') || '검색 중...'}</span>
                </div>
              )}

              {toolResult.status === 'error' && (
                <div className="tool-error">
                  <XCircle size={14} />
                  <span>{toolResult.error}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </CollapsibleSection>
  );
};

// 5. Generation Progress Section
const GenerationProgressSection: React.FC<{
  progress: GenerationProgress | null;
  isGenerating: boolean;
  isExpanded: boolean;
  onToggle: () => void;
  t: (key: string) => string;
}> = ({ progress, isGenerating, isExpanded, onToggle, t }) => {
  if (!progress && !isGenerating) return null;

  return (
    <CollapsibleSection
      title={t('common.ragProgress.generationProgress') || '답변 생성 과정'}
      icon={<MessageSquare size={18} />}
      badge={
        isGenerating ? (
          <span className="search-badge generating">
            <Loader2 size={12} className="spinning" />
            {progress?.progress_pct ? `${progress.progress_pct}%` : '생성 중...'}
          </span>
        ) : (
          <span className="search-badge success">
            <CheckCircle2 size={12} />
            {t('common.ragProgress.completed') || '완료'}
          </span>
        )
      }
      isExpanded={isExpanded}
      onToggle={onToggle}
      className="generation-progress"
    >
      <div className="generation-content">
        {progress && (
          <>
            {/* Progress bar */}
            <div className="generation-progress-bar">
              <div
                className="generation-progress-fill"
                style={{ width: `${progress.progress_pct || 0}%` }}
              />
            </div>

            {/* Stats */}
            <div className="generation-stats">
              {progress.total_sources !== undefined && (
                <div className="generation-stat">
                  <span className="stat-label">{t('common.ragProgress.sourcesUsed') || '사용된 소스'}:</span>
                  <span className="stat-value">{progress.total_sources}</span>
                </div>
              )}
              {progress.tools_used && progress.tools_used.length > 0 && (
                <div className="generation-stat">
                  <span className="stat-label">{t('common.ragProgress.toolsUsed') || '사용된 도구'}:</span>
                  <span className="stat-value">{progress.tools_used.join(', ')}</span>
                </div>
              )}
              {progress.answer_length !== undefined && (
                <div className="generation-stat">
                  <span className="stat-label">{t('common.ragProgress.answerLength') || '답변 길이'}:</span>
                  <span className="stat-value">{progress.answer_length} chars</span>
                </div>
              )}
              {progress.current_chunk !== undefined && progress.total_chunks !== undefined && (
                <div className="generation-stat">
                  <span className="stat-label">{t('common.ragProgress.chunkProgress') || '청크 진행'}:</span>
                  <span className="stat-value">{progress.current_chunk}/{progress.total_chunks}</span>
                </div>
              )}
            </div>
          </>
        )}

        {isGenerating && !progress && (
          <div className="generation-waiting">
            <Loader2 size={16} className="spinning" />
            <span>{t('common.ragProgress.preparingAnswer') || '답변 준비 중...'}</span>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
};

// Main modal component
export const SearchProgressModal: React.FC<SearchProgressModalProps> = ({
  isOpen,
  onClose,
  query,
  toolResults,
  isSearching,
  ragProgress,
  totalTime,
  t,
}) => {
  // Track expanded sections
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    queryAnalysis: true,
    chunkStructure: false,
    embeddingInfo: false,
    toolProgress: true,
    generationProgress: true,
  });

  // Toggle section expansion
  const toggleSection = useCallback((sectionName: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [sectionName]: !prev[sectionName],
    }));
  }, []);

  // Expand all sections
  const expandAll = useCallback(() => {
    setExpandedSections({
      queryAnalysis: true,
      chunkStructure: true,
      embeddingInfo: true,
      toolProgress: true,
      generationProgress: true,
    });
  }, []);

  // Collapse all sections
  const collapseAll = useCallback(() => {
    setExpandedSections({
      queryAnalysis: false,
      chunkStructure: false,
      embeddingInfo: false,
      toolProgress: false,
      generationProgress: false,
    });
  }, []);

  // Calculate total results
  const totalResults = useMemo(() => {
    return toolResults.reduce((sum, tr) => sum + (tr.resultCount || 0), 0);
  }, [toolResults]);

  if (!isOpen) return null;

  return (
    <div className="search-progress-modal-overlay" onClick={onClose}>
      <div className="search-progress-modal" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="search-progress-modal-header">
          <div className="search-progress-header-left">
            <Zap size={20} className="search-progress-icon" />
            <h3>{t('common.searchProgress.title') || 'RAG 검색 진행 상황'}</h3>
          </div>
          <button className="search-progress-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Query info */}
        <div className="search-progress-query">
          <span className="search-progress-query-label">{t('common.searchProgress.query') || '쿼리'}:</span>
          <span className="search-progress-query-text">"{query}"</span>
        </div>

        {/* Progress overview */}
        <div className="search-progress-overview">
          <div className="search-progress-stats">
            <span className="search-stat">
              <Search size={14} />
              {totalResults} {t('common.searchProgress.totalResults') || 'results'}
            </span>
            {totalTime && (
              <span className="search-stat">
                <Clock size={14} />
                {totalTime}ms
              </span>
            )}
            {isSearching && (
              <span className="search-stat searching">
                <Loader2 size={14} className="spinning" />
                {t('common.searchProgress.searching') || '검색 중...'}
              </span>
            )}
          </div>
        </div>

        {/* Section controls */}
        <div className="search-progress-controls">
          <button className="search-control-btn" onClick={expandAll}>
            <ChevronDown size={14} />
            {t('common.searchProgress.expandAll') || '모두 펼치기'}
          </button>
          <button className="search-control-btn" onClick={collapseAll}>
            <ChevronRight size={14} />
            {t('common.searchProgress.collapseAll') || '모두 접기'}
          </button>
        </div>

        {/* 5 Sections */}
        <div className="search-progress-sections">
          {/* 1. Query Analysis */}
          <QueryAnalysisSection
            analysis={ragProgress?.ragAnalysis || null}
            isExpanded={expandedSections.queryAnalysis}
            onToggle={() => toggleSection('queryAnalysis')}
            t={t}
          />

          {/* 2. Chunk Structure */}
          <ChunkStructureSection
            structures={ragProgress?.chunkStructures || []}
            isExpanded={expandedSections.chunkStructure}
            onToggle={() => toggleSection('chunkStructure')}
            t={t}
          />

          {/* 3. Embedding Info */}
          <EmbeddingInfoSection
            embeddings={ragProgress?.embeddingInfos || []}
            isExpanded={expandedSections.embeddingInfo}
            onToggle={() => toggleSection('embeddingInfo')}
            t={t}
          />

          {/* 4. Tool Progress */}
          <ToolProgressSection
            toolResults={toolResults}
            isExpanded={expandedSections.toolProgress}
            onToggle={() => toggleSection('toolProgress')}
            t={t}
          />

          {/* 5. Generation Progress */}
          <GenerationProgressSection
            progress={ragProgress?.generationProgress || null}
            isGenerating={ragProgress?.isGenerating || false}
            isExpanded={expandedSections.generationProgress}
            onToggle={() => toggleSection('generationProgress')}
            t={t}
          />
        </div>

        {/* Footer */}
        <div className="search-progress-modal-footer">
          <button className="search-progress-close-btn" onClick={onClose}>
            {t('common.close') || '닫기'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SearchProgressModal;
