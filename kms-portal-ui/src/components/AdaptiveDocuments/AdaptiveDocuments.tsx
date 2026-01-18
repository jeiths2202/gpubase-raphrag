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
  FolderOpen,
  CheckSquare,
  Square,
  PlayCircle,
} from 'lucide-react';
import {
  adaptiveDocumentsApi,
  evaluateQuality,
  ChunkListItem,
  CoverageResponse,
  QualityResponse,
  StructureAnalysisResponse,
  SearchResultItem,
  ChunkType,
  PendingUploadItem,
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

interface EmbeddingProgress {
  filename: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  taskId?: string;
  pdfId?: string;
  progress?: number;
  error?: string;
}

// =============================================================================
// Main Component
// =============================================================================

export const AdaptiveDocuments = () => {
  const { t } = useTranslation();

  // State - Embedded documents
  const [documents, setDocuments] = useState<AdaptiveDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // State - Pending uploads
  const [pendingFiles, setPendingFiles] = useState<PendingUploadItem[]>([]);
  const [pendingLoading, setPendingLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedPendingFiles, setSelectedPendingFiles] = useState<Set<string>>(new Set());

  // State - Embedding process
  const [embedding, setEmbedding] = useState(false);
  const [embeddingProgress, setEmbeddingProgress] = useState<EmbeddingProgress[]>([]);
  const [showEmbedOptions, setShowEmbedOptions] = useState(false);

  // Filter state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Upload modal
  const [showUploadOptions, setShowUploadOptions] = useState(false);

  // Upload/Embed options
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

  // Quality evaluation state
  const [evaluatingQuality, setEvaluatingQuality] = useState<Set<string>>(new Set());

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [searching, setSearching] = useState(false);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<AdaptiveDocument | null>(null);
  const [deletePendingTarget, setDeletePendingTarget] = useState<string | null>(null);

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBatchDeleteConfirm, setShowBatchDeleteConfirm] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);

  // Refs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const pollingRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());
  const pollingFailuresRef = useRef<Map<string, number>>(new Map());

  // =============================================================================
  // Effects
  // =============================================================================

  // Load existing documents and pending files on mount
  useEffect(() => {
    loadDocuments();
    loadPendingFiles();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      pollingRef.current.forEach((interval) => clearInterval(interval));
      pollingRef.current.clear();
      pollingFailuresRef.current.clear();
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
        name: doc.document_name || `${doc.document_type}_${doc.pdf_id.slice(-8)}`,
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

  const loadPendingFiles = async () => {
    try {
      setPendingLoading(true);
      const response = await adaptiveDocumentsApi.listPending();
      setPendingFiles(response.files);
    } catch (err) {
      console.error('Failed to load pending files:', err);
    } finally {
      setPendingLoading(false);
    }
  };

  // Upload file to pending (without processing)
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Filter PDF files only
    const pdfFiles = Array.from(files).filter(file =>
      file.name.toLowerCase().endsWith('.pdf')
    );

    if (pdfFiles.length === 0) {
      setError(t('common.adaptive.upload.error') + ' - PDF only');
      return;
    }

    setUploading(true);
    setError(null);

    // Upload files to pending (without processing)
    for (const file of pdfFiles) {
      try {
        await adaptiveDocumentsApi.uploadOnly(file);
      } catch (err) {
        console.error(`Upload error for ${file.name}:`, err);
      }
    }

    setUploading(false);
    // Reload pending files and close upload modal
    await loadPendingFiles();
    setShowUploadOptions(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (folderInputRef.current) {
      folderInputRef.current.value = '';
    }
  };

  const handleFolderSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    // Filter PDF files only from the folder
    const pdfFiles = Array.from(files).filter(file =>
      file.name.toLowerCase().endsWith('.pdf')
    );

    if (pdfFiles.length === 0) {
      setError(t('common.adaptive.upload.noPdfInFolder'));
      return;
    }

    setUploading(true);
    setError(null);

    // Upload files to pending (without processing)
    for (const file of pdfFiles) {
      try {
        await adaptiveDocumentsApi.uploadOnly(file);
      } catch (err) {
        console.error(`Upload error for ${file.name}:`, err);
      }
    }

    setUploading(false);
    // Reload pending files and close upload modal
    await loadPendingFiles();
    setShowUploadOptions(false);
    if (folderInputRef.current) {
      folderInputRef.current.value = '';
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;

    try {
      await adaptiveDocumentsApi.delete(deleteTarget.pdf_id);
      setDocuments(prev => prev.filter(d => d.pdf_id !== deleteTarget.pdf_id));
      setSelectedIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(deleteTarget.pdf_id);
        return newSet;
      });
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

  // Multi-select handlers
  const toggleSelect = (pdfId: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(pdfId)) {
        newSet.delete(pdfId);
      } else {
        newSet.add(pdfId);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredDocuments.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredDocuments.map(doc => doc.pdf_id)));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;

    setBatchDeleting(true);
    try {
      const result = await adaptiveDocumentsApi.batchDelete(Array.from(selectedIds));

      // Remove successfully deleted documents from list
      setDocuments(prev => prev.filter(d => !result.results.success.includes(d.pdf_id)));
      setSelectedIds(new Set());
      setShowBatchDeleteConfirm(false);

      // Close detail view if selected doc was deleted
      if (selectedDoc && result.results.success.includes(selectedDoc.pdf_id)) {
        setSelectedDoc(null);
        setDetailView(null);
      }

      // Show error if some deletions failed
      if (result.failed > 0) {
        setError(`${result.failed} ${t('common.adaptive.batchDelete.partialError')}`);
      }
    } catch (err) {
      setError(t('common.adaptive.batchDelete.error'));
      console.error('Batch delete error:', err);
    } finally {
      setBatchDeleting(false);
    }
  };

  // Pending files handlers
  const togglePendingSelect = (filename: string) => {
    setSelectedPendingFiles(prev => {
      const newSet = new Set(prev);
      if (newSet.has(filename)) {
        newSet.delete(filename);
      } else {
        newSet.add(filename);
      }
      return newSet;
    });
  };

  const toggleSelectAllPending = () => {
    if (selectedPendingFiles.size === pendingFiles.length) {
      setSelectedPendingFiles(new Set());
    } else {
      setSelectedPendingFiles(new Set(pendingFiles.map(f => f.filename)));
    }
  };

  const handleDeletePending = async () => {
    if (!deletePendingTarget) return;

    try {
      await adaptiveDocumentsApi.deletePending(deletePendingTarget);
      setPendingFiles(prev => prev.filter(f => f.filename !== deletePendingTarget));
      setSelectedPendingFiles(prev => {
        const newSet = new Set(prev);
        newSet.delete(deletePendingTarget);
        return newSet;
      });
      setDeletePendingTarget(null);
    } catch (err) {
      setError(t('common.adaptive.actions.delete') + ' failed');
      console.error(err);
    }
  };

  // Start batch embedding
  const handleStartEmbedding = async () => {
    if (selectedPendingFiles.size === 0) return;

    setEmbedding(true);
    setShowEmbedOptions(false);

    // Initialize progress tracking
    const filenames = Array.from(selectedPendingFiles);
    setEmbeddingProgress(filenames.map(filename => ({
      filename,
      status: 'pending',
    })));

    try {
      const result = await adaptiveDocumentsApi.startBatchEmbed(filenames, {
        language: uploadOptions.language,
        maxChunkSize: uploadOptions.maxChunkSize,
        preserveTables: uploadOptions.preserveTables,
        preserveSections: uploadOptions.preserveSections,
      });

      // Update progress with task IDs
      setEmbeddingProgress(prev => prev.map(item => {
        const resultItem = result.results.find(r => r.filename === item.filename);
        if (resultItem) {
          return {
            ...item,
            status: resultItem.status === 'processing' ? 'processing' : 'failed',
            taskId: resultItem.task_id,
            pdfId: resultItem.pdf_id,
            error: resultItem.error,
          };
        }
        return item;
      }));

      // Start polling for each processing file
      for (const item of result.results) {
        if (item.status === 'processing' && item.task_id && item.pdf_id) {
          startEmbeddingPolling(item.task_id, item.pdf_id, item.filename);
        }
      }

      // Remove from pending list
      const processingFilenames = result.results
        .filter(r => r.status === 'processing')
        .map(r => r.filename);
      setPendingFiles(prev => prev.filter(f => !processingFilenames.includes(f.filename)));
      setSelectedPendingFiles(new Set());

    } catch (err) {
      setError(t('common.adaptive.embed.error'));
      console.error('Embedding error:', err);
      setEmbeddingProgress([]);
    }
  };

  const startEmbeddingPolling = (taskId: string, pdfId: string, filename: string) => {
    const pollKey = `embed_${pdfId}`;
    const MAX_FAILURES = 5; // Stop after 5 consecutive failures

    if (pollingRef.current.has(pollKey)) {
      clearInterval(pollingRef.current.get(pollKey));
    }

    // Reset failure counter
    pollingFailuresRef.current.set(pollKey, 0);

    const poll = async () => {
      try {
        const status = await adaptiveDocumentsApi.getStatus(taskId);

        // Reset failure counter on success
        pollingFailuresRef.current.set(pollKey, 0);

        // Update embedding progress
        setEmbeddingProgress(prev => prev.map(item =>
          item.filename === filename
            ? {
                ...item,
                status: status.status === 'completed' ? 'completed'
                      : status.status === 'failed' ? 'failed'
                      : 'processing',
                progress: status.progress,
              }
            : item
        ));

        if (status.status === 'completed' || status.status === 'failed') {
          const interval = pollingRef.current.get(pollKey);
          if (interval) {
            clearInterval(interval);
            pollingRef.current.delete(pollKey);
            pollingFailuresRef.current.delete(pollKey);
          }

          // If completed, add to documents list
          if (status.status === 'completed') {
            setDocuments(prev => [{
              pdf_id: pdfId,
              name: filename,
              status: 'completed',
              chunks_count: status.chunks_processed || 0,
              created_at: new Date().toISOString(),
            }, ...prev]);
          }

          // Check if all embedding tasks are done
          setEmbeddingProgress(prev => {
            const allDone = prev.every(item =>
              item.status === 'completed' || item.status === 'failed'
            );
            if (allDone) {
              setEmbedding(false);
            }
            return prev;
          });
        }
      } catch (err) {
        // Track consecutive failures
        const failures = (pollingFailuresRef.current.get(pollKey) || 0) + 1;
        pollingFailuresRef.current.set(pollKey, failures);

        console.warn(`Embedding polling error (${failures}/${MAX_FAILURES}):`, err);

        // Stop polling after too many consecutive failures
        if (failures >= MAX_FAILURES) {
          console.error(`Stopping polling for ${filename} after ${MAX_FAILURES} failures`);
          const interval = pollingRef.current.get(pollKey);
          if (interval) {
            clearInterval(interval);
            pollingRef.current.delete(pollKey);
            pollingFailuresRef.current.delete(pollKey);
          }

          // Mark as failed
          setEmbeddingProgress(prev => prev.map(item =>
            item.filename === filename
              ? { ...item, status: 'failed', error: 'Connection timeout' }
              : item
          ));

          // Check if all tasks done
          setEmbeddingProgress(prev => {
            const allDone = prev.every(item =>
              item.status === 'completed' || item.status === 'failed'
            );
            if (allDone) {
              setEmbedding(false);
            }
            return prev;
          });
        }
        // Otherwise continue polling (transient error)
      }
    };

    const interval = setInterval(poll, 2000);
    pollingRef.current.set(pollKey, interval);
    poll();
  };

  // Handle quality evaluation on-demand
  const handleEvaluateQuality = async (doc: AdaptiveDocument) => {
    const pdfId = doc.pdf_id;

    // Mark as evaluating
    setEvaluatingQuality(prev => new Set(prev).add(pdfId));

    try {
      const result = await evaluateQuality(pdfId);

      if (result.status === 'completed') {
        // Show success message or update UI
        console.log(`Quality evaluation completed for ${pdfId}:`, result);
        // Optionally refresh the document list or show quality metrics
        if (result.quality_metrics) {
          alert(
            `${t('common.adaptive.qualityEvaluation.completed')}\n\n` +
            `Quality Level: ${result.quality_metrics.quality_level}\n` +
            `Top-K Recall: ${(result.quality_metrics.top_k_recall * 100).toFixed(1)}%\n` +
            `Avg Similarity: ${(result.quality_metrics.avg_similarity * 100).toFixed(1)}%`
          );
        }
      } else if (result.status === 'skipped') {
        alert(result.message);
      } else {
        setError(result.message);
      }
    } catch (err) {
      console.error('Quality evaluation failed:', err);
      setError(t('common.adaptive.qualityEvaluation.failed'));
    } finally {
      // Remove from evaluating set
      setEvaluatingQuality(prev => {
        const newSet = new Set(prev);
        newSet.delete(pdfId);
        return newSet;
      });
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
            {selectedIds.size > 0 && (
              <button
                className="btn btn--danger"
                onClick={() => setShowBatchDeleteConfirm(true)}
                disabled={batchDeleting}
              >
                <Trash2 size={16} />
                {t('common.adaptive.batchDelete.button')} ({selectedIds.size})
              </button>
            )}
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

        {/* Semantic Search Section - only show when documents exist */}
        {documents.length > 0 && (
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
        )}

        {/* Embedding Progress */}
        {embeddingProgress.length > 0 && (
          <div className="adaptive-embedding-progress">
            <div className="embedding-progress-header">
              <h4>{t('common.adaptive.embed.progressTitle')}</h4>
              {!embedding && (
                <button
                  className="btn btn--sm"
                  onClick={() => setEmbeddingProgress([])}
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <div className="embedding-progress-list">
              {embeddingProgress.map(item => (
                <div key={item.filename} className={`embedding-progress-item embedding-progress-item--${item.status}`}>
                  <div className="progress-file-info">
                    <FileText size={16} />
                    <span className="progress-filename">{item.filename}</span>
                  </div>
                  <div className="progress-status">
                    {item.status === 'pending' && (
                      <><Clock size={14} /> {t('common.adaptive.embed.statusPending')}</>
                    )}
                    {item.status === 'processing' && (
                      <><Loader2 size={14} className="spinning" /> {t('common.adaptive.embed.statusProcessing')} {item.progress !== undefined && `(${item.progress}%)`}</>
                    )}
                    {item.status === 'completed' && (
                      <><CheckCircle size={14} /> {t('common.adaptive.embed.statusCompleted')}</>
                    )}
                    {item.status === 'failed' && (
                      <><XCircle size={14} /> {t('common.adaptive.embed.statusFailed')}: {item.error}</>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Pending Uploads Section */}
        {(pendingFiles.length > 0 || pendingLoading) && (
          <div className="adaptive-pending-section">
            <div className="pending-header">
              <h4>{t('common.adaptive.pending.title')} ({pendingFiles.length})</h4>
              <div className="pending-actions">
                {selectedPendingFiles.size > 0 && (
                  <>
                    <button
                      className="btn btn--primary"
                      onClick={() => setShowEmbedOptions(true)}
                      disabled={embedding}
                    >
                      <Layers size={16} />
                      {t('common.adaptive.embed.button')} ({selectedPendingFiles.size})
                    </button>
                    <button
                      className="btn btn--danger btn--sm"
                      onClick={() => {
                        // Delete all selected pending files
                        selectedPendingFiles.forEach(async (filename) => {
                          try {
                            await adaptiveDocumentsApi.deletePending(filename);
                          } catch (err) {
                            console.error(`Failed to delete ${filename}:`, err);
                          }
                        });
                        setPendingFiles(prev => prev.filter(f => !selectedPendingFiles.has(f.filename)));
                        setSelectedPendingFiles(new Set());
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
                <button
                  className="btn btn--secondary btn--sm"
                  onClick={loadPendingFiles}
                  disabled={pendingLoading}
                >
                  <RefreshCw size={14} className={pendingLoading ? 'spinning' : ''} />
                </button>
              </div>
            </div>
            {pendingLoading ? (
              <div className="pending-loading">
                <Loader2 size={20} className="spinning" />
              </div>
            ) : (
              <div className="pending-table-container">
                <table className="pending-table">
                  <thead>
                    <tr>
                      <th className="checkbox-column">
                        <button
                          className="checkbox-btn"
                          onClick={toggleSelectAllPending}
                        >
                          {selectedPendingFiles.size === pendingFiles.length && pendingFiles.length > 0 ? (
                            <CheckSquare size={16} />
                          ) : (
                            <Square size={16} />
                          )}
                        </button>
                      </th>
                      <th>{t('common.adaptive.pending.filename')}</th>
                      <th>{t('common.adaptive.pending.size')}</th>
                      <th>{t('common.adaptive.pending.uploadedAt')}</th>
                      <th>{t('common.adaptive.table.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingFiles.map((file) => (
                      <tr key={file.filename} className={selectedPendingFiles.has(file.filename) ? 'selected' : ''}>
                        <td className="checkbox-column">
                          <button
                            className="checkbox-btn"
                            onClick={() => togglePendingSelect(file.filename)}
                          >
                            {selectedPendingFiles.has(file.filename) ? (
                              <CheckSquare size={16} className="checked" />
                            ) : (
                              <Square size={16} />
                            )}
                          </button>
                        </td>
                        <td>
                          <div className="pending-file-name">
                            <FileText size={16} className="text-red-500" />
                            <span>{file.filename}</span>
                          </div>
                        </td>
                        <td>{(file.size / 1024 / 1024).toFixed(2)} MB</td>
                        <td>{formatDate(file.uploaded_at)}</td>
                        <td>
                          <button
                            className="doc-action-btn doc-action-btn--delete"
                            title={t('common.delete')}
                            onClick={() => setDeletePendingTarget(file.filename)}
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

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
                  <th className="checkbox-column">
                    <button
                      className="checkbox-btn"
                      onClick={toggleSelectAll}
                      title={selectedIds.size === filteredDocuments.length ? t('common.externalConnectors.deselectAll') : t('common.externalConnectors.selectAll')}
                    >
                      {selectedIds.size === filteredDocuments.length && filteredDocuments.length > 0 ? (
                        <CheckSquare size={18} />
                      ) : (
                        <Square size={18} />
                      )}
                    </button>
                  </th>
                  <th>{t('common.adaptive.table.document')}</th>
                  <th>{t('common.adaptive.table.status')}</th>
                  <th>{t('common.adaptive.table.chunks')}</th>
                  <th>{t('common.adaptive.table.created')}</th>
                  <th>{t('common.adaptive.table.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredDocuments.map((doc) => (
                  <tr key={doc.pdf_id} className={selectedIds.has(doc.pdf_id) ? 'selected' : ''}>
                    <td className="checkbox-column">
                      <button
                        className="checkbox-btn"
                        onClick={() => toggleSelect(doc.pdf_id)}
                      >
                        {selectedIds.has(doc.pdf_id) ? (
                          <CheckSquare size={18} className="checked" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>
                    </td>
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
                          className="doc-action-btn doc-action-btn--evaluate"
                          title={t('common.adaptive.actions.evaluateQuality')}
                          onClick={() => handleEvaluateQuality(doc)}
                          disabled={doc.status !== 'completed' || evaluatingQuality.has(doc.pdf_id)}
                        >
                          {evaluatingQuality.has(doc.pdf_id) ? (
                            <Loader2 size={16} className="spinning" />
                          ) : (
                            <PlayCircle size={16} />
                          )}
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
              <div className="upload-buttons">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  multiple
                  onChange={handleFileSelect}
                  style={{ display: 'none' }}
                />
                <input
                  ref={folderInputRef}
                  type="file"
                  {...{ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>}
                  multiple
                  onChange={handleFolderSelect}
                  style={{ display: 'none' }}
                />
                {uploading ? (
                  <div className="upload-dropzone uploading">
                    <Loader2 size={32} className="spinning" />
                    <p>{t('common.adaptive.upload.processing')}</p>
                  </div>
                ) : (
                  <div className="upload-options-row">
                    <div className="upload-dropzone" onClick={() => fileInputRef.current?.click()}>
                      <Upload size={32} />
                      <p>{t('common.adaptive.upload.dropzone')}</p>
                    </div>
                    <div className="upload-dropzone folder" onClick={() => folderInputRef.current?.click()}>
                      <FolderOpen size={32} />
                      <p>{t('common.adaptive.upload.selectFolder')}</p>
                    </div>
                  </div>
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
              <p>{t('common.adaptive.deleteConfirm.single')} <strong>{deleteTarget.name}</strong>?</p>
              <p className="delete-warning">{t('common.adaptive.deleteConfirm.warning')}</p>
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

      {/* Batch Delete Confirm Modal */}
      {showBatchDeleteConfirm && (
        <div className="adaptive-modal-overlay" onClick={() => setShowBatchDeleteConfirm(false)}>
          <div className="adaptive-modal adaptive-modal--confirm" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>{t('common.adaptive.batchDelete.title')}</h3>
              <button onClick={() => setShowBatchDeleteConfirm(false)}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              <p>{t('common.adaptive.batchDelete.confirmMessage', { count: selectedIds.size })}</p>
              <p className="delete-warning">{t('common.adaptive.deleteConfirm.warning')}</p>
              <div className="modal-actions">
                <button
                  className="btn btn--secondary"
                  onClick={() => setShowBatchDeleteConfirm(false)}
                  disabled={batchDeleting}
                >
                  {t('common.cancel')}
                </button>
                <button
                  className="btn btn--danger"
                  onClick={handleBatchDelete}
                  disabled={batchDeleting}
                >
                  {batchDeleting ? (
                    <>
                      <Loader2 size={16} className="spinning" />
                      {t('common.adaptive.batchDelete.deleting')}
                    </>
                  ) : (
                    t('common.adaptive.batchDelete.confirm')
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Embed Options Modal */}
      {showEmbedOptions && (
        <div className="adaptive-modal-overlay" onClick={() => setShowEmbedOptions(false)}>
          <div className="adaptive-modal" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>{t('common.adaptive.embed.optionsTitle')}</h3>
              <button onClick={() => setShowEmbedOptions(false)}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              <p className="embed-info">
                {t('common.adaptive.embed.selectedFiles', { count: selectedPendingFiles.size })}
              </p>
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
              <div className="modal-actions">
                <button
                  className="btn btn--secondary"
                  onClick={() => setShowEmbedOptions(false)}
                >
                  {t('common.cancel')}
                </button>
                <button
                  className="btn btn--primary"
                  onClick={handleStartEmbedding}
                  disabled={embedding}
                >
                  {embedding ? (
                    <>
                      <Loader2 size={16} className="spinning" />
                      {t('common.adaptive.embed.processing')}
                    </>
                  ) : (
                    <>
                      <Layers size={16} />
                      {t('common.adaptive.embed.start')}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Pending Confirm Modal */}
      {deletePendingTarget && (
        <div className="adaptive-modal-overlay" onClick={() => setDeletePendingTarget(null)}>
          <div className="adaptive-modal adaptive-modal--confirm" onClick={(e) => e.stopPropagation()}>
            <div className="adaptive-modal-header">
              <h3>{t('common.delete')}</h3>
              <button onClick={() => setDeletePendingTarget(null)}><X size={20} /></button>
            </div>
            <div className="adaptive-modal-content">
              <p>{t('common.adaptive.pending.deleteConfirm')} <strong>{deletePendingTarget}</strong>?</p>
              <div className="modal-actions">
                <button className="btn btn--secondary" onClick={() => setDeletePendingTarget(null)}>
                  {t('common.cancel')}
                </button>
                <button className="btn btn--danger" onClick={handleDeletePending}>
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
