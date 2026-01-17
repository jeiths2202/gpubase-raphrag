/**
 * Enhance Requests Table Component
 * Displays the list of enhancement requests with pagination
 */
import React from 'react';
import {
  Eye,
  Play,
  Trash2,
  Loader2,
  Lightbulb,
  Bot,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react';
import type { EnhanceRequest, PaginationState } from './types';
import {
  formatDate,
  getStatusColor,
  getPriorityColor,
  getTypeIcon,
  canExecute,
} from './utils';

interface EnhanceRequestsTableProps {
  requests: EnhanceRequest[];
  pagination: PaginationState;
  executingId: string | null;
  onExecute: (id: string) => void;
  onDelete: (id: string) => void;
  onViewDetails: (id: string) => void;
  onPageChange: (page: number) => void;
}

// Pagination Component
const Pagination: React.FC<{
  pagination: PaginationState;
  itemsCount: number;
  onPageChange: (page: number) => void;
}> = ({ pagination, itemsCount, onPageChange }) => {
  const { page, totalPages, totalItems } = pagination;

  if (totalPages < 1) return null;

  // Generate page numbers with ellipsis
  const generatePageNumbers = (): (number | 'ellipsis')[] => {
    const pages: (number | 'ellipsis')[] = [];
    const maxVisiblePages = 5;

    if (totalPages <= maxVisiblePages) {
      for (let i = 1; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      if (page > 3) pages.push('ellipsis');

      const start = Math.max(2, page - 1);
      const end = Math.min(totalPages - 1, page + 1);

      for (let i = start; i <= end; i++) {
        if (!pages.includes(i)) pages.push(i);
      }

      if (page < totalPages - 2) pages.push('ellipsis');
      if (!pages.includes(totalPages)) pages.push(totalPages);
    }

    return pages;
  };

  return (
    <div className="admin-pagination-enhanced">
      <div className="admin-pagination-summary">
        Showing {itemsCount > 0 ? (page - 1) * 10 + 1 : 0} -{' '}
        {Math.min(page * 10, totalItems)} of {totalItems} items
      </div>
      <div className="admin-pagination-controls">
        <button
          className="admin-pagination-nav-btn"
          disabled={page === 1}
          onClick={() => onPageChange(1)}
          title="First page"
        >
          <ChevronsLeft size={16} />
        </button>
        <button
          className="admin-pagination-nav-btn"
          disabled={page === 1}
          onClick={() => onPageChange(page - 1)}
          title="Previous page"
        >
          <ChevronLeft size={16} />
        </button>

        {generatePageNumbers().map((p, idx) =>
          p === 'ellipsis' ? (
            <span key={`ellipsis-${idx}`} className="admin-pagination-ellipsis">
              ...
            </span>
          ) : (
            <button
              key={p}
              className={`admin-pagination-page-btn ${page === p ? 'active' : ''}`}
              onClick={() => onPageChange(p)}
            >
              {p}
            </button>
          )
        )}

        <button
          className="admin-pagination-nav-btn"
          disabled={page === totalPages}
          onClick={() => onPageChange(page + 1)}
          title="Next page"
        >
          <ChevronRight size={16} />
        </button>
        <button
          className="admin-pagination-nav-btn"
          disabled={page === totalPages}
          onClick={() => onPageChange(totalPages)}
          title="Last page"
        >
          <ChevronsRight size={16} />
        </button>
      </div>
    </div>
  );
};

// Table Row Component
const TableRow: React.FC<{
  request: EnhanceRequest;
  executingId: string | null;
  onExecute: (id: string) => void;
  onDelete: (id: string) => void;
  onViewDetails: (id: string) => void;
}> = ({ request, executingId, onExecute, onDelete, onViewDetails }) => {
  return (
    <tr>
      <td className="admin-table-title">
        <span className="enhance-type-icon">{getTypeIcon(request.type)}</span>
        <span className="enhance-title-text">{request.title}</span>
        {request.ai_analyzed && (
          <span className="enhance-ai-badge">
            <Bot size={12} />
            AI
          </span>
        )}
      </td>
      <td>
        {request.type ? (
          <span className="enhance-type-badge">{request.type.replace('_', ' ')}</span>
        ) : (
          <span className="enhance-type-badge enhance-type-badge--none">-</span>
        )}
      </td>
      <td>
        {request.priority ? (
          <span
            className="enhance-priority-badge"
            style={{
              backgroundColor: `${getPriorityColor(request.priority)}20`,
              color: getPriorityColor(request.priority),
            }}
          >
            {request.priority}
          </span>
        ) : (
          <span className="enhance-priority-badge enhance-priority-badge--none">-</span>
        )}
      </td>
      <td>
        <span
          className="enhance-status-badge"
          style={{
            backgroundColor: `${getStatusColor(request.status)}20`,
            color: getStatusColor(request.status),
          }}
        >
          {request.status.replace('_', ' ')}
        </span>
      </td>
      <td>{request.author_name}</td>
      <td className="admin-table-date">{formatDate(request.created_at)}</td>
      <td className="admin-table-actions">
        <button
          className="admin-action-btn admin-action-btn--view"
          onClick={() => onViewDetails(request.id)}
          title="View Details"
        >
          <Eye size={16} />
        </button>
        {canExecute(request.status) && (
          <button
            className="admin-action-btn admin-action-btn--execute"
            onClick={() => onExecute(request.id)}
            disabled={executingId === request.id}
            title="Execute AI Analysis"
          >
            {executingId === request.id ? (
              <Loader2 size={16} className="spinning" />
            ) : (
              <Play size={16} />
            )}
          </button>
        )}
        <button
          className="admin-action-btn admin-action-btn--delete"
          onClick={() => onDelete(request.id)}
          title="Delete Request"
        >
          <Trash2 size={16} />
        </button>
      </td>
    </tr>
  );
};

export const EnhanceRequestsTable: React.FC<EnhanceRequestsTableProps> = ({
  requests,
  pagination,
  executingId,
  onExecute,
  onDelete,
  onViewDetails,
  onPageChange,
}) => {
  return (
    <>
      <section className="admin-table-section">
        <div className="admin-table-scroll-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Author</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.length === 0 ? (
                <tr>
                  <td colSpan={7} className="admin-table-empty">
                    <Lightbulb size={32} />
                    <p>No enhancement requests found</p>
                  </td>
                </tr>
              ) : (
                requests.map((request) => (
                  <TableRow
                    key={request.id}
                    request={request}
                    executingId={executingId}
                    onExecute={onExecute}
                    onDelete={onDelete}
                    onViewDetails={onViewDetails}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Pagination
        pagination={pagination}
        itemsCount={requests.length}
        onPageChange={onPageChange}
      />
    </>
  );
};
