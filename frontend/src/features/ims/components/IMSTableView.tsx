/**
 * IMS Table View Component
 * Table-based view for search results with sorting and filtering
 */

import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import type { TranslateFunction } from '../../../i18n/types';

export interface IMSIssue {
  id: string;
  ims_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  reporter: string;
  assignee: string | null;
  project_key: string;
  labels: string[];
  created_at: string;
  updated_at: string;
  similarity_score?: number;
}

interface Props {
  issues: IMSIssue[];
  t: TranslateFunction;
  onIssueClick?: (issue: IMSIssue) => void;
}

type SortField = 'ims_id' | 'title' | 'status' | 'priority' | 'created_at' | 'similarity_score';
type SortDirection = 'asc' | 'desc';

export const IMSTableView: React.FC<Props> = ({ issues, t, onIssueClick }) => {
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedAndFilteredIssues = useMemo(() => {
    let filtered = [...issues];

    // Apply filters
    if (filterStatus !== 'all') {
      filtered = filtered.filter(issue => issue.status === filterStatus);
    }
    if (filterPriority !== 'all') {
      filtered = filtered.filter(issue => issue.priority === filterPriority);
    }

    // Apply sorting
    filtered.sort((a, b) => {
      let aVal: any = a[sortField];
      let bVal: any = b[sortField];

      // Handle dates
      if (sortField === 'created_at') {
        aVal = new Date(aVal).getTime();
        bVal = new Date(bVal).getTime();
      }

      // Handle numbers
      if (sortField === 'similarity_score') {
        aVal = aVal || 0;
        bVal = bVal || 0;
      }

      if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });

    return filtered;
  }, [issues, sortField, sortDirection, filterStatus, filterPriority]);

  const uniqueStatuses = useMemo(() =>
    Array.from(new Set(issues.map(i => i.status))),
    [issues]
  );

  const uniquePriorities = useMemo(() =>
    Array.from(new Set(issues.map(i => i.priority))),
    [issues]
  );

  const getPriorityColor = (priority: string) => {
    switch (priority.toUpperCase()) {
      case 'CRITICAL': return '#dc2626';
      case 'HIGH': return '#f59e0b';
      case 'MEDIUM': return '#3b82f6';
      case 'LOW': return '#10b981';
      default: return '#6b7280';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case 'OPEN': return '#3b82f6';
      case 'IN_PROGRESS': return '#f59e0b';
      case 'RESOLVED': return '#10b981';
      case 'CLOSED': return '#6b7280';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{ width: '100%' }}>
      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: '12px',
        marginBottom: '16px',
        flexWrap: 'wrap'
      }}>
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--text)',
            fontSize: '14px'
          }}
        >
          <option value="all">All Statuses</option>
          {uniqueStatuses.map(status => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>

        <select
          value={filterPriority}
          onChange={(e) => setFilterPriority(e.target.value)}
          style={{
            padding: '8px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border)',
            background: 'var(--card-bg)',
            color: 'var(--text)',
            fontSize: '14px'
          }}
        >
          <option value="all">All Priorities</option>
          {uniquePriorities.map(priority => (
            <option key={priority} value={priority}>{priority}</option>
          ))}
        </select>

        <div style={{
          marginLeft: 'auto',
          fontSize: '14px',
          color: 'var(--text-secondary)',
          alignSelf: 'center'
        }}>
          {sortedAndFilteredIssues.length} / {issues.length} issues
        </div>
      </div>

      {/* Table */}
      <div style={{
        overflowX: 'auto',
        border: '1px solid var(--border)',
        borderRadius: '8px'
      }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '14px'
        }}>
          <thead style={{
            background: 'var(--input-bg)',
            borderBottom: '1px solid var(--border)'
          }}>
            <tr>
              <TableHeader
                label="ID"
                field="ims_id"
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
              <TableHeader
                label="Title"
                field="title"
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
              <TableHeader
                label="Status"
                field="status"
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
              <TableHeader
                label="Priority"
                field="priority"
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
              <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>
                Reporter
              </th>
              <th style={{ padding: '12px', textAlign: 'left', fontWeight: 600 }}>
                Assignee
              </th>
              <TableHeader
                label="Created"
                field="created_at"
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
              />
              {issues.some(i => i.similarity_score !== undefined) && (
                <TableHeader
                  label="Score"
                  field="similarity_score"
                  sortField={sortField}
                  sortDirection={sortDirection}
                  onSort={handleSort}
                />
              )}
            </tr>
          </thead>
          <tbody>
            {sortedAndFilteredIssues.map((issue, idx) => (
              <motion.tr
                key={issue.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.02 }}
                onClick={() => onIssueClick?.(issue)}
                style={{
                  borderBottom: '1px solid var(--border)',
                  cursor: onIssueClick ? 'pointer' : 'default',
                  background: 'var(--card-bg)'
                }}
                whileHover={onIssueClick ? {
                  background: 'var(--input-bg)'
                } : undefined}
              >
                <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: '13px' }}>
                  {issue.ims_id}
                </td>
                <td style={{ padding: '12px', maxWidth: '300px' }}>
                  <div style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    fontWeight: 500
                  }}>
                    {issue.title}
                  </div>
                </td>
                <td style={{ padding: '12px' }}>
                  <span style={{
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 500,
                    background: `${getStatusColor(issue.status)}20`,
                    color: getStatusColor(issue.status)
                  }}>
                    {issue.status}
                  </span>
                </td>
                <td style={{ padding: '12px' }}>
                  <span style={{
                    padding: '4px 8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 500,
                    background: `${getPriorityColor(issue.priority)}20`,
                    color: getPriorityColor(issue.priority)
                  }}>
                    {issue.priority}
                  </span>
                </td>
                <td style={{ padding: '12px', color: 'var(--text-secondary)' }}>
                  {issue.reporter}
                </td>
                <td style={{ padding: '12px', color: 'var(--text-secondary)' }}>
                  {issue.assignee || '-'}
                </td>
                <td style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '13px' }}>
                  {new Date(issue.created_at).toLocaleDateString()}
                </td>
                {issue.similarity_score !== undefined && (
                  <td style={{ padding: '12px', fontFamily: 'monospace', fontSize: '13px' }}>
                    {(issue.similarity_score * 100).toFixed(1)}%
                  </td>
                )}
              </motion.tr>
            ))}
          </tbody>
        </table>

        {sortedAndFilteredIssues.length === 0 && (
          <div style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--text-secondary)'
          }}>
            No issues match the current filters
          </div>
        )}
      </div>
    </div>
  );
};

interface TableHeaderProps {
  label: string;
  field: SortField;
  sortField: SortField;
  sortDirection: SortDirection;
  onSort: (field: SortField) => void;
}

const TableHeader: React.FC<TableHeaderProps> = ({
  label,
  field,
  sortField,
  sortDirection,
  onSort
}) => {
  const isActive = sortField === field;

  return (
    <th
      onClick={() => onSort(field)}
      style={{
        padding: '12px',
        textAlign: 'left',
        fontWeight: 600,
        cursor: 'pointer',
        userSelect: 'none'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        {label}
        <span style={{
          fontSize: '10px',
          color: isActive ? 'var(--accent)' : 'var(--text-secondary)'
        }}>
          {isActive ? (sortDirection === 'asc' ? '▲' : '▼') : '⬍'}
        </span>
      </div>
    </th>
  );
};
