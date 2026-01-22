/**
 * WebPages Component
 *
 * Component for managing web page sources for RAG knowledge base.
 * Handles URL input, processing status, and content viewing.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  Search,
  RefreshCw,
  Plus,
  Loader2,
  Globe,
  Trash2,
  Eye,
  CheckCircle,
  Clock,
  XCircle,
  AlertCircle,
  X,
  Link2,
  Image,
  CheckSquare,
  Square,
  ExternalLink,
} from 'lucide-react';
import {
  webPagesApi,
  WebSourceListItem,
  WebSourceStatus,
  ContentResponse,
  LinksResponse,
  ImagesResponse,
} from '../../api';
import './WebPages.css';

// =============================================================================
// Types
// =============================================================================

type DetailViewType = 'content' | 'links' | 'images' | null;

// =============================================================================
// Main Component
// =============================================================================

export const WebPages = () => {
  const { t } = useTranslation();

  // State - Web sources
  const [webSources, setWebSources] = useState<WebSourceListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);

  // Filter state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Add URL modal
  const [showAddModal, setShowAddModal] = useState(false);
  const [newUrl, setNewUrl] = useState('');
  const [newTags, setNewTags] = useState('');
  const [bulkUrls, setBulkUrls] = useState('');
  const [isBulkMode, setIsBulkMode] = useState(false);
  const [adding, setAdding] = useState(false);

  // Detail modal state
  const [selectedSource, setSelectedSource] = useState<WebSourceListItem | null>(null);
  const [detailView, setDetailView] = useState<DetailViewType>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState<ContentResponse | LinksResponse | ImagesResponse | null>(null);

  // Delete confirm
  const [deleteTarget, setDeleteTarget] = useState<WebSourceListItem | null>(null);

  // Multi-select state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBatchDeleteConfirm, setShowBatchDeleteConfirm] = useState(false);
  const [batchDeleting, setBatchDeleting] = useState(false);

  // Polling for processing items
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // =============================================================================
  // Effects
  // =============================================================================

  useEffect(() => {
    loadWebSources();
  }, [page, statusFilter]);

  // Poll for processing items
  useEffect(() => {
    const hasProcessing = webSources.some(
      (s) =>
        s.status === 'pending' ||
        s.status === 'fetching' ||
        s.status === 'extracting' ||
        s.status === 'chunking' ||
        s.status === 'embedding'
    );

    if (hasProcessing && !pollingRef.current) {
      pollingRef.current = setInterval(() => {
        loadWebSources(true);
      }, 3000);
    } else if (!hasProcessing && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [webSources]);

  // =============================================================================
  // Handlers
  // =============================================================================

  const loadWebSources = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const response = await webPagesApi.list({
        status: statusFilter as WebSourceStatus | undefined,
        page,
        limit,
      });
      setWebSources(response.data.web_sources);
      setTotal(response.data.total);
      setError(null);
    } catch (err) {
      console.error('Failed to load web sources:', err);
      if (!silent) setError(t('common.webPages.errors.loadFailed'));
    } finally {
      if (!silent) setLoading(false);
    }
  }, [page, statusFilter, limit, t]);

  const handleAddUrl = async () => {
    if (isBulkMode) {
      const urls = bulkUrls
        .split('\n')
        .map((u) => u.trim())
        .filter((u) => u && u.startsWith('http'));

      if (urls.length === 0) {
        setError(t('common.webPages.errors.invalidUrl'));
        return;
      }

      setAdding(true);
      try {
        const tags = newTags
          .split(',')
          .map((t) => t.trim())
          .filter((t) => t);
        await webPagesApi.createBulk({ urls, tags: tags.length > 0 ? tags : undefined });
        setShowAddModal(false);
        setBulkUrls('');
        setNewTags('');
        loadWebSources();
      } catch (err) {
        console.error('Failed to add URLs:', err);
        setError(t('common.webPages.errors.addFailed'));
      } finally {
        setAdding(false);
      }
    } else {
      if (!newUrl.trim() || !newUrl.startsWith('http')) {
        setError(t('common.webPages.errors.invalidUrl'));
        return;
      }

      setAdding(true);
      try {
        const tags = newTags
          .split(',')
          .map((t) => t.trim())
          .filter((t) => t);
        await webPagesApi.create({
          url: newUrl.trim(),
          tags: tags.length > 0 ? tags : undefined,
        });
        setShowAddModal(false);
        setNewUrl('');
        setNewTags('');
        loadWebSources();
      } catch (err) {
        console.error('Failed to add URL:', err);
        setError(t('common.webPages.errors.addFailed'));
      } finally {
        setAdding(false);
      }
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;

    try {
      await webPagesApi.delete(deleteTarget.id);
      setWebSources((prev) => prev.filter((s) => s.id !== deleteTarget.id));
      setSelectedIds((prev) => {
        const newSet = new Set(prev);
        newSet.delete(deleteTarget.id);
        return newSet;
      });
      setDeleteTarget(null);
      if (selectedSource?.id === deleteTarget.id) {
        setSelectedSource(null);
        setDetailView(null);
      }
    } catch (err) {
      setError(t('common.webPages.errors.deleteFailed'));
      console.error(err);
    }
  };

  const handleRefresh = async (id: string) => {
    try {
      await webPagesApi.refresh(id, true);
      loadWebSources();
    } catch (err) {
      setError(t('common.webPages.errors.refreshFailed'));
      console.error(err);
    }
  };

  // Multi-select handlers
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredSources.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredSources.map((s) => s.id)));
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;

    setBatchDeleting(true);
    try {
      const deletePromises = Array.from(selectedIds).map((id) =>
        webPagesApi.delete(id).catch((err) => {
          console.error(`Failed to delete ${id}:`, err);
          return null;
        })
      );
      await Promise.all(deletePromises);

      setWebSources((prev) => prev.filter((s) => !selectedIds.has(s.id)));
      setSelectedIds(new Set());
      setShowBatchDeleteConfirm(false);

      if (selectedSource && selectedIds.has(selectedSource.id)) {
        setSelectedSource(null);
        setDetailView(null);
      }
    } catch (err) {
      setError(t('common.webPages.errors.deleteFailed'));
      console.error('Batch delete error:', err);
    } finally {
      setBatchDeleting(false);
    }
  };

  const openDetailView = async (source: WebSourceListItem, view: DetailViewType) => {
    setSelectedSource(source);
    setDetailView(view);
    setDetailLoading(true);

    try {
      switch (view) {
        case 'content':
          const contentData = await webPagesApi.getContent(source.id);
          setDetailData(contentData);
          break;
        case 'links':
          const linksData = await webPagesApi.getLinks(source.id);
          setDetailData(linksData);
          break;
        case 'images':
          const imagesData = await webPagesApi.getImages(source.id);
          setDetailData(imagesData);
          break;
      }
    } catch (err) {
      setError(t('common.webPages.errors.loadFailed'));
      console.error(err);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetailView = () => {
    setSelectedSource(null);
    setDetailView(null);
    setDetailData(null);
  };

  // =============================================================================
  // Render Helpers
  // =============================================================================

  const getStatusBadge = (status: WebSourceStatus) => {
    switch (status) {
      case 'ready':
        return (
          <span className="webpages-status-badge webpages-status-badge--ready">
            <CheckCircle size={12} /> {t('common.webPages.status.ready')}
          </span>
        );
      case 'pending':
        return (
          <span className="webpages-status-badge webpages-status-badge--pending">
            <Clock size={12} /> {t('common.webPages.status.pending')}
          </span>
        );
      case 'fetching':
      case 'extracting':
      case 'chunking':
      case 'embedding':
        return (
          <span className="webpages-status-badge webpages-status-badge--processing">
            <Loader2 size={12} className="spinning" /> {t(`common.webPages.status.${status}`)}
          </span>
        );
      case 'error':
        return (
          <span className="webpages-status-badge webpages-status-badge--error">
            <XCircle size={12} /> {t('common.webPages.status.error')}
          </span>
        );
      default:
        return (
          <span className="webpages-status-badge">
            <AlertCircle size={12} /> {status}
          </span>
        );
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Filter sources by search
  const filteredSources = webSources.filter((source) => {
    if (!search) return true;
    const searchLower = search.toLowerCase();
    return (
      source.display_name.toLowerCase().includes(searchLower) ||
      source.url.toLowerCase().includes(searchLower) ||
      source.domain.toLowerCase().includes(searchLower)
    );
  });

  // =============================================================================
  // Render
  // =============================================================================

  return (
    <div className="webpages-tab">
      {/* Header */}
      <div className="webpages-list-section">
        <div className="webpages-list-header">
          <div className="webpages-search-group">
            <div className="webpages-search">
              <Search size={16} />
              <input
                type="text"
                placeholder={t('common.webPages.search.placeholder')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              className="webpages-filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">{t('common.webPages.filter.allStatus')}</option>
              <option value="ready">{t('common.webPages.status.ready')}</option>
              <option value="pending">{t('common.webPages.status.pending')}</option>
              <option value="error">{t('common.webPages.status.error')}</option>
            </select>
          </div>
          <div className="webpages-header-actions">
            {selectedIds.size > 0 && (
              <button
                className="btn btn--danger"
                onClick={() => setShowBatchDeleteConfirm(true)}
                disabled={batchDeleting}
              >
                <Trash2 size={16} />
                {t('common.webPages.batchDelete.button')} ({selectedIds.size})
              </button>
            )}
            <button
              className="btn btn--secondary"
              onClick={() => loadWebSources()}
              disabled={loading}
            >
              <RefreshCw size={16} className={loading ? 'spinning' : ''} />
              {t('common.refresh')}
            </button>
            <button
              className="btn btn--primary"
              onClick={() => setShowAddModal(true)}
            >
              <Plus size={16} />
              {t('common.webPages.addUrl')}
            </button>
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="webpages-error-banner">
            <AlertCircle size={16} />
            <span>{error}</span>
            <button onClick={() => setError(null)}>
              <X size={14} />
            </button>
          </div>
        )}

        {/* Web Sources Table */}
        {loading && webSources.length === 0 ? (
          <div className="webpages-loading">
            <Loader2 size={32} className="spinning" />
            <span>{t('common.loading')}</span>
          </div>
        ) : filteredSources.length === 0 ? (
          <div className="webpages-empty">
            <Globe size={48} strokeWidth={1} />
            <h3>{t('common.webPages.empty.title')}</h3>
            <p>{t('common.webPages.empty.description')}</p>
            <button
              className="btn btn--primary"
              onClick={() => setShowAddModal(true)}
            >
              <Plus size={16} />
              {t('common.webPages.addUrl')}
            </button>
          </div>
        ) : (
          <div className="webpages-table-container">
            <table className="webpages-table">
              <thead>
                <tr>
                  <th className="checkbox-column">
                    <button
                      className="checkbox-btn"
                      onClick={toggleSelectAll}
                      title={
                        selectedIds.size === filteredSources.length
                          ? t('common.externalConnectors.deselectAll')
                          : t('common.externalConnectors.selectAll')
                      }
                    >
                      {selectedIds.size === filteredSources.length &&
                      filteredSources.length > 0 ? (
                        <CheckSquare size={18} />
                      ) : (
                        <Square size={18} />
                      )}
                    </button>
                  </th>
                  <th>{t('common.webPages.table.url')}</th>
                  <th>{t('common.webPages.table.status')}</th>
                  <th>{t('common.webPages.table.chunks')}</th>
                  <th>{t('common.webPages.table.words')}</th>
                  <th>{t('common.webPages.table.created')}</th>
                  <th>{t('common.webPages.table.actions')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredSources.map((source) => (
                  <tr
                    key={source.id}
                    className={selectedIds.has(source.id) ? 'selected' : ''}
                  >
                    <td className="checkbox-column">
                      <button
                        className="checkbox-btn"
                        onClick={() => toggleSelect(source.id)}
                      >
                        {selectedIds.has(source.id) ? (
                          <CheckSquare size={18} className="checked" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>
                    </td>
                    <td>
                      <div className="webpages-url-cell">
                        <Globe size={18} className="webpages-icon" />
                        <div className="webpages-url-info">
                          <span className="webpages-display-name">
                            {source.display_name}
                          </span>
                          <span className="webpages-domain">{source.domain}</span>
                        </div>
                      </div>
                    </td>
                    <td>{getStatusBadge(source.status)}</td>
                    <td>{source.chunk_count}</td>
                    <td>{source.word_count.toLocaleString()}</td>
                    <td>{formatDate(source.created_at)}</td>
                    <td>
                      <div className="webpages-actions">
                        <button
                          className="webpages-action-btn"
                          title={t('common.webPages.actions.viewContent')}
                          onClick={() => openDetailView(source, 'content')}
                          disabled={source.status !== 'ready'}
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          className="webpages-action-btn"
                          title={t('common.webPages.actions.viewLinks')}
                          onClick={() => openDetailView(source, 'links')}
                          disabled={source.status !== 'ready'}
                        >
                          <Link2 size={16} />
                        </button>
                        <button
                          className="webpages-action-btn"
                          title={t('common.webPages.actions.viewImages')}
                          onClick={() => openDetailView(source, 'images')}
                          disabled={source.status !== 'ready'}
                        >
                          <Image size={16} />
                        </button>
                        <button
                          className="webpages-action-btn"
                          title={t('common.webPages.actions.refresh')}
                          onClick={() => handleRefresh(source.id)}
                          disabled={source.status !== 'ready' && source.status !== 'error'}
                        >
                          <RefreshCw size={16} />
                        </button>
                        <a
                          className="webpages-action-btn"
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={t('common.webPages.actions.openUrl')}
                        >
                          <ExternalLink size={16} />
                        </a>
                        <button
                          className="webpages-action-btn webpages-action-btn--delete"
                          title={t('common.delete')}
                          onClick={() => setDeleteTarget(source)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {total > limit && (
              <div className="webpages-pagination">
                <button
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  {t('common.previous')}
                </button>
                <span>
                  {page} / {Math.ceil(total / limit)}
                </span>
                <button
                  disabled={page >= Math.ceil(total / limit)}
                  onClick={() => setPage((p) => p + 1)}
                >
                  {t('common.next')}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add URL Modal */}
      {showAddModal && (
        <div className="webpages-modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="webpages-modal" onClick={(e) => e.stopPropagation()}>
            <div className="webpages-modal-header">
              <h3>{t('common.webPages.addModal.title')}</h3>
              <button onClick={() => setShowAddModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="webpages-modal-content">
              <div className="webpages-mode-toggle">
                <button
                  className={!isBulkMode ? 'active' : ''}
                  onClick={() => setIsBulkMode(false)}
                >
                  {t('common.webPages.addModal.singleUrl')}
                </button>
                <button
                  className={isBulkMode ? 'active' : ''}
                  onClick={() => setIsBulkMode(true)}
                >
                  {t('common.webPages.addModal.bulkUrls')}
                </button>
              </div>

              {isBulkMode ? (
                <div className="webpages-form-group">
                  <label>{t('common.webPages.addModal.urlsLabel')}</label>
                  <textarea
                    value={bulkUrls}
                    onChange={(e) => setBulkUrls(e.target.value)}
                    placeholder={t('common.webPages.addModal.urlsPlaceholder')}
                    rows={6}
                  />
                </div>
              ) : (
                <div className="webpages-form-group">
                  <label>{t('common.webPages.addModal.urlLabel')}</label>
                  <input
                    type="url"
                    value={newUrl}
                    onChange={(e) => setNewUrl(e.target.value)}
                    placeholder={t('common.webPages.addModal.urlPlaceholder')}
                  />
                </div>
              )}

              <div className="webpages-form-group">
                <label>{t('common.webPages.addModal.tagsLabel')}</label>
                <input
                  type="text"
                  value={newTags}
                  onChange={(e) => setNewTags(e.target.value)}
                  placeholder={t('common.webPages.addModal.tagsPlaceholder')}
                />
              </div>

              <div className="webpages-modal-actions">
                <button
                  className="btn btn--secondary"
                  onClick={() => setShowAddModal(false)}
                >
                  {t('common.cancel')}
                </button>
                <button
                  className="btn btn--primary"
                  onClick={handleAddUrl}
                  disabled={adding}
                >
                  {adding ? (
                    <>
                      <Loader2 size={16} className="spinning" />
                      {t('common.webPages.addModal.adding')}
                    </>
                  ) : (
                    <>
                      <Plus size={16} />
                      {t('common.webPages.addModal.add')}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detail Modal */}
      {detailView && selectedSource && (
        <div className="webpages-modal-overlay" onClick={closeDetailView}>
          <div
            className="webpages-modal webpages-modal--large"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="webpages-modal-header">
              <h3>
                {detailView === 'content' && t('common.webPages.detail.content')}
                {detailView === 'links' && t('common.webPages.detail.links')}
                {detailView === 'images' && t('common.webPages.detail.images')}
                <span className="modal-source-name">
                  {' '}
                  - {selectedSource.display_name}
                </span>
              </h3>
              <button onClick={closeDetailView}>
                <X size={20} />
              </button>
            </div>
            <div className="webpages-modal-content">
              {detailLoading ? (
                <div className="webpages-loading">
                  <Loader2 size={32} className="spinning" />
                  <span>{t('common.loading')}</span>
                </div>
              ) : (
                <>
                  {/* Content View */}
                  {detailView === 'content' && detailData && 'data' in detailData && (
                    <div className="detail-content">
                      <div className="detail-stats">
                        <span>
                          {t('common.webPages.detail.wordCount')}:{' '}
                          {(detailData as ContentResponse).data.word_count.toLocaleString()}
                        </span>
                        <span>
                          {t('common.webPages.detail.charCount')}:{' '}
                          {(detailData as ContentResponse).data.char_count.toLocaleString()}
                        </span>
                      </div>
                      <pre className="detail-text">
                        {(detailData as ContentResponse).data.content || t('common.webPages.detail.noContent')}
                      </pre>
                    </div>
                  )}

                  {/* Links View */}
                  {detailView === 'links' && detailData && 'data' in detailData && (
                    <div className="detail-links">
                      <p className="detail-count">
                        {t('common.webPages.detail.linkCount')}:{' '}
                        {(detailData as LinksResponse).data.count}
                      </p>
                      <ul className="links-list">
                        {(detailData as LinksResponse).data.links.map((link, idx) => (
                          <li key={idx}>
                            <a
                              href={link.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {link.text || link.url}
                            </a>
                            {link.is_internal && (
                              <span className="internal-badge">internal</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Images View */}
                  {detailView === 'images' && detailData && 'data' in detailData && (
                    <div className="detail-images">
                      <p className="detail-count">
                        {t('common.webPages.detail.imageCount')}:{' '}
                        {(detailData as ImagesResponse).data.count}
                      </p>
                      <div className="images-grid">
                        {(detailData as ImagesResponse).data.images.map((img, idx) => (
                          <div key={idx} className="image-item">
                            <img
                              src={img.url}
                              alt={img.alt_text}
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display = 'none';
                              }}
                            />
                            <p>{img.alt_text || 'No alt text'}</p>
                          </div>
                        ))}
                      </div>
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
        <div className="webpages-modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div
            className="webpages-modal webpages-modal--confirm"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="webpages-modal-header">
              <h3>{t('common.delete')}</h3>
              <button onClick={() => setDeleteTarget(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="webpages-modal-content">
              <p>
                {t('common.webPages.deleteConfirm.message')}{' '}
                <strong>{deleteTarget.display_name}</strong>?
              </p>
              <p className="delete-warning">{t('common.webPages.deleteConfirm.warning')}</p>
              <div className="webpages-modal-actions">
                <button
                  className="btn btn--secondary"
                  onClick={() => setDeleteTarget(null)}
                >
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
        <div
          className="webpages-modal-overlay"
          onClick={() => setShowBatchDeleteConfirm(false)}
        >
          <div
            className="webpages-modal webpages-modal--confirm"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="webpages-modal-header">
              <h3>{t('common.webPages.batchDelete.title')}</h3>
              <button onClick={() => setShowBatchDeleteConfirm(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="webpages-modal-content">
              <p>
                {t('common.webPages.batchDelete.message', {
                  count: selectedIds.size,
                })}
              </p>
              <p className="delete-warning">{t('common.webPages.deleteConfirm.warning')}</p>
              <div className="webpages-modal-actions">
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
                      {t('common.webPages.batchDelete.deleting')}
                    </>
                  ) : (
                    t('common.webPages.batchDelete.confirm')
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WebPages;
