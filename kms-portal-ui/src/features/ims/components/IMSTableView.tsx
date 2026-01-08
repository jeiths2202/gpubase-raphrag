/**
 * IMS Table View Component
 *
 * Sortable and filterable table display for issues
 */

import React, { useState, useMemo } from 'react';
import { ChevronUp, ChevronDown, Filter } from 'lucide-react';
import type { IMSIssue, SortConfig, FilterConfig, IssueStatus, IssuePriority } from '../types';

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

  // Sort and filter issues
  const processedIssues = useMemo(() => {
    let result = [...issues];

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

  return (
    <div className="ims-table-container">
      {/* Filter Toggle */}
      <div className="ims-table__toolbar">
        <button
          className={`ims-table__filter-btn ${showFilters ? 'active' : ''}`}
          onClick={() => setShowFilters(!showFilters)}
        >
          <Filter size={16} />
          {t('common.filter')}
        </button>
        <span className="ims-table__count">
          {processedIssues.length} / {issues.length}
        </span>
      </div>

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
              <th onClick={() => handleSort('ims_id')} className="sortable">
                {t('ims.table.id')} <SortIcon field="ims_id" />
              </th>
              <th onClick={() => handleSort('title')} className="sortable">
                {t('ims.table.title')} <SortIcon field="title" />
              </th>
              <th onClick={() => handleSort('status')} className="sortable">
                {t('ims.table.status')} <SortIcon field="status" />
              </th>
              <th onClick={() => handleSort('priority')} className="sortable">
                {t('ims.table.priority')} <SortIcon field="priority" />
              </th>
              <th>{t('ims.table.reporter')}</th>
              <th>{t('ims.table.assignee')}</th>
              <th onClick={() => handleSort('created_at')} className="sortable">
                {t('ims.table.created')} <SortIcon field="created_at" />
              </th>
              <th onClick={() => handleSort('similarity_score')} className="sortable">
                {t('ims.table.score')} <SortIcon field="similarity_score" />
              </th>
            </tr>
          </thead>
          <tbody>
            {processedIssues.map((issue) => (
              <tr
                key={issue.id}
                className="ims-table__row"
                onClick={() => onIssueClick?.(issue)}
              >
                <td className="ims-table__id">{issue.ims_id}</td>
                <td className="ims-table__title" title={issue.title}>
                  {issue.title}
                </td>
                <td>
                  <span className={`ims-badge ${STATUS_COLORS[issue.status]}`}>
                    {t(`ims.status.${issue.status}`)}
                  </span>
                </td>
                <td>
                  <span className={`ims-badge ${PRIORITY_COLORS[issue.priority]}`}>
                    {t(`ims.priority.${issue.priority}`)}
                  </span>
                </td>
                <td>{issue.reporter}</td>
                <td>{issue.assignee || '-'}</td>
                <td>{formatDate(issue.created_at)}</td>
                <td className="ims-table__score">{formatScore(issue.similarity_score)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default IMSTableView;
