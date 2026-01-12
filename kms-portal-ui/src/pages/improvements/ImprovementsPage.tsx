/**
 * Improvements Page
 *
 * Main page for viewing and managing enhancement requests
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  RefreshCw,
  ChevronRight,
  Bot,
  Clock,
  User,
  AlertCircle,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import { useAuthStore } from '../../store/authStore';
import {
  listEnhancements,
  getDashboardStats,
  EnhancementListItem,
  EnhancementDashboardStats,
  EnhancementStatus,
  EnhancementType,
  EnhancementPriority,
} from '../../api/improvements.api';
import './ImprovementsPage.css';

// Status color mapping
const STATUS_COLORS: Record<EnhancementStatus, string> = {
  submitted: 'status-submitted',
  analyzing: 'status-analyzing',
  analyzed: 'status-analyzed',
  architecture_review: 'status-review',
  approved: 'status-approved',
  rejected: 'status-rejected',
  implementing: 'status-implementing',
  code_review: 'status-review',
  testing: 'status-testing',
  verified: 'status-verified',
  released: 'status-released',
  closed: 'status-closed',
};

// Priority color mapping
const PRIORITY_COLORS: Record<EnhancementPriority, string> = {
  critical: 'priority-critical',
  high: 'priority-high',
  medium: 'priority-medium',
  low: 'priority-low',
};

// Type icon mapping
const TYPE_ICONS: Record<EnhancementType, string> = {
  feature: '✨',
  bug_fix: '🐛',
  improvement: '📈',
  refactor: '🔧',
  documentation: '📝',
  security: '🔒',
  performance: '⚡',
};

export const ImprovementsPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user: _user } = useAuthStore();

  // State
  const [items, setItems] = useState<EnhancementListItem[]>([]);
  const [stats, setStats] = useState<EnhancementDashboardStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<EnhancementStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<EnhancementType | ''>('');
  const [priorityFilter, setPriorityFilter] = useState<EnhancementPriority | ''>('');
  const [myRequestsOnly, setMyRequestsOnly] = useState(false);

  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // Load data
  const loadData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const [enhancementsResult, statsResult] = await Promise.all([
        listEnhancements({
          page,
          limit: 20,
          status: statusFilter || undefined,
          type: typeFilter || undefined,
          priority: priorityFilter || undefined,
          my_requests: myRequestsOnly,
          search: searchQuery || undefined,
        }),
        getDashboardStats(),
      ]);

      setItems(enhancementsResult.items);
      setTotalPages(enhancementsResult.pagination.total_pages);
      setTotalItems(enhancementsResult.pagination.total_items);
      setStats(statsResult);
    } catch (err) {
      setError(t('improvements.errors.loadFailed'));
      console.error('Failed to load enhancements:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [page, statusFilter, typeFilter, priorityFilter, myRequestsOnly, searchQuery]);

  // Format date
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffHours < 1) return t('improvements.timeline.created');
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="improvements-page">
      {/* Header */}
      <div className="improvements-header">
        <div className="header-content">
          <h1>{t('improvements.title')}</h1>
          <p>{t('improvements.description')}</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => navigate('/improvements/submit')}
        >
          <Plus size={18} />
          {t('improvements.submit')}
        </button>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-value">{stats.total_requests}</div>
            <div className="stat-label">{t('improvements.dashboard.total')}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.ai_analyzed_count}</div>
            <div className="stat-label">{t('improvements.dashboard.analyzed')}</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.implemented_count}</div>
            <div className="stat-label">{t('improvements.dashboard.implemented')}</div>
          </div>
          <div className="stat-card status-breakdown">
            <div className="stat-label">{t('improvements.dashboard.byStatus')}</div>
            <div className="status-bars">
              {Object.entries(stats.by_status).slice(0, 4).map(([status, count]) => (
                <div key={status} className="status-bar-item">
                  <span className={`status-dot ${STATUS_COLORS[status as EnhancementStatus] || ''}`} />
                  <span className="status-name">{t(`improvements.status.${status}`)}</span>
                  <span className="status-count">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="filters-section">
        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder={t('improvements.filters.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as EnhancementStatus | '')}
          >
            <option value="">{t('improvements.filters.status')}</option>
            {['submitted', 'analyzing', 'analyzed', 'approved', 'implementing', 'testing', 'verified', 'released'].map(
              (status) => (
                <option key={status} value={status}>
                  {t(`improvements.status.${status}`)}
                </option>
              )
            )}
          </select>

          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value as EnhancementType | '')}
          >
            <option value="">{t('improvements.filters.type')}</option>
            {['feature', 'bug_fix', 'improvement', 'refactor', 'documentation', 'security', 'performance'].map(
              (type) => (
                <option key={type} value={type}>
                  {t(`improvements.types.${type}`)}
                </option>
              )
            )}
          </select>

          <select
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value as EnhancementPriority | '')}
          >
            <option value="">{t('improvements.filters.priority')}</option>
            {['critical', 'high', 'medium', 'low'].map((priority) => (
              <option key={priority} value={priority}>
                {t(`improvements.priority.${priority}`)}
              </option>
            ))}
          </select>

          <label className="checkbox-filter">
            <input
              type="checkbox"
              checked={myRequestsOnly}
              onChange={(e) => setMyRequestsOnly(e.target.checked)}
            />
            {t('improvements.filters.myRequests')}
          </label>
        </div>

        <button className="btn-icon" onClick={loadData} title={t('common.refresh')}>
          <RefreshCw size={18} />
        </button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="loading-state">
          <div className="spinner" />
          <p>{t('common.loading')}</p>
        </div>
      ) : error ? (
        <div className="error-state">
          <AlertCircle size={48} />
          <p>{error}</p>
          <button className="btn-secondary" onClick={loadData}>
            {t('common.refresh')}
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">💡</div>
          <h3>{t('improvements.noRequests')}</h3>
          <p>{t('improvements.createFirst')}</p>
          <button
            className="btn-primary"
            onClick={() => navigate('/improvements/submit')}
          >
            <Plus size={18} />
            {t('improvements.submit')}
          </button>
        </div>
      ) : (
        <>
          {/* List */}
          <div className="improvements-list">
            {items.map((item) => (
              <div
                key={item.id}
                className="improvement-card"
                onClick={() => navigate(`/improvements/${item.id}`)}
              >
                <div className="card-header">
                  <div className="card-title">
                    {item.type && (
                      <span className="type-icon">{TYPE_ICONS[item.type]}</span>
                    )}
                    <h3>{item.title}</h3>
                  </div>
                  <ChevronRight size={20} className="chevron" />
                </div>

                <div className="card-meta">
                  <span className={`status-badge ${STATUS_COLORS[item.status]}`}>
                    {t(`improvements.status.${item.status}`)}
                  </span>
                  {item.priority && (
                    <span className={`priority-badge ${PRIORITY_COLORS[item.priority]}`}>
                      {t(`improvements.priority.${item.priority}`)}
                    </span>
                  )}
                  {item.ai_analyzed && (
                    <span className="ai-badge">
                      <Bot size={14} />
                      AI
                    </span>
                  )}
                </div>

                <div className="card-footer">
                  <span className="author">
                    <User size={14} />
                    {item.author_name}
                  </span>
                  <span className="date">
                    <Clock size={14} />
                    {formatDate(item.created_at)}
                  </span>
                  {item.attachments_count > 0 && (
                    <span className="attachments">
                      📎 {item.attachments_count}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="btn-secondary"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t('common.previous')}
              </button>
              <span className="page-info">
                {page} / {totalPages} ({totalItems} {t('improvements.dashboard.total').toLowerCase()})
              </span>
              <button
                className="btn-secondary"
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('common.next')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default ImprovementsPage;
