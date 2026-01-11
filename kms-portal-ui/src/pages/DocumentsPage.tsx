/**
 * Documents & RAG Governance Page
 *
 * Unified page for document management and RAG configuration.
 * Follows AdminDashboardPage tab pattern.
 */

import React, { useState, useEffect, useCallback } from 'react';
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
} from 'lucide-react';
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

// =============================================================================
// Types
// =============================================================================

type TabId = 'documents' | 'profiles' | 'experiments' | 'metrics';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

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

// =============================================================================
// Constants
// =============================================================================

const TABS: TabConfig[] = [
  { id: 'documents', label: 'Documents', icon: <FileText size={18} /> },
  { id: 'profiles', label: 'RAG Profiles', icon: <Settings size={18} /> },
  { id: 'experiments', label: 'A/B Tests', icon: <FlaskConical size={18} /> },
  { id: 'metrics', label: 'Metrics', icon: <TrendingUp size={18} /> },
];

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
  const [activeTab, setActiveTab] = useState<TabId>('profiles');
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<RAGConfigOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

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
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`documents-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
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
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<DocumentListItem | null>(null);
  const limit = 15;

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
        return (
          <span className="doc-status-badge doc-status-badge--completed">
            <CheckCircle size={12} /> Completed
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
        return (
          <span className="doc-status-badge doc-status-badge--failed">
            <XCircle size={12} /> Failed
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
              <option value="completed">Completed</option>
              <option value="processing">Processing</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
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
                            onClick={() => window.open(`/api/v1/documents/${doc.id}`, '_blank')}
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

const DocumentUploadModal: React.FC<UploadModalProps> = ({ onClose, onSuccess }) => {
  const [file, setFile] = useState<File | null>(null);
  const [displayName, setDisplayName] = useState('');
  const [language, setLanguage] = useState('auto');
  const [processingMode, setProcessingMode] = useState('text_only');
  const [enableVlm, setEnableVlm] = useState(false);
  const [tags, setTags] = useState('');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      setFile(droppedFile);
      if (!displayName) {
        setDisplayName(droppedFile.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      if (!displayName) {
        setDisplayName(selectedFile.name.replace(/\.[^/.]+$/, ''));
      }
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file to upload');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      if (displayName) formData.append('name', displayName);
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

      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-content--medium" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Upload Document</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        <div className="modal-body">
          {error && <div className="modal-error">{error}</div>}

          {/* Drop Zone */}
          <div
            className={`upload-dropzone ${dragOver ? 'upload-dropzone--active' : ''} ${file ? 'upload-dropzone--has-file' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-input')?.click()}
          >
            <input
              id="file-input"
              type="file"
              onChange={handleFileSelect}
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.gif,.html"
              style={{ display: 'none' }}
            />
            {file ? (
              <div className="upload-file-preview">
                <FileText size={32} />
                <div className="upload-file-info">
                  <span className="upload-file-name">{file.name}</span>
                  <span className="upload-file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                </div>
                <button
                  className="upload-file-remove"
                  onClick={(e) => { e.stopPropagation(); setFile(null); }}
                >
                  <X size={16} />
                </button>
              </div>
            ) : (
              <>
                <Upload size={40} strokeWidth={1} />
                <p>Drag & drop a file here, or click to browse</p>
                <span className="upload-hint">
                  Supports: PDF, Word, Excel, PowerPoint, Text, Images
                </span>
              </>
            )}
          </div>

          {/* Upload Options */}
          <div className="upload-options">
            <div className="form-group">
              <label>Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Optional display name"
              />
            </div>

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
                  <option value="vlm_enhanced">VLM Enhanced</option>
                  <option value="multimodal">Full Multimodal</option>
                  <option value="ocr">OCR (Scanned)</option>
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
        </div>
        <div className="modal-footer">
          <button className="btn btn--secondary" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button className="btn btn--primary" onClick={handleUpload} disabled={uploading || !file}>
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
