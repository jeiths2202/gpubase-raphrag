/**
 * IMS Table View Component
 *
 * Sortable and filterable table display for issues with configurable columns
 */

import React, { useState, useMemo, useEffect } from 'react';
import { ChevronUp, ChevronDown, Filter, Settings, X } from 'lucide-react';
import type { IMSIssue, SortConfig, FilterConfig, IssueStatus, IssuePriority } from '../types';

// Define all available columns - keys must match IMSIssue interface
type ColumnKey = 'ims_id' | 'title' | 'category' | 'product' | 'version' | 'module' | 'customer' | 'issued_date' | 'status' | 'priority' | 'reporter' | 'assignee' | 'similarity_score';

interface ColumnConfig {
  key: ColumnKey;
  labelKey: string;  // i18n key
  width?: string;
}

// All available columns configuration
const ALL_COLUMNS: ColumnConfig[] = [
  { key: 'ims_id', labelKey: 'ims.table.id', width: '80px' },
  { key: 'title', labelKey: 'ims.table.title' },
  { key: 'category', labelKey: 'ims.table.category' },
  { key: 'product', labelKey: 'ims.table.product' },
  { key: 'version', labelKey: 'ims.table.version', width: '80px' },
  { key: 'module', labelKey: 'ims.table.module' },
  { key: 'customer', labelKey: 'ims.table.customer' },
  { key: 'issued_date', labelKey: 'ims.table.issuedDate', width: '100px' },
  { key: 'status', labelKey: 'ims.table.status', width: '100px' },
  { key: 'priority', labelKey: 'ims.table.priority', width: '80px' },
  { key: 'reporter', labelKey: 'ims.table.reporter' },
  { key: 'assignee', labelKey: 'ims.table.assignee' },
  { key: 'similarity_score', labelKey: 'ims.table.score', width: '80px' },
];

// Default visible columns
const DEFAULT_VISIBLE_COLUMNS: ColumnKey[] = ['ims_id', 'title', 'category', 'product', 'version', 'module', 'customer'];

const STORAGE_KEY = 'ims-table-columns';

interface IMSTableViewProps {
  issues: IMSIssue[];
  onIssueClick?: (issue: IMSIssue) => void;
  t: (key: string) => string;
}

const STATUS_COLORS: Record<IssueStatus, string> = {
  open: 'status--open',
  in_progress: 'status--progress',
  resolved: 'status--resolved',
  closed: 'status--closed',
  pending: 'status--pending',
  rejected: 'status--rejected',
};

const PRIORITY_COLORS: Record<IssuePriority, string> = {
  critical: 'priority--critical',
  high: 'priority--high',
  medium: 'priority--medium',
  low: 'priority--low',
  trivial: 'priority--trivial',
};

export const IMSTableView: React.FC<IMSTableViewProps> = ({ issues, onIssueClick, t }) => {
  const [sortConfig, setSortConfig] = useState<SortConfig>({
    field: 'created_at',
    direction: 'desc',
  });
  const [filter, setFilter] = useState<FilterConfig>({});
  const [showFilters, setShowFilters] = useState(false);
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const [visibleColumns, setVisibleColumns] = useState<ColumnKey[]>(() => {
    // Load from localStorage or use defaults
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        return JSON.parse(saved) as ColumnKey[];
      }
    } catch {
      // ignore parse errors
    }
    return DEFAULT_VISIBLE_COLUMNS;
  });

  // Save column preferences to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(visibleColumns));
    } catch {
      // ignore storage errors
    }
  }, [visibleColumns]);

  // Get visible column configs
  const activeColumns = useMemo(() => {
    return visibleColumns
      .map(key => ALL_COLUMNS.find(col => col.key === key))
      .filter((col): col is ColumnConfig => col !== undefined);
  }, [visibleColumns]);

  const toggleColumn = (key: ColumnKey) => {
    setVisibleColumns(prev => {
      if (prev.includes(key)) {
        // Don't allow removing all columns - keep at least ID
        if (prev.length <= 1) return prev;
        return prev.filter(k => k !== key);
      } else {
        // Add column in the correct order
        const newColumns = [...prev, key];
        return ALL_COLUMNS.filter(col => newColumns.includes(col.key)).map(col => col.key);
      }
    });
  };

  const selectAllColumns = () => {
    setVisibleColumns(ALL_COLUMNS.map(col => col.key));
  };

  const resetToDefault = () => {
    setVisibleColumns(DEFAULT_VISIBLE_COLUMNS);
  };

  // Sort and filter issues
  const processedIssues = useMemo(() => {
    // Deduplicate issues by ID to prevent React key warnings
    const uniqueMap = new Map<string, IMSIssue>();
    issues.forEach(issue => {
      if (!uniqueMap.has(issue.id)) {
        uniqueMap.set(issue.id, issue);
      }
    });
    let result = Array.from(uniqueMap.values());

    // Apply filters
    if (filter.status) {
      result = result.filter((issue) => issue.status === filter.status);
    }
    if (filter.priority) {
      result = result.filter((issue) => issue.priority === filter.priority);
    }

    // Apply sorting
    result.sort((a, b) => {
      const aValue = a[sortConfig.field as keyof IMSIssue];
      const bValue = b[sortConfig.field as keyof IMSIssue];

      if (aValue === undefined || aValue === null) return 1;
      if (bValue === undefined || bValue === null) return -1;

      let comparison = 0;
      if (typeof aValue === 'string' && typeof bValue === 'string') {
        comparison = aValue.localeCompare(bValue);
      } else if (typeof aValue === 'number' && typeof bValue === 'number') {
        comparison = aValue - bValue;
      }

      return sortConfig.direction === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [issues, sortConfig, filter]);

  const handleSort = (field: SortConfig['field']) => {
    setSortConfig((prev) => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc',
    }));
  };

  const SortIcon = ({ field }: { field: SortConfig['field'] }) => {
    if (sortConfig.field !== field) return null;
    return sortConfig.direction === 'asc' ? (
      <ChevronUp size={14} />
    ) : (
      <ChevronDown size={14} />
    );
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  const formatScore = (score?: number) => {
    if (score === undefined || score === null) return '-';
    return `${(score * 100).toFixed(0)}%`;
  };

  // Helper to render cell value
  const renderCellValue = (issue: IMSIssue, column: ColumnConfig): React.ReactNode => {
    const key = column.key;
    const value = issue[key];

    // Truncate text to specified length with ellipsis
    const truncateText = (text: string, maxLength: number = 30): string => {
      if (!text) return '';
      return text.length > maxLength ? text.slice(0, maxLength) + '...' : text;
    };

    switch (key) {
      case 'ims_id':
        return <span className="ims-table__id">{issue.ims_id}</span>;
      case 'title':
        return <span className="ims-table__title" title={issue.title}>{truncateText(issue.title, 30)}</span>;
      case 'status':
        return issue.status ? (
          <span className={`ims-badge ${STATUS_COLORS[issue.status] || ''}`}>
            {t(`ims.status.${issue.status}`)}
          </span>
        ) : '-';
      case 'priority':
        return issue.priority ? (
          <span className={`ims-badge ${PRIORITY_COLORS[issue.priority] || ''}`}>
            {t(`ims.priority.${issue.priority}`)}
          </span>
        ) : '-';
      case 'issued_date':
        return issue.issued_date ? formatDate(issue.issued_date) : '-';
      case 'similarity_score':
        return formatScore(issue.similarity_score);
      default:
        return value || '-';
    }
  };

  return (
    <div className="ims-table-container">
      {/* Toolbar */}
      <div className="ims-table__toolbar">
        <div className="ims-table__toolbar-left">
          <button
            className={`ims-table__filter-btn ${showFilters ? 'active' : ''}`}
            onClick={() => setShowFilters(!showFilters)}
          >
            <Filter size={16} />
            {t('common.filter')}
          </button>
          <button
            className={`ims-table__filter-btn ${showColumnPicker ? 'active' : ''}`}
            onClick={() => setShowColumnPicker(!showColumnPicker)}
          >
            <Settings size={16} />
            {t('ims.table.columns') || 'Columns'}
          </button>
        </div>
        <span className="ims-table__count">
          {processedIssues.length} / {issues.length}
        </span>
      </div>

      {/* Column Picker */}
      {showColumnPicker && (
        <div className="ims-column-picker">
          <div className="ims-column-picker__header">
            <span>{t('ims.table.selectColumns') || 'Select Columns'}</span>
            <button className="btn-icon" onClick={() => setShowColumnPicker(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="ims-column-picker__actions">
            <button className="btn btn-ghost btn-sm" onClick={selectAllColumns}>
              {t('ims.search.selectAll')}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={resetToDefault}>
              {t('common.reset')}
            </button>
          </div>
          <div className="ims-column-picker__list">
            {ALL_COLUMNS.map(col => (
              <label key={col.key} className="ims-column-picker__item">
                <input
                  type="checkbox"
                  checked={visibleColumns.includes(col.key)}
                  onChange={() => toggleColumn(col.key)}
                />
                <span>{t(col.labelKey)}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      {showFilters && (
        <div className="ims-table__filters">
          <select
            className="ims-select"
            value={filter.status || ''}
            onChange={(e) =>
              setFilter((prev) => ({
                ...prev,
                status: (e.target.value as IssueStatus) || undefined,
              }))
            }
          >
            <option value="">{t('ims.table.allStatuses')}</option>
            <option value="open">{t('ims.status.open')}</option>
            <option value="in_progress">{t('ims.status.in_progress')}</option>
            <option value="resolved">{t('ims.status.resolved')}</option>
            <option value="closed">{t('ims.status.closed')}</option>
          </select>
          <select
            className="ims-select"
            value={filter.priority || ''}
            onChange={(e) =>
              setFilter((prev) => ({
                ...prev,
                priority: (e.target.value as IssuePriority) || undefined,
              }))
            }
          >
            <option value="">{t('ims.table.allPriorities')}</option>
            <option value="critical">{t('ims.priority.critical')}</option>
            <option value="high">{t('ims.priority.high')}</option>
            <option value="medium">{t('ims.priority.medium')}</option>
            <option value="low">{t('ims.priority.low')}</option>
          </select>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setFilter({})}
          >
            {t('common.reset')}
          </button>
        </div>
      )}

      {/* Table */}
      <div className="ims-table-wrapper">
        <table className="ims-table">
          <thead>
            <tr>
              {activeColumns.map(col => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="sortable"
                  style={col.width ? { width: col.width } : undefined}
                >
                  {t(col.labelKey)} <SortIcon field={col.key} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {processedIssues.map((issue) => (
              <tr
                key={issue.id}
                className="ims-table__row"
                onClick={() => onIssueClick?.(issue)}
              >
                {activeColumns.map(col => (
                  <td key={col.key}>
                    {renderCellValue(issue, col)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default IMSTableView;
