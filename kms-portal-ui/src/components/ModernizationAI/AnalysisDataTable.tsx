/**
 * AnalysisDataTable - Persisted analysis results Data Table
 *
 * Features:
 *  - Paginated table with sort/filter
 *  - Row click opens popup detail page
 *  - Checkbox selection for bulk delete
 *  - Auto-refresh on mount and after analysis
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw,
  Trash2,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Database,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import {
  getPersistedAnalyses,
  deletePersistedAnalysis,
} from '../../api/legacy.api';
import type {
  PersistedAnalysisItem,
  AnalysisListParams,
} from '../../api/legacy.api';
import './AnalysisDataTable.css';

interface AnalysisDataTableProps {
  refreshTrigger?: number;
}

type SortField = 'file_name' | 'asset_type' | 'support_rate' | 'total_features' | 'incompatible_count' | 'risk_high' | 'created_at';

const AnalysisDataTable: React.FC<AnalysisDataTableProps> = ({ refreshTrigger }) => {
  const { t } = useTranslation();

  const [items, setItems] = useState<PersistedAnalysisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(20);
  const [sortBy, setSortBy] = useState<SortField>('created_at');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [filterAssetType, setFilterAssetType] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const params: AnalysisListParams = {
        page,
        limit,
        sort_by: sortBy,
        sort_order: sortOrder,
      };
      if (filterAssetType) params.asset_type = filterAssetType;

      const res = await getPersistedAnalyses(params);
      setItems(res.items);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (err: unknown) {
      console.error('[AnalysisDataTable] fetch error:', err);
      const msg = err instanceof Error ? err.message : String(err);
      setFetchError(msg);
    } finally {
      setLoading(false);
    }
  }, [page, limit, sortBy, sortOrder, filterAssetType]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Re-fetch when parent signals a new analysis completed
  useEffect(() => {
    if (refreshTrigger && refreshTrigger > 0) {
      fetchData();
    }
  }, [refreshTrigger, fetchData]);

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
    setPage(1);
  };

  const handleRowClick = (item: PersistedAnalysisItem) => {
    window.open(
      `/legacy/analysis/${item.id}`,
      '_blank',
      'width=1200,height=800,scrollbars=yes,resizable=yes'
    );
  };

  const handleSelectToggle = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selected.size === items.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(items.map((i) => i.id)));
    }
  };

  const handleDeleteSelected = async () => {
    if (selected.size === 0) return;
    setDeleting(true);
    try {
      await Promise.all(
        Array.from(selected).map((id) => deletePersistedAnalysis(id))
      );
      setSelected(new Set());
      await fetchData();
    } catch {
      // Silent error
    } finally {
      setDeleting(false);
    }
  };

  const SortIcon: React.FC<{ field: SortField }> = ({ field }) => {
    if (sortBy !== field) return null;
    return sortOrder === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />;
  };

  const getRiskBadge = (high: number, medium: number, low: number) => {
    if (high > 0) return <span className="adt-risk-badge adt-risk-high">{high}H</span>;
    if (medium > 0) return <span className="adt-risk-badge adt-risk-medium">{medium}M</span>;
    if (low > 0) return <span className="adt-risk-badge adt-risk-low">{low}L</span>;
    return <span className="adt-risk-badge adt-risk-none">-</span>;
  };

  const getSupportRateColor = (rate: number): string => {
    if (rate >= 90) return 'var(--color-success, #22c55e)';
    if (rate >= 70) return 'var(--color-warning, #f59e0b)';
    return 'var(--color-error, #ef4444)';
  };

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return '-';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="adt-container">
      {/* Toolbar */}
      <div className="adt-toolbar">
        <div className="adt-toolbar-left">
          <Database size={16} />
          <span className="adt-toolbar-title">{t('legacy.dataTable.title')}</span>
          <span className="adt-toolbar-count">({total})</span>
        </div>
        <div className="adt-toolbar-right">
          <select
            className="adt-filter-select"
            value={filterAssetType}
            onChange={(e) => { setFilterAssetType(e.target.value); setPage(1); }}
          >
            <option value="">{t('legacy.dataTable.allTypes')}</option>
            <option value="cobol">COBOL</option>
            <option value="jcl">JCL</option>
            <option value="map">MAP</option>
            <option value="asm">ASM</option>
          </select>

          <select
            className="adt-filter-select"
            value={limit}
            onChange={(e) => { setLimit(Number(e.target.value)); setPage(1); }}
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}>50</option>
          </select>

          {selected.size > 0 && (
            <button
              className="adt-btn adt-btn-danger"
              onClick={handleDeleteSelected}
              disabled={deleting}
            >
              {deleting ? <Loader2 size={14} className="adt-spinner" /> : <Trash2 size={14} />}
              {t('legacy.dataTable.delete')} ({selected.size})
            </button>
          )}

          <button
            className="adt-btn adt-btn-ghost"
            onClick={fetchData}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'adt-spinner' : ''} />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="adt-table-wrapper">
        <table className="adt-table">
          <thead>
            <tr>
              <th className="adt-th-check">
                <input
                  type="checkbox"
                  checked={items.length > 0 && selected.size === items.length}
                  onChange={handleSelectAll}
                />
              </th>
              <th className="adt-th-sortable" onClick={() => handleSort('file_name')}>
                {t('legacy.dataTable.fileName')} <SortIcon field="file_name" />
              </th>
              <th className="adt-th-sortable" onClick={() => handleSort('asset_type')}>
                {t('legacy.dataTable.type')} <SortIcon field="asset_type" />
              </th>
              <th>{t('legacy.dataTable.product')}</th>
              <th className="adt-th-sortable adt-th-num" onClick={() => handleSort('support_rate')}>
                {t('legacy.dataTable.supportRate')} <SortIcon field="support_rate" />
              </th>
              <th className="adt-th-sortable adt-th-num" onClick={() => handleSort('total_features')}>
                {t('legacy.dataTable.features')} <SortIcon field="total_features" />
              </th>
              <th className="adt-th-sortable adt-th-num" onClick={() => handleSort('incompatible_count')}>
                {t('legacy.dataTable.incompatible')} <SortIcon field="incompatible_count" />
              </th>
              <th className="adt-th-sortable adt-th-num" onClick={() => handleSort('risk_high')}>
                {t('legacy.dataTable.risk')} <SortIcon field="risk_high" />
              </th>
              <th className="adt-th-sortable" onClick={() => handleSort('created_at')}>
                {t('legacy.dataTable.date')} <SortIcon field="created_at" />
              </th>
              <th className="adt-th-action"></th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 ? (
              <tr>
                <td colSpan={10} className="adt-empty">
                  <Loader2 size={20} className="adt-spinner" />
                  {t('legacy.dataTable.loading')}
                </td>
              </tr>
            ) : fetchError ? (
              <tr>
                <td colSpan={10} className="adt-empty">
                  <AlertTriangle size={20} style={{ color: 'var(--color-error, #ef4444)' }} />
                  <span style={{ color: 'var(--color-error, #ef4444)', fontSize: '0.8rem' }}>
                    {t('legacy.dataTable.fetchError')}: {fetchError}
                  </span>
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={10} className="adt-empty">
                  <Database size={20} style={{ opacity: 0.3 }} />
                  {t('legacy.dataTable.empty')}
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.id}
                  className={`adt-row ${selected.has(item.id) ? 'adt-row-selected' : ''}`}
                  onClick={() => handleRowClick(item)}
                >
                  <td className="adt-td-check" onClick={(e) => handleSelectToggle(item.id, e)}>
                    <input
                      type="checkbox"
                      checked={selected.has(item.id)}
                      readOnly
                    />
                  </td>
                  <td className="adt-td-filename">
                    <span className="adt-filename">{item.file_name}</span>
                  </td>
                  <td>
                    <span className="adt-type-badge">{item.asset_type.toUpperCase()}</span>
                  </td>
                  <td className="adt-td-product">
                    {item.target_product || '-'}
                  </td>
                  <td className="adt-td-num">
                    <span style={{ color: getSupportRateColor(item.support_rate), fontWeight: 600 }}>
                      {item.support_rate.toFixed(1)}%
                    </span>
                  </td>
                  <td className="adt-td-num">{item.total_features}</td>
                  <td className="adt-td-num">
                    {item.incompatible_count > 0 ? (
                      <span style={{ color: 'var(--color-error, #ef4444)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <AlertTriangle size={12} />
                        {item.incompatible_count}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--color-success, #22c55e)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        <CheckCircle2 size={12} />
                        0
                      </span>
                    )}
                  </td>
                  <td className="adt-td-num">
                    {getRiskBadge(item.risk_high, item.risk_medium, item.risk_low)}
                  </td>
                  <td className="adt-td-date">{formatDate(item.created_at)}</td>
                  <td className="adt-td-action">
                    <ExternalLink size={14} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="adt-pagination">
          <span className="adt-pagination-info">
            {(page - 1) * limit + 1}-{Math.min(page * limit, total)} / {total}
          </span>
          <div className="adt-pagination-btns">
            <button
              className="adt-page-btn"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={14} />
            </button>
            {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
              const startPage = Math.max(1, Math.min(page - 2, totalPages - 4));
              const p = startPage + i;
              if (p > totalPages) return null;
              return (
                <button
                  key={p}
                  className={`adt-page-btn ${p === page ? 'adt-page-active' : ''}`}
                  onClick={() => setPage(p)}
                >
                  {p}
                </button>
              );
            })}
            <button
              className="adt-page-btn"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalysisDataTable;
