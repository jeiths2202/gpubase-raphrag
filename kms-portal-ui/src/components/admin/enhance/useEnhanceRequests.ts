/**
 * Custom hook for managing Enhancement Requests state and API calls
 */
import { useState, useCallback, useEffect } from 'react';
import type { EnhanceRequest, EnhanceStats, PaginationState } from './types';

interface UseEnhanceRequestsOptions {
  pageSize?: number;
}

interface UseEnhanceRequestsReturn {
  // State
  requests: EnhanceRequest[];
  loading: boolean;
  error: string | null;
  stats: EnhanceStats | null;
  pagination: PaginationState;
  searchQuery: string;
  statusFilter: string;
  executingId: string | null;
  deletingId: string | null;
  showDeleteConfirm: string | null;

  // Actions
  setSearchQuery: (query: string) => void;
  setStatusFilter: (filter: string) => void;
  setPage: (page: number) => void;
  setShowDeleteConfirm: (id: string | null) => void;
  fetchRequests: () => Promise<void>;
  handleExecute: (id: string) => Promise<void>;
  handleDelete: (id: string) => Promise<void>;
}

export const useEnhanceRequests = (
  options: UseEnhanceRequestsOptions = {}
): UseEnhanceRequestsReturn => {
  const { pageSize = 10 } = options;

  // Request state
  const [requests, setRequests] = useState<EnhanceRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<EnhanceStats | null>(null);

  // Pagination state
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);

  // Filter state
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Action state
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

  // Fetch enhancement requests
  const fetchRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('limit', pageSize.toString());
      if (statusFilter) params.append('status', statusFilter);
      if (searchQuery) params.append('search', searchQuery);

      const response = await fetch(`/api/v1/enhancements?${params.toString()}`, {
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to fetch enhancement requests');

      const data = await response.json();
      setRequests(data.data.items || []);
      setTotalPages(data.pagination?.total_pages || 1);
      setTotalItems(data.pagination?.total_items || 0);

      // Fetch stats
      const statsResponse = await fetch('/api/v1/enhancements/dashboard', {
        credentials: 'include',
      });
      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        const byStatus = statsData.data?.by_status || {};
        setStats({
          total: statsData.data?.total_requests || 0,
          pending: (byStatus['submitted'] || 0) + (byStatus['analyzing'] || 0),
          analyzed: byStatus['analyzed'] || 0,
          implemented: statsData.data?.implemented_count || 0,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load requests');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, searchQuery, pageSize]);

  // Execute (analyze) enhancement request
  const handleExecute = useCallback(async (id: string) => {
    setExecutingId(id);
    try {
      const response = await fetch(`/api/v1/enhancements/${id}/analyze`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to analyze enhancement');

      // Refresh the list
      await fetchRequests();
    } catch (err) {
      console.error('Execute failed:', err);
      alert('Failed to execute enhancement analysis');
    } finally {
      setExecutingId(null);
    }
  }, [fetchRequests]);

  // Delete enhancement request
  const handleDelete = useCallback(async (id: string) => {
    setDeletingId(id);
    try {
      const response = await fetch(`/api/v1/enhancements/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to delete enhancement');

      setShowDeleteConfirm(null);
      await fetchRequests();
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Failed to delete enhancement request');
    } finally {
      setDeletingId(null);
    }
  }, [fetchRequests]);

  // Set search query and reset page
  const handleSetSearchQuery = useCallback((query: string) => {
    setSearchQuery(query);
    setPage(1);
  }, []);

  // Set status filter and reset page
  const handleSetStatusFilter = useCallback((filter: string) => {
    setStatusFilter(filter);
    setPage(1);
  }, []);

  // Fetch requests on mount and when filters change
  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  return {
    // State
    requests,
    loading,
    error,
    stats,
    pagination: { page, totalPages, totalItems },
    searchQuery,
    statusFilter,
    executingId,
    deletingId,
    showDeleteConfirm,

    // Actions
    setSearchQuery: handleSetSearchQuery,
    setStatusFilter: handleSetStatusFilter,
    setPage,
    setShowDeleteConfirm,
    fetchRequests,
    handleExecute,
    handleDelete,
  };
};
