/**
 * AdaptiveDocuments Component
 *
 * Component for managing adaptive PDF embedding with structure-preserving chunking.
 * Redesigned to match DocumentsTab table structure with i18n support.
 */

import { useState, useEffect, useRef } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  Search,
  RefreshCw,
  Upload,
  Loader2,
  FileText,
  Trash2,
  Eye,
  CheckCircle,
  Clock,
  XCircle,
  AlertCircle,
  X,
  BarChart3,
  Layers,
  GitBranch,
} from 'lucide-react';
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
  document_type?: string;
}

type DetailViewType = 'chunks' | 'coverage' | 'quality' | 'structure' | null;

// =============================================================================
// Main Component
// =============================================================================

export const AdaptiveDocuments = () => {
  const { t } = useTranslation();

  // State
  const [documents, setDocuments] = useState<AdaptiveDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Upload options
  const [showUploadOptions, setShowUploadOptions] = useState(false);
  const [uploadOptions, setUploadOptions] = useState({
    language: 'auto',
    maxChunkSize: 1500,
    preserveTables: true,
    preserveSections: true,
  });

  // Detail modal state
  const [selectedDoc, setSelectedDoc] = useState<AdaptiveDocument | null>(null);
  const [detailView, setDetailView] = useState<DetailViewType>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Detail data
  const [chunks, setChunks] = useState<ChunkListItem[]>([]);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [quality, setQuality] = useState<QualityResponse | null>(null);
  const [structure, setStructure] = useState<StructureAnalysisResponse | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<AdaptiveDocument | null>(null);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // =============================================================================
  // Effects
  // =============================================================================

  // Load existing documents on mount
  useEffect(() => {
    loadDocuments();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      pollingRef.current.forEach((interval) => clearInterval(interval));
      pollingRef.current.clear();
    };
  }, []);

  // =============================================================================
  // Handlers
  // =============================================================================

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
        document_type: doc.document_type,
      })));
    } catch (err) {
      console.error('Failed to load documents:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError(t('common.adaptive.upload.error') + ' - PDF only');
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
      const newDoc: AdaptiveDocument = {
        pdf_id: response.pdf_id,
        name: file.name,
        status: response.status,
        chunks_count: response.estimated_chunks,
        created_at: new Date().toISOString(),
      };
      setDocuments(prev => [newDoc, ...prev]);

      // Start polling for status
      startPolling(response.task_id, response.pdf_id);
      setShowUploadOptions(false);

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
    // Clear existing polling for this PDF
    if (pollingRef.current.has(pdfId)) {
      clearInterval(pollingRef.current.get(pdfId));
    }

    const poll = async () => {
      try {
        const status = await adaptiveDocumentsApi.getStatus(taskId);

        // Update document status
        setDocuments(prev => prev.map(doc =>
          doc.pdf_id === pdfId ? { ...doc, status: status.status, chunks_count: status.chunks_processed || doc.chunks_count } : doc
        ));

        if (status.status === 'completed' || status.status === 'failed') {
          const interval = pollingRef.current.get(pdfId);
          if (interval) {
            clearInterval(interval);
            pollingRef.current.delete(pdfId);
          }
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    };

    const interval = setInterval(poll, 2000);
    pollingRef.current.set(pdfId, interval);
    poll(); // Initial poll
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;

    try {
      await adaptiveDocumentsApi.delete(deleteTarget.pdf_id);
      setDocuments(prev => prev.filter(d => d.pdf_id !== deleteTarget.pdf_id));
      setDeleteTarget(null);
      if (selectedDoc?.pdf_id === deleteTarget.pdf_id) {
        setSelectedDoc(null);
        setDetailView(null);
      }
    } catch (err) {
      setError(t('common.adaptive.actions.delete') + ' failed');
      console.error(err);
    }
  };

  const openDetailView = async (doc: AdaptiveDocument, view: DetailViewType) => {
    setSelectedDoc(doc);
    setDetailView(view);
    setDetailLoading(true);

    try {
      switch (view) {
        case 'chunks':
          const chunksData = await adaptiveDocumentsApi.getChunks(doc.pdf_id);
          setChunks(chunksData);
          break;
        case 'coverage':
          const coverageData = await adaptiveDocumentsApi.getCoverage(doc.pdf_id);
          setCoverage(coverageData);
          break;
        case 'quality':
          try {
            const qualityData = await adaptiveDocumentsApi.refreshQuality(doc.pdf_id);
            setQuality(qualityData);
          } catch {
            const cached = await adaptiveDocumentsApi.getQuality(doc.pdf_id);
            setQuality(cached);
          }
          break;
        case 'structure':
          const structureData = await adaptiveDocumentsApi.getStructure(doc.pdf_id);
          setStructure(structureData);
          break;
      }
    } catch (err) {
      setError('Failed to load details');
      console.error(err);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetailView = () => {
    setSelectedDoc(null);
    setDetailView(null);
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;

    setSearching(true);
    try {
      const response = await adaptiveDocumentsApi.search({
        query: searchQuery,
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

  // =============================================================================
  // Render Helpers
  // =============================================================================

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="adaptive-status-badge adaptive-status-badge--completed">
            <CheckCircle size={12} /> {t('common.adaptive.status.completed')}
          </span>
        );
      case 'pending':
        return (
          <span className="adaptive-status-badge adaptive-status-badge--pending">
            <Clock size={12} /> {t('common.adaptive.status.pending')}
          </span>
        );
      case 'analyzing':
      case 'chunking':
      case 'embedding':
      case 'validating':
        return (
          <span className="adaptive-status-badge adaptive-status-badge--processing">
            <Loader2 size={12} className="spinning" /> {t(`common.adaptive.status.${status}`)}
          </span>
        );
      case 'failed':
        return (
          <span className="adaptive-status-badge adaptive-status-badge--failed">
            <XCircle size={12} /> {t('common.adaptive.status.failed')}
          </span>
        );
      default:
        return (
          <span className="adaptive-status-badge">
            <AlertCircle size={12} /> {status}
          </span>
        );
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatPercentage = (value: number) => `${(value * 100).toFixed(1)}%`;

  const getChunkTypeBadgeClass = (type: ChunkType) => {
    switch (type) {
      case 'TEXT_CHUNK': return 'chunk-type-text';
      case 'TABLE_CHUNK': return 'chunk-type-table';
      case 'IMAGE_CHUNK': return 'chunk-type-image';
      case 'OCR_CHUNK': return 'chunk-type-ocr';
      default: return '';
    }
  };

  // Filter documents
  const filteredDocuments = documents.filter(doc => {
    const matchesSearch = !search || doc.name.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = !statusFilter || doc.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // =============================================================================
  // Render
  // =============================================================================

  return (
    <div className="adaptive-documents-tab">
      {/* Header */}
      <div className="adaptive-list-section">
        <div className="adaptive-list-header">
          <div className="adaptive-search-group">
            <div className="adaptive-search">
              <Search size={16} />
              <input
                type="text"
                placeholder={t('common.adaptive.search.placeholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              className="adaptive-filter-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">{t('common.adaptive.table.allStatus')}</option>
              <option value="completed">{t('common.adaptive.status.completed')}</option>
              <option value="pending">{t('common.adaptive.status.pending')}</option>
              <option value="analyzing">{t('common.adaptive.status.analyzing')}</option>
              <option value="failed">{t('common.adaptive.status.failed')}</option>
            </select>
          </div>
          <div className="adaptive-header-actions">
            <button className="btn btn--secondary" onClick={loadDocuments} disabled={loading}>
              <RefreshCw size={16} className={loading ? 'spinning' : ''} />
              {t('common.refresh')}
            </button>
            <button
              className="btn btn--primary"
              onClick={() => setShowUploadOptions(true)}
              disabled={uploading}
            >
              <Upload size={16} />
              {t('common.adaptive.table.uploadPdf')}
            </button>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="adaptive-error-banner">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)}><X size={14} /></button>
          </div>
        )}

        {/* Search Section */}
        <div className="adaptive-search-section">
          <div className="adaptive-search-bar">
            <Search size={16} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('common.adaptive.search.placeholder')}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button onClick={handleSearch} disabled={searching} className="btn btn--sm">
              {searching ? <Loader2 size={14} className="spinning" /> : t('common.search')}
            </button>
          </div>
          {searchResults.length > 0 && (
            <div className="adaptive-search-results">
              <div className="search-results-header">
                <span>{t('common.adaptive.search.results')}: {searchResults.length}</span>
                <button onClick={() => setSearchResults([])}><X size={14} /></button>
              </div>
              <ul>
                {searchResults.map(result => (
                  <li key={result.chunk_id} className="search-result-item">
                    <div className="result-header">
                      <span className={`chunk-type-badge ${getChunkTypeBadgeClass(result.chunk_type)}`}>
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

        {/* Documents Table */}
        {loading ? (
          <div className="adaptive-loading">
            <Loader2 size={32} className="spinning" />
            <span>{t('common.loading')}</span>
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="adaptive-empty">
            <FileText size={48} strokeWidth={1} />
            <h3>{t('common.adaptive.documents.empty')}</h3>
            <p>{t('common.adaptive.documents.uploadFirst')}</p>
            <button className="btn btn--primary" onClick={() => setShowUploadOptions(true)}>
              <Upload size={16} />
              {t('common.adaptive.table.uploadPdf')}
            </button>
          </div>
        ) : (
          <div className="adaptive-table-container">
            <table className="adaptive-table">
              <thead>
                <tr>
                  <th>{t('common.adaptive.table.document')}</th>
                  <th>{t('common.adaptive.table.status')}</th>
                  <th>{t('common.adaptive.table.chunks')}</th>
                  <th>{t('common.adaptive.table.created')}</th>
                  <th>{t('common.adaptive.table.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((doc) => (
                  <tr key={doc.pdf_id}>
                    <td>
                      <div className="doc-name-cell">
                        <FileText size={18} className="text-red-500" />
                        <div className="doc-name-info">
                          <span className="doc-name">{doc.name}</span>
                          {doc.document_type && (
                            <span className="doc-type">{doc.document_type}</span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>{getStatusBadge(doc.status)}</td>
                    <td>{doc.chunks_count}</td>
                    <td>{formatDate(doc.created_at)}</td>
                    <td>
                      <div className="doc-actions">
                        <button
                          className="doc-action-btn"
                          title={t('common.adaptive.actions.viewChunks')}
                          onClick={() => openDetailView(doc, 'chunks')}
                          disabled={doc.status !== 'completed'}
                        >
                          <Layers size={16} />
                        </button>
                        <button
                          className="doc-action-btn"
                          title={t('common.adaptive.actions.viewCoverage')}
                          onClick={() => openDetailView(doc, 'coverage')}
                          disabled={doc.status !== 'completed'}
                        >
                          <BarChart3 size={16} />
                        </button>
                        <button
                          className="doc-action-btn"
                          title={t('common.adaptive.actions.viewQuality')}
                          onClick={() => openDetailView(doc, 'quality')}
                          disabled={doc.status !== 'completed'}
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          className="doc-action-btn"
                          title={t('common.adaptive.actions.viewStructure')}
                          onClick={() => openDetailView(doc, 'structure')}
                          disabled={doc.status !== 'completed'}
                        >
                          <GitBranch size={16} />
                        </button>
                        <button
                          className="doc-action-btn doc-action-btn--delete"
                          title={t('common.adaptive.actions.delete')}
                          onClick={() => setDeleteTarget(doc)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upload Modal */}
      {showUploadOptions && (
        <div className="adaptive-modal-overlay" onClick={() => setShowUploadOptions(false)}>
          <div className="adaptive-modal" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>{t('common.adaptive.upload.title')}</h3>
              <button onClick={() => setShowUploadOptions(false)}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              <div className="adaptive-options-grid">
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
              <div className="upload-dropzone" onClick={() => fileInputRef.current?.click()}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />
                {uploading ? (
                  <>
                    <Loader2 size={32} className="spinning" />
                    <p>{t('common.adaptive.upload.processing')}</p>
                  </>
                ) : (
                  <>
                    <Upload size={32} />
                    <p>{t('common.adaptive.upload.dropzone')}</p>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {detailView && selectedDoc && (
        <div className="adaptive-modal-overlay" onClick={closeDetailView}>
          <div className="adaptive-modal adaptive-modal--large" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>
                {detailView === 'chunks' && t('common.adaptive.chunks.title')}
                {detailView === 'coverage' && t('common.adaptive.coverage.title')}
                {detailView === 'quality' && t('common.adaptive.quality.title')}
                {detailView === 'structure' && t('common.adaptive.structure.title')}
                <span className="modal-doc-name"> - {selectedDoc.name}</span>
              </h3>
              <button onClick={closeDetailView}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              {detailLoading ? (
                <div className="adaptive-loading">
                  <Loader2 size={32} className="spinning" />
                  <span>{t('common.loading')}</span>
                </div>
              ) : (
                <>
                  {/* Chunks View */}
                  {detailView === 'chunks' && (
                    <div className="detail-chunks">
                      {chunks.length === 0 ? (
                        <p>{t('common.adaptive.chunks.noChunks')}</p>
                      ) : (
                        <ul className="chunks-list">
                          {chunks.map(chunk => (
                            <li key={chunk.chunk_id} className="chunk-item">
                              <div className="chunk-header">
                                <span className={`chunk-type-badge ${getChunkTypeBadgeClass(chunk.chunk_type)}`}>
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
                  {detailView === 'coverage' && coverage && (
                    <div className="detail-coverage">
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
                  {detailView === 'quality' && quality && (
                    <div className="detail-quality">
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
                  {detailView === 'structure' && structure && (
                    <div className="detail-structure">
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
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {deleteTarget && (
        <div className="adaptive-modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="adaptive-modal adaptive-modal--confirm" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>{t('common.delete')}</h3>
              <button onClick={() => setDeleteTarget(null)}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              <p>Are you sure you want to delete <strong>{deleteTarget.name}</strong>?</p>
              <div className="modal-actions">
                <button className="btn btn--secondary" onClick={() => setDeleteTarget(null)}>
                  {t('common.cancel')}
                </button>
                <button className="btn btn--danger" onClick={handleDelete}>
                  {t('common.delete')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdaptiveDocuments;
