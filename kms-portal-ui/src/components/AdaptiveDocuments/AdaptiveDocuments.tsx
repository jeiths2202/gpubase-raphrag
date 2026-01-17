/**
 * AdaptiveDocuments Component
 *
 * Component for managing adaptive PDF embedding with structure-preserving chunking.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  adaptiveDocumentsApi,
  ChunkListItem,
  CoverageResponse,
  QualityResponse,
  StructureAnalysisResponse,
  SearchResultItem,
  ChunkType,
} from '../../api';
import './AdaptiveDocuments.css';

// =============================================================================
// Types
// =============================================================================

interface AdaptiveDocument {
  pdf_id: string;
  name: string;
  status: string;
  chunks_count: number;
  created_at: string;
}

type ViewMode = 'list' | 'chunks' | 'coverage' | 'quality' | 'structure' | 'search';

// =============================================================================
// Main Component
// =============================================================================

export const AdaptiveDocuments = () => {
  const { t } = useTranslation();

  // State
  const [documents, setDocuments] = useState<AdaptiveDocument[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Upload options
  const [uploadOptions, setUploadOptions] = useState({
    language: 'auto',
    maxChunkSize: 1500,
    preserveTables: true,
    preserveSections: true,
  });

  // Detail data
  const [chunks, setChunks] = useState<ChunkListItem[]>([]);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [quality, setQuality] = useState<QualityResponse | null>(null);
  const [structure, setStructure] = useState<StructureAnalysisResponse | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // =============================================================================
  // Effects
  // =============================================================================

  // Load existing documents on mount
  useEffect(() => {
    const loadDocuments = async () => {
      try {
        setLoading(true);
        const docs = await adaptiveDocumentsApi.list();
        setDocuments(docs.map(doc => ({
          pdf_id: doc.pdf_id,
          name: `${doc.document_type}_${doc.pdf_id.slice(-8)}`,
          status: doc.status,
          chunks_count: doc.chunks_count,
          created_at: doc.created_at || new Date().toISOString(),
        })));
      } catch (err) {
        console.error('Failed to load documents:', err);
        // Don't show error - just start with empty list
      } finally {
        setLoading(false);
      }
    };
    loadDocuments();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // =============================================================================
  // Handlers
  // =============================================================================

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const response = await adaptiveDocumentsApi.process(file, {
        language: uploadOptions.language,
        maxChunkSize: uploadOptions.maxChunkSize,
        preserveTables: uploadOptions.preserveTables,
        preserveSections: uploadOptions.preserveSections,
      });

      // Add to documents list
      setDocuments(prev => [{
        pdf_id: response.pdf_id,
        name: file.name,
        status: response.status,
        chunks_count: response.estimated_chunks,
        created_at: new Date().toISOString(),
      }, ...prev]);

      // Start polling for status
      startPolling(response.task_id, response.pdf_id);

    } catch (err) {
      setError(t('common.adaptive.upload.error'));
      console.error('Upload error:', err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const startPolling = (taskId: string, pdfId: string) => {
    const poll = async () => {
      try {
        const status = await adaptiveDocumentsApi.getStatus(taskId);

        // Update document status
        setDocuments(prev => prev.map(doc =>
          doc.pdf_id === pdfId ? { ...doc, status: status.status } : doc
        ));

        if (status.status === 'completed' || status.status === 'failed') {
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    pollingRef.current = setInterval(poll, 2000);
    poll(); // Initial poll
  };

  const loadChunks = useCallback(async (pdfId: string) => {
    setLoading(true);
    try {
      const data = await adaptiveDocumentsApi.getChunks(pdfId);
      setChunks(data);
    } catch (err) {
      setError('Failed to load chunks');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadCoverage = useCallback(async (pdfId: string) => {
    setLoading(true);
    try {
      const data = await adaptiveDocumentsApi.getCoverage(pdfId);
      setCoverage(data);
    } catch (err) {
      setError('Failed to load coverage');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadQuality = useCallback(async (pdfId: string) => {
    setLoading(true);
    try {
      // Use refreshQuality to recalculate metrics with actual embeddings
      const data = await adaptiveDocumentsApi.refreshQuality(pdfId);
      setQuality(data);
    } catch (err) {
      // Fall back to cached quality if refresh fails
      try {
        const cached = await adaptiveDocumentsApi.getQuality(pdfId);
        setQuality(cached);
      } catch {
        setError('Failed to load quality metrics');
      }
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStructure = useCallback(async (pdfId: string) => {
    setLoading(true);
    try {
      const data = await adaptiveDocumentsApi.getStructure(pdfId);
      setStructure(data);
    } catch (err) {
      setError('Failed to load structure');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const response = await adaptiveDocumentsApi.search({
        query: searchQuery,
        pdf_id: selectedDoc || undefined,
        limit: 10,
      });
      setSearchResults(response.results);
    } catch (err) {
      setError('Search failed');
      console.error(err);
    } finally {
      setSearching(false);
    }
  };

  const handleDelete = async (pdfId: string) => {
    if (!confirm('Are you sure you want to delete this document?')) return;

    try {
      await adaptiveDocumentsApi.delete(pdfId);
      setDocuments(prev => prev.filter(d => d.pdf_id !== pdfId));
      if (selectedDoc === pdfId) {
        setSelectedDoc(null);
        setViewMode('list');
      }
    } catch (err) {
      setError('Failed to delete document');
      console.error(err);
    }
  };

  const selectDocument = (pdfId: string, mode: ViewMode) => {
    setSelectedDoc(pdfId);
    setViewMode(mode);

    switch (mode) {
      case 'chunks':
        loadChunks(pdfId);
        break;
      case 'coverage':
        loadCoverage(pdfId);
        break;
      case 'quality':
        loadQuality(pdfId);
        break;
      case 'structure':
        loadStructure(pdfId);
        break;
    }
  };

  // =============================================================================
  // Render Helpers
  // =============================================================================

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed': return 'badge-success';
      case 'failed': return 'badge-error';
      case 'pending': return 'badge-warning';
      default: return 'badge-info';
    }
  };

  const getChunkTypeBadgeClass = (type: ChunkType) => {
    switch (type) {
      case 'TEXT_CHUNK': return 'chunk-type-text';
      case 'TABLE_CHUNK': return 'chunk-type-table';
      case 'IMAGE_CHUNK': return 'chunk-type-image';
      case 'OCR_CHUNK': return 'chunk-type-ocr';
      default: return '';
    }
  };

  const formatPercentage = (value: number) => `${(value * 100).toFixed(1)}%`;

  // =============================================================================
  // Render
  // =============================================================================

  return (
    <div className="adaptive-documents">
      {/* Header */}
      <div className="adaptive-header">
        <div className="adaptive-header-left">
          <h2>{t('common.adaptive.title')}</h2>
          <p className="adaptive-description">{t('common.adaptive.description')}</p>
        </div>
        <div className="adaptive-header-actions">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            onChange={handleFileSelect}
            style={{ display: 'none' }}
          />
          <button
            className="btn-primary"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
          >
            {uploading ? t('common.adaptive.upload.processing') : t('common.adaptive.upload.title')}
          </button>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="adaptive-error">
          {error}
          <button onClick={() => setError(null)}>x</button>
        </div>
      )}

      {/* Upload Options */}
      <div className="adaptive-options">
        <div className="option-group">
          <label>{t('common.adaptive.options.language')}</label>
          <select
            value={uploadOptions.language}
            onChange={(e) => setUploadOptions({ ...uploadOptions, language: e.target.value })}
          >
            <option value="auto">{t('common.adaptive.options.languageAuto')}</option>
            <option value="en">English</option>
            <option value="ko">Korean</option>
            <option value="ja">Japanese</option>
          </select>
        </div>
        <div className="option-group">
          <label>{t('common.adaptive.options.maxChunkSize')}</label>
          <input
            type="number"
            value={uploadOptions.maxChunkSize}
            onChange={(e) => setUploadOptions({ ...uploadOptions, maxChunkSize: parseInt(e.target.value) })}
            min={200}
            max={4000}
          />
        </div>
        <div className="option-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={uploadOptions.preserveTables}
              onChange={(e) => setUploadOptions({ ...uploadOptions, preserveTables: e.target.checked })}
            />
            {t('common.adaptive.options.preserveTables')}
          </label>
        </div>
        <div className="option-group checkbox">
          <label>
            <input
              type="checkbox"
              checked={uploadOptions.preserveSections}
              onChange={(e) => setUploadOptions({ ...uploadOptions, preserveSections: e.target.checked })}
            />
            {t('common.adaptive.options.preserveSections')}
          </label>
        </div>
      </div>

      {/* Main Content */}
      <div className="adaptive-content">
        {/* Document List */}
        <div className="adaptive-sidebar">
          <h3>{t('common.adaptive.documents.title')}</h3>
          {documents.length === 0 ? (
            <div className="empty-state">
              <p>{t('common.adaptive.documents.empty')}</p>
              <p className="hint">{t('common.adaptive.documents.uploadFirst')}</p>
            </div>
          ) : (
            <ul className="document-list">
              {documents.map(doc => (
                <li
                  key={doc.pdf_id}
                  className={selectedDoc === doc.pdf_id ? 'selected' : ''}
                >
                  <div className="doc-info">
                    <span className="doc-name">{doc.name}</span>
                    <span className={`status-badge ${getStatusBadgeClass(doc.status)}`}>
                      {t(`common.adaptive.status.${doc.status}`)}
                    </span>
                  </div>
                  <div className="doc-meta">
                    <span>{doc.chunks_count} chunks</span>
                  </div>
                  <div className="doc-actions">
                    <button
                      className="btn-sm"
                      onClick={() => selectDocument(doc.pdf_id, 'chunks')}
                      disabled={doc.status !== 'completed'}
                    >
                      {t('common.adaptive.actions.viewChunks')}
                    </button>
                    <button
                      className="btn-sm"
                      onClick={() => selectDocument(doc.pdf_id, 'coverage')}
                      disabled={doc.status !== 'completed'}
                    >
                      {t('common.adaptive.actions.viewCoverage')}
                    </button>
                    <button
                      className="btn-sm"
                      onClick={() => selectDocument(doc.pdf_id, 'quality')}
                      disabled={doc.status !== 'completed'}
                    >
                      {t('common.adaptive.actions.viewQuality')}
                    </button>
                    <button
                      className="btn-sm"
                      onClick={() => selectDocument(doc.pdf_id, 'structure')}
                      disabled={doc.status !== 'completed'}
                    >
                      {t('common.adaptive.actions.viewStructure')}
                    </button>
                    <button
                      className="btn-sm btn-danger"
                      onClick={() => handleDelete(doc.pdf_id)}
                    >
                      {t('common.adaptive.actions.delete')}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Detail Panel */}
        <div className="adaptive-detail">
          {/* Search */}
          <div className="search-section">
            <h3>{t('common.adaptive.search.title')}</h3>
            <div className="search-bar">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t('common.adaptive.search.placeholder')}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              />
              <button onClick={handleSearch} disabled={searching}>
                {searching ? '...' : t('common.search')}
              </button>
            </div>
            {searchResults.length > 0 && (
              <div className="search-results">
                <h4>{t('common.adaptive.search.results')}: {searchResults.length}</h4>
                <ul>
                  {searchResults.map(result => (
                    <li key={result.chunk_id} className="search-result-item">
                      <div className="result-header">
                        <span className={`chunk-type ${getChunkTypeBadgeClass(result.chunk_type)}`}>
                          {t(`common.adaptive.chunks.types.${result.chunk_type}`)}
                        </span>
                        <span className="similarity">
                          {t('common.adaptive.search.similarity')}: {formatPercentage(result.similarity)}
                        </span>
                      </div>
                      <p className="result-content">{result.content.slice(0, 200)}...</p>
                      <div className="result-meta">
                        <span>{t('common.adaptive.chunks.pages')}: {result.page_start}-{result.page_end}</span>
                        {result.section_title && (
                          <span>{t('common.adaptive.chunks.section')}: {result.section_title}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Loading */}
          {loading && <div className="loading">{t('common.loading')}</div>}

          {/* Chunks View */}
          {viewMode === 'chunks' && !loading && (
            <div className="chunks-view">
              <h3>{t('common.adaptive.chunks.title')}</h3>
              {chunks.length === 0 ? (
                <p>{t('common.adaptive.chunks.noChunks')}</p>
              ) : (
                <ul className="chunks-list">
                  {chunks.map(chunk => (
                    <li key={chunk.chunk_id} className="chunk-item">
                      <div className="chunk-header">
                        <span className={`chunk-type ${getChunkTypeBadgeClass(chunk.chunk_type)}`}>
                          {t(`common.adaptive.chunks.types.${chunk.chunk_type}`)}
                        </span>
                        <span className={chunk.has_embedding ? 'embedded' : 'not-embedded'}>
                          {chunk.has_embedding ? t('common.adaptive.chunks.embedded') : t('common.adaptive.chunks.notEmbedded')}
                        </span>
                      </div>
                      <p className="chunk-preview">{chunk.content_preview}</p>
                      <div className="chunk-meta">
                        <span>{t('common.adaptive.chunks.pages')}: {chunk.page_start}-{chunk.page_end}</span>
                        <span>{chunk.content_length} chars</span>
                        {chunk.section_title && (
                          <span>{t('common.adaptive.chunks.section')}: {chunk.section_title}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Coverage View */}
          {viewMode === 'coverage' && !loading && coverage && (
            <div className="coverage-view">
              <h3>{t('common.adaptive.coverage.title')}</h3>
              <div className="coverage-grid">
                <div className="coverage-card overall">
                  <span className="label">{t('common.adaptive.coverage.overall')}</span>
                  <span className="value">{formatPercentage(coverage.overall_coverage)}</span>
                </div>
                <div className="coverage-card">
                  <span className="label">{t('common.adaptive.coverage.text')}</span>
                  <span className="value">{formatPercentage(coverage.text_coverage)}</span>
                </div>
                <div className="coverage-card">
                  <span className="label">{t('common.adaptive.coverage.table')}</span>
                  <span className="value">{formatPercentage(coverage.table_coverage)}</span>
                </div>
                <div className="coverage-card">
                  <span className="label">{t('common.adaptive.coverage.image')}</span>
                  <span className="value">{formatPercentage(coverage.image_coverage)}</span>
                </div>
                <div className="coverage-card">
                  <span className="label">{t('common.adaptive.coverage.ocr')}</span>
                  <span className="value">{formatPercentage(coverage.ocr_coverage)}</span>
                </div>
              </div>
              <div className="coverage-stats">
                <div className="stat">
                  <span className="label">{t('common.adaptive.coverage.totalChunks')}</span>
                  <span className="value">{coverage.total_chunks}</span>
                </div>
                <div className="stat">
                  <span className="label">{t('common.adaptive.coverage.embeddedChunks')}</span>
                  <span className="value">{coverage.embedded_chunks}</span>
                </div>
              </div>
            </div>
          )}

          {/* Quality View */}
          {viewMode === 'quality' && !loading && quality && (
            <div className="quality-view">
              <h3>{t('common.adaptive.quality.title')}</h3>
              <div className={`quality-level quality-${quality.quality_level}`}>
                {t(`common.adaptive.quality.levels.${quality.quality_level}`)}
              </div>
              <div className="quality-metrics">
                <div className="metric">
                  <span className="label">{t('common.adaptive.quality.topKRecall')}</span>
                  <span className="value">{formatPercentage(quality.top_k_recall)}</span>
                </div>
                <div className="metric">
                  <span className="label">{t('common.adaptive.quality.sectionPrecision')}</span>
                  <span className="value">{formatPercentage(quality.section_precision)}</span>
                </div>
                <div className="metric">
                  <span className="label">{t('common.adaptive.quality.avgSimilarity')}</span>
                  <span className="value">{formatPercentage(quality.avg_similarity)}</span>
                </div>
              </div>
              {quality.hallucination_detected && (
                <div className="warning-banner">
                  {t('common.adaptive.quality.hallucination')}
                </div>
              )}
              {quality.issues.length > 0 && (
                <div className="issues-section">
                  <h4>{t('common.adaptive.quality.issues')}</h4>
                  <ul>
                    {quality.issues.map((issue, idx) => (
                      <li key={idx}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
              {quality.recommendations.length > 0 && (
                <div className="recommendations-section">
                  <h4>{t('common.adaptive.quality.recommendations')}</h4>
                  <ul>
                    {quality.recommendations.map((rec, idx) => (
                      <li key={idx}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Structure View */}
          {viewMode === 'structure' && !loading && structure && (
            <div className="structure-view">
              <h3>{t('common.adaptive.structure.title')}</h3>
              <div className="structure-info">
                <div className="info-item">
                  <span className="label">{t('common.adaptive.structure.documentType')}</span>
                  <span className="value">{t(`common.adaptive.structure.types.${structure.document_type}`)}</span>
                </div>
                <div className="info-item">
                  <span className="label">{t('common.adaptive.structure.totalPages')}</span>
                  <span className="value">{structure.total_pages}</span>
                </div>
                <div className="info-item">
                  <span className="label">{t('common.adaptive.structure.totalSections')}</span>
                  <span className="value">{structure.total_sections}</span>
                </div>
                <div className="info-item">
                  <span className="label">{t('common.adaptive.structure.totalImages')}</span>
                  <span className="value">{structure.total_images}</span>
                </div>
                <div className="info-item">
                  <span className="label">{t('common.adaptive.structure.totalTables')}</span>
                  <span className="value">{structure.total_tables}</span>
                </div>
              </div>
              {structure.hierarchy.length > 0 && (
                <div className="hierarchy-section">
                  <h4>{t('common.adaptive.structure.hierarchy')}</h4>
                  <ul className="hierarchy-tree">
                    {structure.hierarchy.map(section => (
                      <li
                        key={section.id}
                        className={`hierarchy-item level-${section.level}`}
                        style={{ paddingLeft: `${section.level * 16}px` }}
                      >
                        <span className="section-id">{section.id}</span>
                        <span className="section-title">{section.title}</span>
                        <span className="section-pages">
                          ({section.page_start}-{section.page_end})
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AdaptiveDocuments;
