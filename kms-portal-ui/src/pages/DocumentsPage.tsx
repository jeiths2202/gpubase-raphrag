/**
 * Documents & RAG Governance Page
 *
 * Unified page for document management and RAG configuration.
 * Follows AdminDashboardPage tab pattern.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  FileText,
  Settings,
  FlaskConical,
  TrendingUp,
  Plus,
  Search,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Loader2,
  Play,
  Pause,
  Copy,
  Edit,
  Check,
  X,
  AlertTriangle,
  Upload,
  Trash2,
  Eye,
  File,
  FileImage,
  FileSpreadsheet,
  Presentation,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Database,
  Shield,
  Layers,
  FolderOpen,
  Globe,
} from 'lucide-react';
import { AdaptiveDocuments } from '../components/AdaptiveDocuments';
import { WebPages } from '../components/WebPages';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import './DocumentsPage.css';
import { useSimplePageContext } from '../hooks/usePageContext';
import { useAuthStore } from '../store/authStore';
import { useTranslation } from '../hooks/useTranslation';

// =============================================================================
// Types
// =============================================================================

type TabId = 'documents' | 'webpages' | 'adaptive' | 'profiles' | 'experiments' | 'metrics';

interface RAGProfileSummary {
  id: string;
  name: string;
  description: string | null;
  space_id: string | null;
  embedding_version: number;
  is_active: boolean;
  traffic_percentage: number;
  retrieval_strategy: string;
  chunk_size: number;
  created_at: string;
}

interface ExperimentSummary {
  id: string;
  name: string;
  status: string;
  baseline_profile_name: string;
  variant_count: number;
  total_queries: number;
  started_at: string | null;
  created_at: string;
}

interface RAGConfigOverview {
  total_profiles: number;
  active_profiles: number;
  total_experiments: number;
  active_experiments: number;
  documents_with_custom_profile: number;
  pending_reembedding: number;
  recent_profiles: RAGProfileSummary[];
  recent_experiments: ExperimentSummary[];
}

interface ProfileMetrics {
  profile_id: string;
  profile_name: string;
  total_queries: number;
  success_rate: number;
  avg_latency_ms: number;
  avg_similarity_score: number;
  satisfaction_rate: number;
}

interface DocumentListItem {
  id: string;
  filename: string;
  display_name: string;
  document_type: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  file_size: number;
  chunk_count: number;
  entity_count: number;
  language: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

interface OrphanedDataInfo {
  orphaned_image_embeddings: number;
  orphaned_text_chunks: number;
  orphaned_document_ids: string[];
}

interface CleanupResult {
  deleted_image_embeddings: number;
  deleted_text_chunks: number;
  cleaned_document_ids: string[];
  message: string;
}

// =============================================================================
// Constants
// =============================================================================

// Tab icons only - labels are translated in component
const TAB_ICONS: Record<TabId, React.ReactNode> = {
  documents: <FileText size={18} />,
  webpages: <Globe size={18} />,
  adaptive: <Layers size={18} />,
  profiles: <Settings size={18} />,
  experiments: <FlaskConical size={18} />,
  metrics: <TrendingUp size={18} />,
};

const TAB_IDS: TabId[] = ['documents', 'webpages', 'adaptive', 'profiles', 'experiments', 'metrics'];

const STRATEGY_COLORS: Record<string, string> = {
  vector: '#6366f1',
  graph: '#8b5cf6',
  hybrid: '#22c55e',
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  active: { bg: '#dcfce7', text: '#166534' },
  draft: { bg: '#dbeafe', text: '#1e40af' },
  paused: { bg: '#fef3c7', text: '#92400e' },
  completed: { bg: '#f3f4f6', text: '#374151' },
};

// Reserved for future PieChart usage
// const CHART_COLORS = ['#6366f1', '#8b5cf6', '#22c55e', '#f59e0b', '#ef4444'];

// =============================================================================
// Main Component
// =============================================================================

export const DocumentsPage: React.FC = () => {
  // Register page context for AI awareness
  useSimplePageContext(['documents', 'adaptive-embedding', 'rag-profiles', 'experiments', 'metrics']);
  const { t } = useTranslation();

  const [activeTab, setActiveTab] = useState<TabId>('profiles');
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<RAGConfigOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Get translated tab labels
  const getTabLabel = (tabId: TabId): string => {
    switch (tabId) {
      case 'documents': return 'Documents';
      case 'webpages': return t('common.webPages.tabLabel');
      case 'adaptive': return t('common.adaptive.tabLabelFull');
      case 'profiles': return 'RAG Profiles';
      case 'experiments': return 'A/B Tests';
      case 'metrics': return 'Metrics';
      default: return tabId;
    }
  };

  // Fetch overview data
  const fetchOverview = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/rag-config/overview', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setOverview(result.data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch RAG config overview:', err);
      setError('Failed to load RAG configuration data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  // Render tab content
  const renderTabContent = () => {
    if (loading) {
      return (
        <div className="documents-loading">
          <Loader2 className="spinning" size={32} />
          <span>Loading...</span>
        </div>
      );
    }

    if (error) {
      return (
        <div className="documents-error">
          <AlertTriangle size={32} />
          <span>{error}</span>
          <button onClick={fetchOverview}>Retry</button>
        </div>
      );
    }

    switch (activeTab) {
      case 'documents':
        return <DocumentsTab />;
      case 'webpages':
        return <WebPages />;
      case 'adaptive':
        return <AdaptiveDocuments />;
      case 'profiles':
        return <ProfilesTab onRefresh={fetchOverview} />;
      case 'experiments':
        return <ExperimentsTab onRefresh={fetchOverview} />;
      case 'metrics':
        return <MetricsTab />;
      default:
        return null;
    }
  };

  return (
    <div className="documents-page">
      {/* Header */}
      <header className="documents-header">
        <div className="documents-header-left">
          <h1>Documents & RAG Governance</h1>
          <p>Manage documents, RAG profiles, and A/B experiments</p>
        </div>
        <div className="documents-header-right">
          <button className="documents-btn documents-btn--secondary" onClick={fetchOverview}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </header>

      {/* Overview KPIs */}
      {overview && (
        <div className="documents-kpi-grid">
          <div className="documents-kpi-card">
            <div className="documents-kpi-icon" style={{ backgroundColor: '#6366f115', color: '#6366f1' }}>
              <Settings size={20} />
            </div>
            <div className="documents-kpi-content">
              <div className="documents-kpi-label">Active Profiles</div>
              <div className="documents-kpi-value">{overview.active_profiles}</div>
              <div className="documents-kpi-sub">of {overview.total_profiles} total</div>
            </div>
          </div>
          <div className="documents-kpi-card">
            <div className="documents-kpi-icon" style={{ backgroundColor: '#8b5cf615', color: '#8b5cf6' }}>
              <FlaskConical size={20} />
            </div>
            <div className="documents-kpi-content">
              <div className="documents-kpi-label">Active Experiments</div>
              <div className="documents-kpi-value">{overview.active_experiments}</div>
              <div className="documents-kpi-sub">of {overview.total_experiments} total</div>
            </div>
          </div>
          <div className="documents-kpi-card">
            <div className="documents-kpi-icon" style={{ backgroundColor: '#22c55e15', color: '#22c55e' }}>
              <FileText size={20} />
            </div>
            <div className="documents-kpi-content">
              <div className="documents-kpi-label">Custom Profiles</div>
              <div className="documents-kpi-value">{overview.documents_with_custom_profile}</div>
              <div className="documents-kpi-sub">documents assigned</div>
            </div>
          </div>
          <div className="documents-kpi-card">
            <div className="documents-kpi-icon" style={{ backgroundColor: '#f59e0b15', color: '#f59e0b' }}>
              <RefreshCw size={20} />
            </div>
            <div className="documents-kpi-content">
              <div className="documents-kpi-label">Pending Re-embedding</div>
              <div className="documents-kpi-value">{overview.pending_reembedding}</div>
              <div className="documents-kpi-sub">documents queued</div>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="documents-tabs">
        {TAB_IDS.map((tabId) => (
          <button
            key={tabId}
            className={`documents-tab ${activeTab === tabId ? 'active' : ''}`}
            onClick={() => setActiveTab(tabId)}
          >
            {TAB_ICONS[tabId]}
            <span>{getTabLabel(tabId)}</span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="documents-content">{renderTabContent()}</div>
    </div>
  );
};

// =============================================================================
// Documents Tab
// =============================================================================

const DocumentsTab: React.FC = () => {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin';

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null);
  const [detailDocId, setDetailDocId] = useState<string | null>(null);
  const limit = 15;

  // Admin: Orphaned data state
  const [orphanedData, setOrphanedData] = useState<OrphanedDataInfo | null>(null);
  const [orphanedLoading, setOrphanedLoading] = useState(false);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [showCleanupConfirm, setShowCleanupConfirm] = useState(false);
  const [showFullCleanupConfirm, setShowFullCleanupConfirm] = useState(false);

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);

      const response = await fetch(`/api/v1/documents?${params}`, {
        credentials: 'include',
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      setDocuments(result.data.documents || []);
      setTotalPages(result.pagination?.total_pages || 1);
      setTotalItems(result.pagination?.total_items || 0);
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      const response = await fetch(`/api/v1/documents/${deleteTarget.id}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      if (response.ok) {
        fetchDocuments();
        setDeleteTarget(null);
      }
    } catch (err) {
      console.error('Failed to delete document:', err);
    }
  };

  // Admin: Check for orphaned data
  const checkOrphanedData = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setOrphanedLoading(true);
      const response = await fetch('/api/v1/admin/cleanup/orphaned-data', {
        credentials: 'include',
      });
      if (response.ok) {
        const result = await response.json();
        setOrphanedData(result.data);
      }
    } catch (err) {
      console.error('Failed to check orphaned data:', err);
    } finally {
      setOrphanedLoading(false);
    }
  }, [isAdmin]);

  // Admin: Cleanup orphaned data
  const cleanupOrphanedData = async () => {
    try {
      setCleanupLoading(true);
      const response = await fetch('/api/v1/admin/cleanup/orphaned-data', {
        method: 'DELETE',
        credentials: 'include',
      });
      if (response.ok) {
        const result = await response.json();
        setCleanupResult(result.data);
        setOrphanedData(null);
        await checkOrphanedData();
      }
    } catch (err) {
      console.error('Failed to cleanup orphaned data:', err);
    } finally {
      setCleanupLoading(false);
      setShowCleanupConfirm(false);
    }
  };

  // Admin: Full embedding cleanup (delete all embeddings)
  const cleanupAllEmbeddings = async () => {
    try {
      setCleanupLoading(true);
      // First, get all document IDs from image_embeddings that exist
      const checkResponse = await fetch('/api/v1/admin/cleanup/orphaned-data', {
        credentials: 'include',
      });

      if (checkResponse.ok) {
        const checkResult = await checkResponse.json();
        const orphanedIds = checkResult.data?.orphaned_document_ids || [];

        // Delete orphaned data
        if (orphanedIds.length > 0) {
          const response = await fetch('/api/v1/admin/cleanup/orphaned-data', {
            method: 'DELETE',
            credentials: 'include',
          });
          if (response.ok) {
            const result = await response.json();
            setCleanupResult(result.data);
          }
        }
      }
      await checkOrphanedData();
    } catch (err) {
      console.error('Failed to cleanup all embeddings:', err);
    } finally {
      setCleanupLoading(false);
      setShowFullCleanupConfirm(false);
    }
  };

  // Auto-check orphaned data for admin users
  useEffect(() => {
    if (isAdmin) {
      checkOrphanedData();
    }
  }, [isAdmin, checkOrphanedData]);

  const getFileIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'pdf':
        return <FileText size={18} className="text-red-500" />;
      case 'image':
        return <FileImage size={18} className="text-blue-500" />;
      case 'excel':
        return <FileSpreadsheet size={18} className="text-green-500" />;
      case 'powerpoint':
        return <Presentation size={18} className="text-orange-500" />;
      default:
        return <File size={18} className="text-gray-500" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
      case 'ready':
        return (
          <span className="doc-status-badge doc-status-badge--completed">
            <CheckCircle size={12} /> Ready
          </span>
        );
      case 'processing':
        return (
          <span className="doc-status-badge doc-status-badge--processing">
            <Clock size={12} /> Processing
          </span>
        );
      case 'pending':
        return (
          <span className="doc-status-badge doc-status-badge--pending">
            <AlertCircle size={12} /> Pending
          </span>
        );
      case 'failed':
      case 'error':
        return (
          <span className="doc-status-badge doc-status-badge--failed">
            <XCircle size={12} /> Error
          </span>
        );
      case 'interrupted':
        return (
          <span className="doc-status-badge doc-status-badge--interrupted">
            <AlertCircle size={12} /> Interrupted
          </span>
        );
      default:
        return <span className="doc-status-badge">{status}</span>;
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
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

  return (
    <div className="documents-tab-content">
      {/* Header */}
      <div className="documents-list-section">
        <div className="documents-list-header">
          <div className="documents-search-group">
            <div className="documents-search">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search documents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select
              className="documents-filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Status</option>
              <option value="ready">Ready</option>
              <option value="processing">Processing</option>
              <option value="pending">Pending</option>
              <option value="error">Error</option>
              <option value="interrupted">Interrupted</option>
            </select>
          </div>
          <div className="documents-header-actions">
            <button className="btn btn--secondary" onClick={fetchDocuments}>
              <RefreshCw size={16} />
              Refresh
            </button>
            <button className="btn btn--primary" onClick={() => setShowUploadModal(true)}>
              <Upload size={16} />
              Upload Document
            </button>
          </div>
        </div>

        {/* Admin: Data Cleanup Section */}
        {isAdmin && (
          <div className="admin-cleanup-section">
            <div className="admin-cleanup-header">
              <div className="admin-cleanup-title">
                <Shield size={18} />
                <span>Data Management (Admin)</span>
              </div>
              <button
                className="btn btn--secondary btn--sm"
                onClick={checkOrphanedData}
                disabled={orphanedLoading}
              >
                {orphanedLoading ? <Loader2 size={14} className="spinning" /> : <RefreshCw size={14} />}
                Check Orphaned Data
              </button>
            </div>

            {/* Orphaned Data Status */}
            {orphanedData && (
              <div className="admin-cleanup-status">
                <div className="cleanup-stat-card">
                  <Database size={24} />
                  <div className="cleanup-stat-info">
                    <span className="cleanup-stat-value">{orphanedData.orphaned_image_embeddings}</span>
                    <span className="cleanup-stat-label">Orphaned Images</span>
                  </div>
                </div>
                <div className="cleanup-stat-card">
                  <FileText size={24} />
                  <div className="cleanup-stat-info">
                    <span className="cleanup-stat-value">{orphanedData.orphaned_text_chunks}</span>
                    <span className="cleanup-stat-label">Orphaned Chunks</span>
                  </div>
                </div>
                <div className="cleanup-stat-card">
                  <File size={24} />
                  <div className="cleanup-stat-info">
                    <span className="cleanup-stat-value">{orphanedData.orphaned_document_ids.length}</span>
                    <span className="cleanup-stat-label">Orphaned Doc IDs</span>
                  </div>
                </div>

                {(orphanedData.orphaned_image_embeddings > 0 || orphanedData.orphaned_text_chunks > 0) && (
                  <button
                    className="btn btn--warning btn--sm"
                    onClick={() => setShowCleanupConfirm(true)}
                    disabled={cleanupLoading}
                  >
                    {cleanupLoading ? <Loader2 size={14} className="spinning" /> : <Trash2 size={14} />}
                    Cleanup Orphaned Data
                  </button>
                )}
              </div>
            )}

            {/* Cleanup Result */}
            {cleanupResult && (
              <div className="cleanup-result">
                <CheckCircle size={16} />
                <span>{cleanupResult.message}</span>
                <button className="cleanup-result-close" onClick={() => setCleanupResult(null)}>
                  <X size={14} />
                </button>
              </div>
            )}

            {/* Full Cleanup Button */}
            <div className="admin-cleanup-actions">
              <button
                className="btn btn--danger btn--sm"
                onClick={() => setShowFullCleanupConfirm(true)}
                disabled={cleanupLoading}
              >
                <Trash2 size={14} />
                Full Embedding Cleanup
              </button>
              <span className="cleanup-help-text">
                Removes all orphaned embeddings not linked to any document
              </span>
            </div>
          </div>
        )}

        {/* Documents Table */}
        {loading ? (
          <div className="documents-loading">
            <Loader2 size={32} className="spinning" />
            <span>Loading documents...</span>
          </div>
        ) : documents.length === 0 ? (
          <div className="documents-empty">
            <FileText size={48} strokeWidth={1} />
            <h3>No documents found</h3>
            <p>Upload your first document to get started with RAG processing.</p>
            <button className="btn btn--primary" onClick={() => setShowUploadModal(true)}>
              <Upload size={16} />
              Upload Document
            </button>
          </div>
        ) : (
          <>
            <div className="documents-table-container">
              <table className="documents-table">
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Size</th>
                    <th>Chunks</th>
                    <th>Language</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        <div className="doc-name-cell">
                          {getFileIcon(doc.document_type)}
                          <div className="doc-name-info">
                            <span className="doc-name">{doc.display_name || doc.filename}</span>
                            {doc.display_name && doc.display_name !== doc.filename && (
                              <span className="doc-filename">{doc.filename}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="doc-type-badge">{doc.document_type}</span>
                      </td>
                      <td>{getStatusBadge(doc.status)}</td>
                      <td>{formatFileSize(doc.file_size)}</td>
                      <td>{doc.chunk_count}</td>
                      <td>{doc.language?.toUpperCase() || 'AUTO'}</td>
                      <td>{formatDate(doc.created_at)}</td>
                      <td>
                        <div className="doc-actions">
                          <button
                            className="doc-action-btn"
                            title="View Details"
                            onClick={() => setDetailDocId(doc.id)}
                          >
                            <Eye size={16} />
                          </button>
                          <button
                            className="doc-action-btn doc-action-btn--delete"
                            title="Delete"
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

            {/* Pagination */}
            <div className="documents-pagination">
              <span className="pagination-info">
                {totalItems} documents total
              </span>
              <div className="pagination-controls">
                <button
                  className="pagination-btn"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft size={16} />
                  Previous
                </button>
                <span className="pagination-page">
                  Page {page} of {totalPages}
                </span>
                <button
                  className="pagination-btn"
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                >
                  Next
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <DocumentUploadModal
          onClose={() => setShowUploadModal(false)}
          onSuccess={() => {
            setShowUploadModal(false);
            fetchDocuments();
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal-content modal-content--small" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header modal-header--danger">
              <h2>Delete Document</h2>
              <button className="modal-close" onClick={() => setDeleteTarget(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="delete-warning">
                <AlertTriangle size={48} className="delete-warning-icon" />
                <p className="delete-warning-text">
                  Are you sure you want to delete this document?
                </p>
                <p className="delete-warning-subtext">
                  This will permanently remove the document and all associated chunks and embeddings.
                </p>
              </div>
              <div className="delete-doc-info">
                <div><strong>File:</strong> {deleteTarget.filename}</div>
                <div><strong>Chunks:</strong> {deleteTarget.chunk_count}</div>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn--secondary" onClick={() => setDeleteTarget(null)}>
                Cancel
              </button>
              <button className="btn btn--danger" onClick={handleDelete}>
                <Trash2 size={16} />
                Delete Document
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Document Detail Modal */}
      {detailDocId && (
        <DocumentDetailModal
          documentId={detailDocId}
          onClose={() => setDetailDocId(null)}
        />
      )}

      {/* Orphaned Data Cleanup Confirmation Modal */}
      {showCleanupConfirm && (
        <div className="modal-overlay" onClick={() => setShowCleanupConfirm(false)}>
          <div className="modal-content modal-content--small" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header modal-header--warning">
              <h2>Cleanup Orphaned Data</h2>
              <button className="modal-close" onClick={() => setShowCleanupConfirm(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="delete-warning">
                <AlertTriangle size={48} className="delete-warning-icon" />
                <p className="delete-warning-text">
                  Are you sure you want to clean up orphaned data?
                </p>
                <p className="delete-warning-subtext">
                  This will permanently remove embeddings and chunks that are not linked to any document.
                </p>
              </div>
              {orphanedData && (
                <div className="delete-doc-info">
                  <div><strong>Orphaned Images:</strong> {orphanedData.orphaned_image_embeddings}</div>
                  <div><strong>Orphaned Chunks:</strong> {orphanedData.orphaned_text_chunks}</div>
                  <div><strong>Orphaned Doc IDs:</strong> {orphanedData.orphaned_document_ids.length}</div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn--secondary" onClick={() => setShowCleanupConfirm(false)}>
                Cancel
              </button>
              <button className="btn btn--warning" onClick={cleanupOrphanedData} disabled={cleanupLoading}>
                {cleanupLoading ? <Loader2 size={16} className="spinning" /> : <Trash2 size={16} />}
                Cleanup Orphaned Data
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Full Embedding Cleanup Confirmation Modal */}
      {showFullCleanupConfirm && (
        <div className="modal-overlay" onClick={() => setShowFullCleanupConfirm(false)}>
          <div className="modal-content modal-content--small" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header modal-header--danger">
              <h2>Full Embedding Cleanup</h2>
              <button className="modal-close" onClick={() => setShowFullCleanupConfirm(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="delete-warning">
                <AlertTriangle size={48} className="delete-warning-icon" />
                <p className="delete-warning-text">
                  Are you sure you want to perform a full embedding cleanup?
                </p>
                <p className="delete-warning-subtext">
                  This will remove ALL orphaned embeddings from the database that are not linked to any document in the documents table.
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn--secondary" onClick={() => setShowFullCleanupConfirm(false)}>
                Cancel
              </button>
              <button className="btn btn--danger" onClick={cleanupAllEmbeddings} disabled={cleanupLoading}>
                {cleanupLoading ? <Loader2 size={16} className="spinning" /> : <Trash2 size={16} />}
                Full Cleanup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// =============================================================================
// Document Detail Modal
// =============================================================================

// Embedding Quality Types
interface EmbeddingQualityMetrics {
  overall_score: number;
  quality_level: 'excellent' | 'good' | 'fair' | 'poor';
  retrieval_accuracy: number;
  avg_similarity: number;
  similarity_std: number;
  coverage_score: number;
}

interface SimilarityTestResult {
  query: string;
  expected_chunk_index: number;
  retrieved_chunk_index: number;
  similarity_score: number;
  is_hit: boolean;
}

interface EmbeddingQualityResult {
  document_id: string;
  verified_at: string;
  metrics: EmbeddingQualityMetrics;
  embedding_dimension: number;
  chunks_tested: number;
  chunks_total: number;
  test_results: SimilarityTestResult[];
  issues: string[];
  recommendations: string[];
}

interface DocumentDetail {
  id: string;
  filename: string;
  original_name: string;
  file_size: number;
  mime_type: string;
  document_type: string;
  status: string;
  chunks_count: number;
  entities_count: number;
  embedding_status: string;
  language: string;
  processing_mode: string;
  vlm_processed: boolean;
  created_at: string;
  updated_at: string;
  tags: string[];
  stats?: {
    pages: number;
    chunks_count: number;
    entities_count: number;
    avg_chunk_size: number;
    embedding_dimension: number;
    images_count: number;
    tables_count: number;
    figures_count: number;
    vlm_processed: boolean;
  };
  processing_info?: {
    started_at: string | null;
    completed_at: string | null;
    processing_time_seconds: number | null;
  };
  embedding_quality?: {
    overall_score: number;
    quality_level: string;
    verified_at: string;
    has_issues: boolean;
  };
  error?: string | null;
}

interface DetailModalProps {
  documentId: string;
  onClose: () => void;
}

const DocumentDetailModal: React.FC<DetailModalProps> = ({ documentId, onClose }) => {
  const [document, setDocument] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Embedding quality verification state
  const [qualityResult, setQualityResult] = useState<EmbeddingQualityResult | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);

  // Re-embedding state
  const [showReEmbedForm, setShowReEmbedForm] = useState(false);
  const [reEmbedLoading, setReEmbedLoading] = useState(false);
  const [reEmbedError, setReEmbedError] = useState<string | null>(null);
  const [reEmbedParams, setReEmbedParams] = useState({
    chunk_size: 512,
    chunk_overlap: 50,
    processing_mode: 'text_only',
    enable_vlm: false,
    extract_tables: true,
    extract_images: true,
    force: false,
  });

  // Re-embedding progress state
  const [reEmbedTaskId, setReEmbedTaskId] = useState<string | null>(null);
  const [reEmbedProgress, setReEmbedProgress] = useState<{
    current_step: string;
    steps: Array<{ name: string; status: string; progress: number }>;
    overall_progress: number;
  } | null>(null);
  const [isReEmbedding, setIsReEmbedding] = useState(false);

  useEffect(() => {
    const fetchDocument = async () => {
      try {
        setLoading(true);
        const response = await fetch(`/api/v1/documents/${documentId}`, {
          credentials: 'include',
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();
        setDocument(result.data);
        setError(null);

        // Auto-fetch existing quality result if available
        if (result.data?.embedding_status === 'completed') {
          fetchQualityResult();
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load document');
      } finally {
        setLoading(false);
      }
    };

    fetchDocument();
  }, [documentId]);

  // Poll for re-embedding progress
  useEffect(() => {
    if (!reEmbedTaskId || !isReEmbedding) return;

    const pollStatus = async () => {
      try {
        const response = await fetch(`/api/v1/documents/upload-status/${reEmbedTaskId}`, {
          credentials: 'include',
        });

        if (!response.ok) {
          console.error('Failed to fetch re-embed status');
          return;
        }

        const result = await response.json();
        const status = result.data;

        setReEmbedProgress({
          current_step: status.progress.current_step,
          steps: status.progress.steps,
          overall_progress: status.progress.overall_progress,
        });

        // Check if processing is complete
        if (status.status === 'ready' || status.progress.overall_progress >= 100) {
          setIsReEmbedding(false);
          setReEmbedTaskId(null);
          setReEmbedProgress(null);

          // Refresh document data
          const docResponse = await fetch(`/api/v1/documents/${documentId}`, {
            credentials: 'include',
          });
          if (docResponse.ok) {
            const docResult = await docResponse.json();
            setDocument(docResult.data);

            // Fetch new quality result if available
            if (docResult.data?.embedding_status === 'completed') {
              fetchQualityResult();
            }
          }
        } else if (status.status === 'error') {
          setIsReEmbedding(false);
          setReEmbedError('Re-embedding failed');
        }
      } catch (err) {
        console.error('Error polling re-embed status:', err);
      }
    };

    // Poll every 800ms
    const interval = setInterval(pollStatus, 800);
    // Initial poll
    pollStatus();

    return () => clearInterval(interval);
  }, [reEmbedTaskId, isReEmbedding, documentId]);

  // Fetch existing quality verification result
  const fetchQualityResult = async () => {
    try {
      const response = await fetch(`/api/v1/documents/${documentId}/embedding-quality`, {
        credentials: 'include',
      });

      if (response.ok) {
        const result = await response.json();
        setQualityResult(result.data);
      }
    } catch (err) {
      // Silent fail - quality result may not exist yet
      console.log('No existing quality result found');
    }
  };

  // Run quality verification
  const runQualityVerification = async () => {
    try {
      setQualityLoading(true);
      setQualityError(null);

      const response = await fetch(`/api/v1/documents/${documentId}/verify-embedding?sample_size=10`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail?.message || 'Verification failed');
      }

      const result = await response.json();
      setQualityResult(result.data);
    } catch (err) {
      setQualityError(err instanceof Error ? err.message : 'Quality verification failed');
    } finally {
      setQualityLoading(false);
    }
  };

  // Run re-embedding with custom parameters
  const runReEmbed = async () => {
    try {
      setReEmbedLoading(true);
      setReEmbedError(null);

      const response = await fetch(`/api/v1/documents/${documentId}/re-embed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(reEmbedParams),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail?.message || 'Re-embedding failed');
      }

      const result = await response.json();
      const taskId = result.data?.task_id;

      // Update document status to show it's processing
      if (document) {
        setDocument({
          ...document,
          status: 'processing',
          embedding_status: 'pending',
        });
      }

      // Close re-embed form and start progress tracking
      setShowReEmbedForm(false);
      setQualityResult(null); // Clear old quality result

      if (taskId) {
        setReEmbedTaskId(taskId);
        setIsReEmbedding(true);
        // Initialize progress display
        setReEmbedProgress({
          current_step: 're-chunking',
          steps: [
            { name: 're-chunking', status: 'pending', progress: 0 },
            { name: 'embedding', status: 'pending', progress: 0 },
            { name: 'quality-check', status: 'pending', progress: 0 },
          ],
          overall_progress: 10,
        });
      }
    } catch (err) {
      setReEmbedError(err instanceof Error ? err.message : 'Re-embedding failed');
    } finally {
      setReEmbedLoading(false);
    }
  };

  // Get quality level color
  const getQualityLevelColor = (level: string) => {
    switch (level) {
      case 'excellent':
        return '#22c55e';
      case 'good':
        return '#3b82f6';
      case 'fair':
        return '#f59e0b';
      case 'poor':
        return '#ef4444';
      default:
        return '#6b7280';
    }
  };

  // Get quality level label
  const getQualityLevelLabel = (level: string) => {
    switch (level) {
      case 'excellent':
        return 'Excellent (우수)';
      case 'good':
        return 'Good (양호)';
      case 'fair':
        return 'Fair (보통)';
      case 'poor':
        return 'Poor (개선필요)';
      default:
        return level;
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ready':
      case 'completed':
        return 'var(--color-success, #22c55e)';
      case 'processing':
      case 'in_progress':
        return 'var(--color-primary, #6366f1)';
      case 'error':
      case 'failed':
        return 'var(--color-danger, #ef4444)';
      default:
        return 'var(--color-warning, #f59e0b)';
    }
  };

  const getFileIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'pdf':
        return <FileText size={32} className="detail-file-icon detail-file-icon--pdf" />;
      case 'image':
        return <FileImage size={32} className="detail-file-icon detail-file-icon--image" />;
      case 'excel':
        return <FileSpreadsheet size={32} className="detail-file-icon detail-file-icon--excel" />;
      case 'powerpoint':
        return <Presentation size={32} className="detail-file-icon detail-file-icon--ppt" />;
      default:
        return <File size={32} className="detail-file-icon" />;
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-content--large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Document Details</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="modal-body">
          {loading ? (
            <div className="detail-loading">
              <Loader2 size={32} className="spinning" />
              <span>Loading document details...</span>
            </div>
          ) : error ? (
            <div className="detail-error">
              <AlertTriangle size={32} />
              <span>{error}</span>
            </div>
          ) : document ? (
            <div className="detail-content">
              {/* Header Section */}
              <div className="detail-header-section">
                {getFileIcon(document.document_type)}
                <div className="detail-header-info">
                  <h3 className="detail-filename">{document.original_name || document.filename}</h3>
                  <div className="detail-meta-row">
                    <span className="detail-type-badge">{document.document_type?.toUpperCase()}</span>
                    <span
                      className="detail-status-badge"
                      style={{ backgroundColor: getStatusColor(document.status), color: 'white' }}
                    >
                      {document.status}
                    </span>
                    {document.vlm_processed && (
                      <span className="detail-vlm-badge">VLM Processed</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Error Message */}
              {document.error && (
                <div className="detail-error-box">
                  <AlertTriangle size={16} />
                  <span>{document.error}</span>
                </div>
              )}

              {/* Info Grid */}
              <div className="detail-grid">
                {/* Basic Info */}
                <div className="detail-card">
                  <h4 className="detail-card-title">
                    <FileText size={16} />
                    Basic Information
                  </h4>
                  <div className="detail-info-list">
                    <div className="detail-info-row">
                      <span className="detail-info-label">File Size</span>
                      <span className="detail-info-value">{formatFileSize(document.file_size)}</span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">MIME Type</span>
                      <span className="detail-info-value">{document.mime_type}</span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">Language</span>
                      <span className="detail-info-value">{document.language?.toUpperCase() || 'AUTO'}</span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">Processing Mode</span>
                      <span className="detail-info-value">{document.processing_mode?.replace('_', ' ')}</span>
                    </div>
                    {document.tags && document.tags.length > 0 && (
                      <div className="detail-info-row">
                        <span className="detail-info-label">Tags</span>
                        <span className="detail-info-value">
                          {document.tags.map((tag, i) => (
                            <span key={i} className="detail-tag">{tag}</span>
                          ))}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Statistics */}
                <div className="detail-card">
                  <h4 className="detail-card-title">
                    <TrendingUp size={16} />
                    Statistics
                  </h4>
                  <div className="detail-stats-grid">
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{document.stats?.pages || 0}</span>
                      <span className="detail-stat-label">Pages</span>
                    </div>
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{document.chunks_count || document.stats?.chunks_count || 0}</span>
                      <span className="detail-stat-label">Chunks</span>
                    </div>
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{document.entities_count || document.stats?.entities_count || 0}</span>
                      <span className="detail-stat-label">Entities</span>
                    </div>
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{document.stats?.images_count || 0}</span>
                      <span className="detail-stat-label">Images</span>
                    </div>
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{document.stats?.tables_count || 0}</span>
                      <span className="detail-stat-label">Tables</span>
                    </div>
                    <div className="detail-stat-item">
                      <span className="detail-stat-value">{Math.round(document.stats?.avg_chunk_size || 0)}</span>
                      <span className="detail-stat-label">Avg Chunk</span>
                    </div>
                  </div>
                </div>

                {/* Processing Info */}
                <div className="detail-card">
                  <h4 className="detail-card-title">
                    <Clock size={16} />
                    Processing Information
                  </h4>
                  <div className="detail-info-list">
                    <div className="detail-info-row">
                      <span className="detail-info-label">Embedding Status</span>
                      <span
                        className="detail-status-badge detail-status-badge--small"
                        style={{ backgroundColor: getStatusColor(document.embedding_status) }}
                      >
                        {document.embedding_status}
                      </span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">Embedding Dimension</span>
                      <span className="detail-info-value">{document.stats?.embedding_dimension || 'N/A'}</span>
                    </div>
                    {document.processing_info?.started_at && (
                      <div className="detail-info-row">
                        <span className="detail-info-label">Started At</span>
                        <span className="detail-info-value">{formatDate(document.processing_info.started_at)}</span>
                      </div>
                    )}
                    {document.processing_info?.completed_at && (
                      <div className="detail-info-row">
                        <span className="detail-info-label">Completed At</span>
                        <span className="detail-info-value">{formatDate(document.processing_info.completed_at)}</span>
                      </div>
                    )}
                    {document.processing_info?.processing_time_seconds && (
                      <div className="detail-info-row">
                        <span className="detail-info-label">Processing Time</span>
                        <span className="detail-info-value">{document.processing_info.processing_time_seconds}s</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Timestamps */}
                <div className="detail-card">
                  <h4 className="detail-card-title">
                    <Clock size={16} />
                    Timestamps
                  </h4>
                  <div className="detail-info-list">
                    <div className="detail-info-row">
                      <span className="detail-info-label">Created</span>
                      <span className="detail-info-value">{formatDate(document.created_at)}</span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">Updated</span>
                      <span className="detail-info-value">{formatDate(document.updated_at)}</span>
                    </div>
                    <div className="detail-info-row">
                      <span className="detail-info-label">Document ID</span>
                      <span className="detail-info-value detail-info-value--mono">{document.id}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Embedding Quality Verification Section */}
              {document.embedding_status === 'completed' && (
                <div className="detail-quality-section">
                  <div className="detail-quality-header">
                    <h4 className="detail-card-title">
                      <CheckCircle size={16} />
                      Embedding Quality Verification
                    </h4>
                    <button
                      className="btn btn--sm btn--primary"
                      onClick={runQualityVerification}
                      disabled={qualityLoading}
                    >
                      {qualityLoading ? (
                        <>
                          <Loader2 size={14} className="spinning" />
                          Verifying...
                        </>
                      ) : (
                        <>
                          <RefreshCw size={14} />
                          {qualityResult ? 'Re-verify' : 'Verify Quality'}
                        </>
                      )}
                    </button>
                  </div>

                  {qualityError && (
                    <div className="detail-quality-error">
                      <AlertTriangle size={14} />
                      <span>{qualityError}</span>
                    </div>
                  )}

                  {qualityResult && (
                    <div className="detail-quality-content">
                      {/* Overall Score */}
                      <div className="detail-quality-score">
                        <div
                          className="quality-score-circle"
                          style={{
                            borderColor: getQualityLevelColor(qualityResult.metrics.quality_level),
                          }}
                        >
                          <span className="quality-score-value">
                            {Math.round(qualityResult.metrics.overall_score * 100)}
                          </span>
                          <span className="quality-score-label">점</span>
                        </div>
                        <div className="quality-score-info">
                          <span
                            className="quality-level-badge"
                            style={{
                              backgroundColor: getQualityLevelColor(qualityResult.metrics.quality_level),
                            }}
                          >
                            {getQualityLevelLabel(qualityResult.metrics.quality_level)}
                          </span>
                          <span className="quality-verified-at">
                            Verified: {formatDate(qualityResult.verified_at)}
                          </span>
                        </div>
                      </div>

                      {/* Metrics Grid */}
                      <div className="detail-quality-metrics">
                        <div className="quality-metric-item">
                          <span className="quality-metric-value">
                            {Math.round(qualityResult.metrics.retrieval_accuracy * 100)}%
                          </span>
                          <span className="quality-metric-label">Retrieval Accuracy</span>
                        </div>
                        <div className="quality-metric-item">
                          <span className="quality-metric-value">
                            {(qualityResult.metrics.avg_similarity * 100).toFixed(1)}%
                          </span>
                          <span className="quality-metric-label">Avg Similarity</span>
                        </div>
                        <div className="quality-metric-item">
                          <span className="quality-metric-value">
                            {Math.round(qualityResult.metrics.coverage_score * 100)}%
                          </span>
                          <span className="quality-metric-label">Coverage</span>
                        </div>
                        <div className="quality-metric-item">
                          <span className="quality-metric-value">
                            {qualityResult.chunks_tested}/{qualityResult.chunks_total}
                          </span>
                          <span className="quality-metric-label">Chunks Tested</span>
                        </div>
                      </div>

                      {/* Issues & Recommendations */}
                      {qualityResult.issues.length > 0 && (
                        <div className="detail-quality-issues">
                          <h5>
                            <AlertCircle size={14} />
                            Issues Found
                          </h5>
                          <ul>
                            {qualityResult.issues.map((issue, idx) => (
                              <li key={idx}>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {qualityResult.recommendations.length > 0 && (
                        <div className="detail-quality-recommendations">
                          <h5>
                            <CheckCircle size={14} />
                            Recommendations
                          </h5>
                          <ul>
                            {qualityResult.recommendations.map((rec, idx) => (
                              <li key={idx}>{rec}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {!qualityResult && !qualityLoading && !qualityError && (
                    <div className="detail-quality-empty">
                      <p>Click "Verify Quality" to check embedding quality for this document.</p>
                    </div>
                  )}
                </div>
              )}

              {/* Re-Embedding Section */}
              {(document.status !== 'processing' || isReEmbedding) && (
                <div className="detail-reembed-section">
                  <div className="detail-reembed-header">
                    <h4 className="detail-card-title">
                      <RefreshCw size={16} className={isReEmbedding ? 'spinning' : ''} />
                      Re-Embed Document
                    </h4>
                    {!isReEmbedding && (
                      <button
                        className="btn btn--sm btn--secondary"
                        onClick={() => setShowReEmbedForm(!showReEmbedForm)}
                      >
                        {showReEmbedForm ? 'Hide Parameters' : 'Configure & Re-embed'}
                      </button>
                    )}
                  </div>

                  {/* Re-Embedding Progress Display */}
                  {isReEmbedding && reEmbedProgress && (
                    <div className="reembed-progress-container">
                      {/* Overall progress bar */}
                      <div className="reembed-progress-bar-container">
                        <div className="reembed-progress-bar">
                          <div
                            className="reembed-progress-bar-fill"
                            style={{ width: `${reEmbedProgress.overall_progress}%` }}
                          />
                        </div>
                        <span className="reembed-progress-percentage">
                          {reEmbedProgress.overall_progress}%
                        </span>
                      </div>

                      {/* Steps */}
                      <div className="reembed-progress-steps">
                        {reEmbedProgress.steps.map((step, index) => (
                          <div
                            key={step.name}
                            className={`reembed-progress-step ${step.status === 'in_progress' ? 'reembed-progress-step--active' : ''} ${step.status === 'completed' ? 'reembed-progress-step--completed' : ''}`}
                          >
                            <div className="reembed-progress-step-icon">
                              {step.status === 'completed' ? (
                                <CheckCircle size={16} className="step-icon step-icon--completed" />
                              ) : step.status === 'in_progress' ? (
                                <Loader2 size={16} className="step-icon step-icon--progress spinning" />
                              ) : (
                                <Clock size={16} className="step-icon step-icon--pending" />
                              )}
                            </div>
                            <div className="reembed-progress-step-content">
                              <span className="reembed-progress-step-name">
                                {step.name === 're-chunking' && 'Re-chunking Document'}
                                {step.name === 'embedding' && 'Generating Embeddings'}
                                {step.name === 'quality-check' && 'Quality Check'}
                              </span>
                              {step.status === 'in_progress' && (
                                <span className="reembed-progress-step-detail">{step.progress}%</span>
                              )}
                            </div>
                            {index < reEmbedProgress.steps.length - 1 && (
                              <div className={`reembed-progress-step-line ${step.status === 'completed' ? 'reembed-progress-step-line--completed' : ''}`} />
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Current step info */}
                      <div className="reembed-progress-info">
                        <Loader2 size={14} className="spinning" />
                        <span>
                          Processing: {reEmbedProgress.current_step === 're-chunking' && 'Re-chunking Document'}
                          {reEmbedProgress.current_step === 'embedding' && 'Generating Embeddings'}
                          {reEmbedProgress.current_step === 'quality-check' && 'Quality Check'}
                          {reEmbedProgress.current_step === 'completed' && 'Completed'}
                        </span>
                      </div>
                    </div>
                  )}

                  {showReEmbedForm && !isReEmbedding && (
                    <div className="detail-reembed-form">
                      {reEmbedError && (
                        <div className="detail-quality-error">
                          <AlertTriangle size={14} />
                          <span>{reEmbedError}</span>
                        </div>
                      )}

                      <div className="reembed-form-grid">
                        <div className="form-group">
                          <label>Chunk Size (100-4000)</label>
                          <input
                            type="number"
                            value={reEmbedParams.chunk_size}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              chunk_size: Math.max(100, Math.min(4000, Number(e.target.value)))
                            })}
                            min={100}
                            max={4000}
                          />
                          <span className="form-hint">Characters per chunk</span>
                        </div>

                        <div className="form-group">
                          <label>Chunk Overlap (0-500)</label>
                          <input
                            type="number"
                            value={reEmbedParams.chunk_overlap}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              chunk_overlap: Math.max(0, Math.min(500, Number(e.target.value)))
                            })}
                            min={0}
                            max={500}
                          />
                          <span className="form-hint">Overlap between chunks</span>
                        </div>

                        <div className="form-group">
                          <label>Processing Mode</label>
                          <select
                            value={reEmbedParams.processing_mode}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              processing_mode: e.target.value
                            })}
                          >
                            <option value="text_only">Text Only</option>
                            <option value="image_only">Image Only (OCR)</option>
                            <option value="vlm_enhanced">VLM Enhanced</option>
                          </select>
                        </div>
                      </div>

                      <div className="reembed-form-checkboxes">
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={reEmbedParams.enable_vlm}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              enable_vlm: e.target.checked
                            })}
                          />
                          Enable VLM Analysis
                        </label>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={reEmbedParams.extract_tables}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              extract_tables: e.target.checked
                            })}
                          />
                          Extract Tables
                        </label>
                        <label className="checkbox-label">
                          <input
                            type="checkbox"
                            checked={reEmbedParams.extract_images}
                            onChange={(e) => setReEmbedParams({
                              ...reEmbedParams,
                              extract_images: e.target.checked
                            })}
                          />
                          Extract Images
                        </label>
                      </div>

                      <div className="reembed-form-info">
                        <AlertCircle size={14} />
                        <span>
                          Re-embedding will delete existing chunks and embeddings, then create new ones
                          with the specified parameters. This process may take several minutes.
                        </span>
                      </div>

                      <div className="reembed-form-actions">
                        <button
                          className="btn btn--secondary"
                          onClick={() => setShowReEmbedForm(false)}
                        >
                          Cancel
                        </button>
                        <button
                          className="btn btn--primary"
                          onClick={runReEmbed}
                          disabled={reEmbedLoading}
                        >
                          {reEmbedLoading ? (
                            <>
                              <Loader2 size={14} className="spinning" />
                              Processing...
                            </>
                          ) : (
                            <>
                              <RefreshCw size={14} />
                              Start Re-embedding
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}

                  {!showReEmbedForm && !isReEmbedding && (
                    <div className="detail-reembed-hint">
                      <p>
                        If embedding quality is poor, you can re-embed the document with different
                        chunk sizes and processing options to improve retrieval accuracy.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </div>
        <div className="modal-footer">
          <button className="btn btn--secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// Document Upload Modal
// =============================================================================

interface UploadModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

interface UploadStep {
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progress: number;
}

interface UploadProgress {
  current_step: string;
  steps: UploadStep[];
  overall_progress: number;
}

interface UploadStatus {
  task_id: string;
  document_id: string;
  status: 'processing' | 'ready' | 'error';
  progress: UploadProgress;
  started_at: string;
  estimated_completion?: string;
}

// Supported file extensions for document upload
const SUPPORTED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.md', '.csv', '.json', '.png', '.jpg', '.jpeg', '.gif', '.html'];

const DocumentUploadModal: React.FC<UploadModalProps> = ({ onClose, onSuccess }) => {
  const [files, setFiles] = useState<File[]>([]);
  const [language, setLanguage] = useState('auto');
  const [processingMode, setProcessingMode] = useState('text_only');
  const [enableVlm, setEnableVlm] = useState(false);
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Progress tracking state
  const [uploadStatus, setUploadStatus] = useState<UploadStatus | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Batch upload progress
  const [currentFileIndex, setCurrentFileIndex] = useState(0);
  const [totalFiles, setTotalFiles] = useState(0);
  const [uploadResults, setUploadResults] = useState<{success: number; failed: number}>({success: 0, failed: 0});

  // Refs for file inputs
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const isValidFile = (file: File): boolean => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    return SUPPORTED_EXTENSIONS.includes(ext);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files);
    const validFiles = droppedFiles.filter(isValidFile);

    if (validFiles.length === 0) {
      setError('No valid files found. Supported formats: PDF, Word, Excel, PowerPoint, Text, Images');
      return;
    }

    setFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      const newFiles = validFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...newFiles];
    });
    setError(null);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const validFiles = Array.from(selectedFiles).filter(isValidFile);

    if (validFiles.length === 0) {
      setError('No valid files found. Supported formats: PDF, Word, Excel, PowerPoint, Text, Images');
      return;
    }

    setFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      const newFiles = validFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...newFiles];
    });
    setError(null);

    // Reset input value to allow selecting same files again
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleFolderSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    const validFiles = Array.from(selectedFiles).filter(isValidFile);

    if (validFiles.length === 0) {
      setError('No valid files found in folder. Supported formats: PDF, Word, Excel, PowerPoint, Text, Images');
      return;
    }

    setFiles(prev => {
      const existingNames = new Set(prev.map(f => f.name));
      const newFiles = validFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...newFiles];
    });
    setError(null);

    // Reset input value
    if (folderInputRef.current) {
      folderInputRef.current.value = '';
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const clearAllFiles = () => {
    setFiles([]);
  };

  // Upload a single file and return task_id
  const uploadSingleFile = async (file: File): Promise<string | null> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', file.name.replace(/\.[^/.]+$/, ''));
    formData.append('language', language);
    formData.append('processing_mode', processingMode);
    formData.append('enable_vlm', enableVlm.toString());
    if (tags) formData.append('tags', tags);

    const response = await fetch('/api/v1/documents', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error?.message || `Upload failed: HTTP ${response.status}`);
    }

    const result = await response.json();
    return result.data?.task_id || null;
  };

  // Wait for task to complete
  const waitForTaskCompletion = async (taskId: string): Promise<boolean> => {
    return new Promise((resolve) => {
      const poll = async () => {
        try {
          const response = await fetch(`/api/v1/documents/upload-status/${taskId}`, {
            credentials: 'include',
          });

          if (!response.ok) {
            resolve(false);
            return;
          }

          const result = await response.json();
          const status = result.data as UploadStatus;
          setUploadStatus(status);

          if (status.status === 'ready' || status.progress.overall_progress >= 100) {
            resolve(true);
          } else if (status.status === 'error') {
            resolve(false);
          } else {
            setTimeout(poll, 800);
          }
        } catch (err) {
          console.error('Error polling status:', err);
          resolve(false);
        }
      };
      poll();
    });
  };

  const handleUpload = async () => {
    if (files.length === 0) {
      setError('Please select files to upload');
      return;
    }

    setUploading(true);
    setIsProcessing(true);
    setError(null);
    setTotalFiles(files.length);
    setCurrentFileIndex(0);
    setUploadResults({ success: 0, failed: 0 });

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setCurrentFileIndex(i);

      // Initialize progress display for current file
      setUploadStatus({
        task_id: '',
        document_id: '',
        status: 'processing',
        progress: {
          current_step: 'uploading',
          steps: [
            { name: 'uploading', status: 'in_progress', progress: 0 },
            { name: 'parsing', status: 'pending', progress: 0 },
            { name: 'chunking', status: 'pending', progress: 0 },
            { name: 'embedding', status: 'pending', progress: 0 },
          ],
          overall_progress: 0,
        },
        started_at: new Date().toISOString(),
      });

      try {
        const taskId = await uploadSingleFile(file);

        if (taskId) {
          // Update upload step as completed
          setUploadStatus(prev => prev ? {
            ...prev,
            task_id: taskId,
            progress: {
              ...prev.progress,
              steps: prev.progress.steps.map(s =>
                s.name === 'uploading' ? { ...s, status: 'completed', progress: 100 } : s
              ),
              overall_progress: 10,
            }
          } : prev);

          const success = await waitForTaskCompletion(taskId);
          if (success) {
            successCount++;
          } else {
            failCount++;
          }
        } else {
          successCount++;
        }
      } catch (err) {
        console.error(`Failed to upload ${file.name}:`, err);
        failCount++;
      }

      setUploadResults({ success: successCount, failed: failCount });
    }

    setUploading(false);
    setIsProcessing(false);

    // Show completion message briefly then close
    if (successCount > 0) {
      setTimeout(() => {
        onSuccess();
      }, 1000);
    } else {
      setError(`All ${failCount} file(s) failed to upload`);
      setUploading(false);
    }
  };

  const getStepIcon = (step: UploadStep) => {
    switch (step.status) {
      case 'completed':
        return <CheckCircle size={16} className="step-icon step-icon--completed" />;
      case 'in_progress':
        return <Loader2 size={16} className="step-icon step-icon--progress spinning" />;
      case 'failed':
        return <XCircle size={16} className="step-icon step-icon--failed" />;
      default:
        return <Clock size={16} className="step-icon step-icon--pending" />;
    }
  };

  const getStepLabel = (stepName: string) => {
    const labels: Record<string, string> = {
      uploading: 'Uploading',
      parsing: 'Parsing Document',
      chunking: 'Creating Chunks',
      embedding: 'Generating Embeddings',
    };
    return labels[stepName] || stepName;
  };

  return (
    <div className="modal-overlay" onClick={isProcessing ? undefined : onClose}>
      <div className="modal-content modal-content--large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isProcessing ? `Processing Documents (${currentFileIndex + 1}/${totalFiles})` : 'Upload Documents'}</h2>
          {!isProcessing && (
            <button className="modal-close" onClick={onClose}>
              <X size={20} />
            </button>
          )}
        </div>
        <div className="modal-body">
          {error && <div className="modal-error">{error}</div>}

          {/* Progress View - shown during processing */}
          {isProcessing && uploadStatus && (
            <div className="upload-progress-container">
              {/* Batch progress header */}
              {totalFiles > 1 && (
                <div className="upload-batch-progress">
                  <div className="upload-batch-progress-header">
                    <span>Overall Progress: {currentFileIndex + 1} of {totalFiles} files</span>
                    <span className="upload-batch-stats">
                      <CheckCircle size={14} className="text-success" /> {uploadResults.success} succeeded
                      {uploadResults.failed > 0 && (
                        <> | <XCircle size={14} className="text-error" /> {uploadResults.failed} failed</>
                      )}
                    </span>
                  </div>
                  <div className="upload-progress-bar">
                    <div
                      className="upload-progress-bar-fill"
                      style={{ width: `${((currentFileIndex) / totalFiles) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Current file info */}
              <div className="upload-progress-file">
                <FileText size={24} />
                <div className="upload-progress-file-info">
                  <span className="upload-progress-filename">{files[currentFileIndex]?.name || 'Processing...'}</span>
                  <span className="upload-progress-status">
                    {uploadStatus.status === 'ready' ? 'Completed' : 'Processing...'}
                  </span>
                </div>
              </div>

              {/* Current file progress bar */}
              <div className="upload-progress-bar-container">
                <div className="upload-progress-bar">
                  <div
                    className="upload-progress-bar-fill"
                    style={{ width: `${uploadStatus.progress.overall_progress}%` }}
                  />
                </div>
                <span className="upload-progress-percentage">
                  {uploadStatus.progress.overall_progress}%
                </span>
              </div>

              {/* Steps */}
              <div className="upload-progress-steps">
                {uploadStatus.progress.steps.map((step, index) => (
                  <div
                    key={step.name}
                    className={`upload-progress-step ${step.status === 'in_progress' ? 'upload-progress-step--active' : ''} ${step.status === 'completed' ? 'upload-progress-step--completed' : ''}`}
                  >
                    <div className="upload-progress-step-icon">
                      {getStepIcon(step)}
                    </div>
                    <div className="upload-progress-step-content">
                      <span className="upload-progress-step-name">{getStepLabel(step.name)}</span>
                      {step.status === 'in_progress' && (
                        <span className="upload-progress-step-detail">{step.progress}%</span>
                      )}
                    </div>
                    {index < uploadStatus.progress.steps.length - 1 && (
                      <div className={`upload-progress-step-line ${step.status === 'completed' ? 'upload-progress-step-line--completed' : ''}`} />
                    )}
                  </div>
                ))}
              </div>

              {/* Current step info */}
              <div className="upload-progress-info">
                <Clock size={14} />
                <span>
                  Current step: {getStepLabel(uploadStatus.progress.current_step)}
                </span>
              </div>
            </div>
          )}

          {/* Upload Form - hidden during processing */}
          {!isProcessing && (
            <>
              {/* Drop Zone */}
              <div
                className={`upload-dropzone ${dragOver ? 'upload-dropzone--active' : ''} ${files.length > 0 ? 'upload-dropzone--has-file' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                <input
                  ref={fileInputRef}
                  id="file-input"
                  type="file"
                  multiple
                  onChange={handleFileSelect}
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.gif,.html"
                  style={{ display: 'none' }}
                />
                <input
                  ref={folderInputRef}
                  id="folder-input"
                  type="file"
                  {...{ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>}
                  multiple
                  onChange={handleFolderSelect}
                  style={{ display: 'none' }}
                />
                {files.length === 0 ? (
                  <>
                    <Upload size={40} strokeWidth={1} />
                    <p>Drag & drop files here</p>
                    <span className="upload-hint">
                      Supports: PDF, Word, Excel, PowerPoint, Text, Images
                    </span>
                    <div className="upload-buttons">
                      <button
                        className="btn btn--secondary btn--sm"
                        onClick={(e) => { e.stopPropagation(); fileInputRef.current?.click(); }}
                      >
                        <Upload size={14} />
                        Select Files
                      </button>
                      <button
                        className="btn btn--secondary btn--sm"
                        onClick={(e) => { e.stopPropagation(); folderInputRef.current?.click(); }}
                      >
                        <FolderOpen size={14} />
                        Select Folder
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="upload-file-list-container" onClick={(e) => e.stopPropagation()}>
                    <div className="upload-file-list-header">
                      <span>{files.length} file(s) selected</span>
                      <div className="upload-file-list-actions">
                        <button
                          className="btn btn--ghost btn--sm"
                          onClick={() => fileInputRef.current?.click()}
                        >
                          <Plus size={14} />
                          Add Files
                        </button>
                        <button
                          className="btn btn--ghost btn--sm"
                          onClick={() => folderInputRef.current?.click()}
                        >
                          <FolderOpen size={14} />
                          Add Folder
                        </button>
                        <button
                          className="btn btn--ghost btn--sm text-error"
                          onClick={clearAllFiles}
                        >
                          <Trash2 size={14} />
                          Clear All
                        </button>
                      </div>
                    </div>
                    <div className="upload-file-list">
                      {files.map((file, index) => (
                        <div key={`${file.name}-${index}`} className="upload-file-item">
                          <FileText size={16} />
                          <span className="upload-file-item-name" title={file.name}>{file.name}</span>
                          <span className="upload-file-item-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                          <button
                            className="upload-file-item-remove"
                            onClick={() => removeFile(index)}
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Upload Options */}
              <div className="upload-options">
                <div className="form-row">
                  <div className="form-group">
                    <label>Language</label>
                    <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                      <option value="auto">Auto Detect</option>
                      <option value="ko">Korean</option>
                      <option value="en">English</option>
                      <option value="ja">Japanese</option>
                      <option value="zh">Chinese</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Processing Mode</label>
                    <select value={processingMode} onChange={(e) => setProcessingMode(e.target.value)}>
                      <option value="text_only">Text Only</option>
                      <option value="image_only">Image Only (OCR)</option>
                      <option value="vlm_enhanced">VLM Enhanced</option>
                    </select>
                  </div>
                </div>

                <div className="form-group">
                  <label>Tags (comma separated)</label>
                  <input
                    type="text"
                    value={tags}
                    onChange={(e) => setTags(e.target.value)}
                    placeholder="e.g., manual, guide, internal"
                  />
                </div>

                <div className="form-group form-group--checkbox">
                  <label>
                    <input
                      type="checkbox"
                      checked={enableVlm}
                      onChange={(e) => setEnableVlm(e.target.checked)}
                    />
                    Enable VLM Analysis (images, charts, tables)
                  </label>
                </div>
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          {isProcessing ? (
            <div className="upload-progress-footer">
              <span className="upload-progress-footer-text">
                Processing {currentFileIndex + 1} of {totalFiles} documents...
              </span>
            </div>
          ) : (
            <>
              <button className="btn btn--secondary" onClick={onClose} disabled={uploading}>
                Cancel
              </button>
              <button className="btn btn--primary" onClick={handleUpload} disabled={uploading || files.length === 0}>
                {uploading ? (
                  <>
                    <Loader2 size={16} className="spinning" />
                    Uploading...
                  </>
                ) : (
                  <>
                    <Upload size={16} />
                    Upload
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// RAG Profiles Tab
// =============================================================================

interface ProfilesTabProps {
  onRefresh: () => void;
}

const ProfilesTab: React.FC<ProfilesTabProps> = ({ onRefresh }) => {
  const [profiles, setProfiles] = useState<RAGProfileSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const limit = 10;

  const fetchProfiles = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
        include_inactive: 'true',
      });

      const response = await fetch(`/api/v1/rag-config/profiles?${params}`, {
        credentials: 'include',
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      setProfiles(result.data.profiles);
      setTotalPages(result.pagination.total_pages);
    } catch (err) {
      console.error('Failed to fetch profiles:', err);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchProfiles();
  }, [fetchProfiles]);

  const handleActivate = async (profileId: string) => {
    try {
      const response = await fetch(`/api/v1/rag-config/profiles/${profileId}/activate?traffic_percentage=100`, {
        method: 'POST',
        credentials: 'include',
      });

      if (response.ok) {
        fetchProfiles();
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to activate profile:', err);
    }
  };

  const handleClone = async (profileId: string, name: string) => {
    const newName = prompt('Enter name for cloned profile:', `${name}-copy`);
    if (!newName) return;

    try {
      const response = await fetch(`/api/v1/rag-config/profiles/${profileId}/clone?new_name=${encodeURIComponent(newName)}`, {
        method: 'POST',
        credentials: 'include',
      });

      if (response.ok) {
        fetchProfiles();
        onRefresh();
      }
    } catch (err) {
      console.error('Failed to clone profile:', err);
    }
  };

  const filteredProfiles = profiles.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) ||
      (p.description && p.description.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="profiles-tab">
      {/* Header */}
      <div className="profiles-header">
        <div className="profiles-search">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search profiles..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button className="documents-btn documents-btn--primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} />
          New Profile
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="documents-loading">
          <Loader2 className="spinning" size={24} />
          <span>Loading profiles...</span>
        </div>
      ) : (
        <>
          <div className="profiles-table-container">
            <table className="profiles-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Version</th>
                  <th>Strategy</th>
                  <th>Chunk Size</th>
                  <th>Traffic</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredProfiles.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="profiles-empty">
                      No profiles found
                    </td>
                  </tr>
                ) : (
                  filteredProfiles.map((profile) => (
                    <tr key={profile.id}>
                      <td>
                        <div className="profile-name-cell">
                          <span className="profile-name">{profile.name}</span>
                          {profile.description && (
                            <span className="profile-desc">{profile.description}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <span className="version-badge">v{profile.embedding_version}</span>
                      </td>
                      <td>
                        <span
                          className="strategy-badge"
                          style={{ backgroundColor: STRATEGY_COLORS[profile.retrieval_strategy] || '#9ca3af' }}
                        >
                          {profile.retrieval_strategy}
                        </span>
                      </td>
                      <td>{profile.chunk_size}</td>
                      <td>{profile.traffic_percentage}%</td>
                      <td>
                        <span
                          className="status-badge"
                          style={{
                            backgroundColor: profile.is_active ? STATUS_COLORS.active.bg : STATUS_COLORS.draft.bg,
                            color: profile.is_active ? STATUS_COLORS.active.text : STATUS_COLORS.draft.text,
                          }}
                        >
                          {profile.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <div className="profile-actions">
                          {!profile.is_active && (
                            <button
                              className="action-btn action-btn--success"
                              onClick={() => handleActivate(profile.id)}
                              title="Activate"
                            >
                              <Check size={14} />
                            </button>
                          )}
                          <button
                            className="action-btn action-btn--edit"
                            onClick={() => handleClone(profile.id, profile.name)}
                            title="Clone"
                          >
                            <Copy size={14} />
                          </button>
                          <button className="action-btn action-btn--edit" title="Edit">
                            <Edit size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="profiles-pagination">
              <button
                className="pagination-btn"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                <ChevronLeft size={18} />
                Previous
              </button>
              <span className="pagination-info">
                Page {page} of {totalPages}
              </span>
              <button
                className="pagination-btn"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </>
      )}

      {/* Create Modal (placeholder) */}
      {showCreateModal && (
        <ProfileCreateModal onClose={() => setShowCreateModal(false)} onCreated={() => { fetchProfiles(); onRefresh(); setShowCreateModal(false); }} />
      )}
    </div>
  );
};

// =============================================================================
// Profile Create Modal
// =============================================================================

interface ProfileCreateModalProps {
  onClose: () => void;
  onCreated: () => void;
}

const ProfileCreateModal: React.FC<ProfileCreateModalProps> = ({ onClose, onCreated }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [chunkSize, setChunkSize] = useState(512);
  const [chunkOverlap, setChunkOverlap] = useState(80);
  const [strategy, setStrategy] = useState('hybrid');
  const [topK, setTopK] = useState(5);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError('Name is required');
      return;
    }

    try {
      setSaving(true);
      setError(null);

      const response = await fetch('/api/v1/rag-config/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
          chunking: {
            strategy: 'semantic',
            chunk_size: chunkSize,
            chunk_overlap: chunkOverlap,
            min_chunk_size: 100,
            max_chunk_size: 1000,
            language: 'auto',
          },
          retrieval: {
            strategy,
            top_k: topK,
            score_threshold: 0.7,
            hybrid_alpha: 0.5,
          },
        }),
      });

      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.error?.message || `HTTP ${response.status}`);
      }

      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create profile');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create RAG Profile</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="modal-error">{error}</div>}

            <div className="form-group">
              <label>Profile Name *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g., manual-v1"
                autoFocus
              />
            </div>

            <div className="form-group">
              <label>Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe this profile's purpose..."
                rows={2}
              />
            </div>

            <div className="form-section">
              <h4>Chunking Settings</h4>
              <div className="form-row">
                <div className="form-group">
                  <label>Chunk Size</label>
                  <input
                    type="number"
                    value={chunkSize}
                    onChange={(e) => setChunkSize(Number(e.target.value))}
                    min={100}
                    max={4000}
                  />
                </div>
                <div className="form-group">
                  <label>Chunk Overlap</label>
                  <input
                    type="number"
                    value={chunkOverlap}
                    onChange={(e) => setChunkOverlap(Number(e.target.value))}
                    min={0}
                    max={500}
                  />
                </div>
              </div>
            </div>

            <div className="form-section">
              <h4>Retrieval Settings</h4>
              <div className="form-row">
                <div className="form-group">
                  <label>Strategy</label>
                  <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                    <option value="vector">Vector</option>
                    <option value="graph">Graph</option>
                    <option value="hybrid">Hybrid</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Top K</label>
                  <input
                    type="number"
                    value={topK}
                    onChange={(e) => setTopK(Number(e.target.value))}
                    min={1}
                    max={50}
                  />
                </div>
              </div>
            </div>

            <div className="form-warning">
              <AlertTriangle size={16} />
              <span>Creating a new profile increments the embedding version. Existing documents will continue using the previous version.</span>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="documents-btn documents-btn--secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="documents-btn documents-btn--primary" disabled={saving}>
              {saving ? (
                <>
                  <Loader2 className="spinning" size={16} />
                  Creating...
                </>
              ) : (
                <>
                  <Plus size={16} />
                  Create Profile
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// =============================================================================
// Experiments Tab
// =============================================================================

interface ExperimentsTabProps {
  onRefresh: () => void;
}

const ExperimentsTab: React.FC<ExperimentsTabProps> = ({ onRefresh }) => {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchExperiments = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/rag-config/experiments?limit=20', {
        credentials: 'include',
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const result = await response.json();
      setExperiments(result.data.experiments);
    } catch (err) {
      console.error('Failed to fetch experiments:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchExperiments();
  }, [fetchExperiments]);

  const handleStatusChange = async (experimentId: string, action: 'start' | 'stop') => {
    try {
      const response = await fetch(`/api/v1/rag-config/experiments/${experimentId}/${action}`, {
        method: 'POST',
        credentials: 'include',
      });

      if (response.ok) {
        fetchExperiments();
        onRefresh();
      }
    } catch (err) {
      console.error(`Failed to ${action} experiment:`, err);
    }
  };

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

  return (
    <div className="experiments-tab">
      <div className="experiments-header">
        <h3>A/B Testing Experiments</h3>
        <button className="documents-btn documents-btn--primary">
          <Plus size={16} />
          New Experiment
        </button>
      </div>

      {loading ? (
        <div className="documents-loading">
          <Loader2 className="spinning" size={24} />
          <span>Loading experiments...</span>
        </div>
      ) : experiments.length === 0 ? (
        <div className="experiments-empty">
          <FlaskConical size={48} strokeWidth={1} />
          <h4>No Experiments Yet</h4>
          <p>Create an A/B experiment to compare RAG profiles</p>
        </div>
      ) : (
        <div className="experiments-list">
          {experiments.map((exp) => (
            <div key={exp.id} className="experiment-card">
              <div className="experiment-header">
                <div className="experiment-info">
                  <h4>{exp.name}</h4>
                  <span
                    className="status-badge"
                    style={{
                      backgroundColor: STATUS_COLORS[exp.status]?.bg || '#f3f4f6',
                      color: STATUS_COLORS[exp.status]?.text || '#374151',
                    }}
                  >
                    {exp.status}
                  </span>
                </div>
                <div className="experiment-actions">
                  {exp.status === 'draft' && (
                    <button
                      className="documents-btn documents-btn--success"
                      onClick={() => handleStatusChange(exp.id, 'start')}
                    >
                      <Play size={14} />
                      Start
                    </button>
                  )}
                  {exp.status === 'active' && (
                    <button
                      className="documents-btn documents-btn--warning"
                      onClick={() => handleStatusChange(exp.id, 'stop')}
                    >
                      <Pause size={14} />
                      Stop
                    </button>
                  )}
                </div>
              </div>
              <div className="experiment-details">
                <div className="experiment-stat">
                  <span className="stat-label">Baseline</span>
                  <span className="stat-value">{exp.baseline_profile_name}</span>
                </div>
                <div className="experiment-stat">
                  <span className="stat-label">Variants</span>
                  <span className="stat-value">{exp.variant_count}</span>
                </div>
                <div className="experiment-stat">
                  <span className="stat-label">Queries</span>
                  <span className="stat-value">{exp.total_queries.toLocaleString()}</span>
                </div>
                <div className="experiment-stat">
                  <span className="stat-label">Started</span>
                  <span className="stat-value">{formatDate(exp.started_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// =============================================================================
// Metrics Tab
// =============================================================================

const MetricsTab: React.FC = () => {
  const [metrics, setMetrics] = useState<ProfileMetrics[]>([]);
  const [loading, setLoading] = useState(true);

  // Mock data for demonstration
  useEffect(() => {
    // Simulate loading metrics
    setTimeout(() => {
      setMetrics([
        {
          profile_id: '1',
          profile_name: 'default',
          total_queries: 1250,
          success_rate: 0.92,
          avg_latency_ms: 450,
          avg_similarity_score: 0.78,
          satisfaction_rate: 0.85,
        },
        {
          profile_id: '2',
          profile_name: 'manual-v1',
          total_queries: 830,
          success_rate: 0.95,
          avg_latency_ms: 380,
          avg_similarity_score: 0.82,
          satisfaction_rate: 0.89,
        },
      ]);
      setLoading(false);
    }, 500);
  }, []);

  if (loading) {
    return (
      <div className="documents-loading">
        <Loader2 className="spinning" size={24} />
        <span>Loading metrics...</span>
      </div>
    );
  }

  return (
    <div className="metrics-tab">
      <h3>Retrieval Quality Metrics</h3>

      <div className="metrics-grid">
        {/* Profile Comparison Chart */}
        <div className="metrics-chart-card">
          <h4>Profile Comparison</h4>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={metrics} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <YAxis dataKey="profile_name" type="category" width={100} />
              <Tooltip
                formatter={(value: number) => `${(value * 100).toFixed(1)}%`}
                contentStyle={{ backgroundColor: 'var(--color-bg-elevated)', borderRadius: '8px' }}
              />
              <Legend />
              <Bar dataKey="success_rate" name="Success Rate" fill="#22c55e" />
              <Bar dataKey="satisfaction_rate" name="Satisfaction" fill="#6366f1" />
              <Bar dataKey="avg_similarity_score" name="Similarity" fill="#8b5cf6" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Latency Distribution */}
        <div className="metrics-chart-card">
          <h4>Average Latency (ms)</h4>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={metrics}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="profile_name" />
              <YAxis />
              <Tooltip
                formatter={(value: number) => `${value}ms`}
                contentStyle={{ backgroundColor: 'var(--color-bg-elevated)', borderRadius: '8px' }}
              />
              <Bar dataKey="avg_latency_ms" name="Latency" fill="#f59e0b" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Metrics Table */}
      <div className="metrics-table-container">
        <table className="metrics-table">
          <thead>
            <tr>
              <th>Profile</th>
              <th>Queries</th>
              <th>Success Rate</th>
              <th>Avg Latency</th>
              <th>Similarity</th>
              <th>Satisfaction</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.profile_id}>
                <td>{m.profile_name}</td>
                <td>{m.total_queries.toLocaleString()}</td>
                <td>{(m.success_rate * 100).toFixed(1)}%</td>
                <td>{m.avg_latency_ms}ms</td>
                <td>{(m.avg_similarity_score * 100).toFixed(1)}%</td>
                <td>{(m.satisfaction_rate * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default DocumentsPage;
