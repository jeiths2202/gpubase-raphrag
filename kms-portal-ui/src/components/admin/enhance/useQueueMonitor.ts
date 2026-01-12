/**
 * Custom hook for managing Queue Monitoring state and API calls
 */
import { useState, useCallback, useEffect } from 'react';
import type { QueueStatus } from './types';

interface UseQueueMonitorOptions {
  refreshInterval?: number;
  autoRefresh?: boolean;
}

interface UseQueueMonitorReturn {
  // State
  queueStatus: QueueStatus | null;
  loading: boolean;
  showPanel: boolean;
  stoppingTaskId: string | null;
  stoppingAgentType: string | null;
  clearingQueue: boolean;

  // Computed
  runningCount: number;
  queuedCount: number;
  totalCount: number;
  isProcessing: boolean;

  // Actions
  setShowPanel: (show: boolean) => void;
  fetchQueueStatus: () => Promise<void>;
  handleForceStopTask: (taskId: string) => Promise<void>;
  handleForceStopAgent: (agentType: string) => Promise<void>;
  handleClearQueue: () => Promise<void>;
}

export const useQueueMonitor = (
  options: UseQueueMonitorOptions = {}
): UseQueueMonitorReturn => {
  const { refreshInterval = 5000, autoRefresh = true } = options;

  // Queue status state
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPanel, setShowPanel] = useState(true);

  // Action state
  const [stoppingTaskId, setStoppingTaskId] = useState<string | null>(null);
  const [stoppingAgentType, setStoppingAgentType] = useState<string | null>(null);
  const [clearingQueue, setClearingQueue] = useState(false);

  // Fetch queue status
  const fetchQueueStatus = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/enhancements/queue/status', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setQueueStatus(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch queue status:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Force stop a task
  const handleForceStopTask = useCallback(async (taskId: string) => {
    setStoppingTaskId(taskId);
    try {
      const response = await fetch(`/api/v1/enhancements/queue/force-stop/${taskId}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to stop task');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Force stop failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to stop task');
    } finally {
      setStoppingTaskId(null);
    }
  }, [fetchQueueStatus]);

  // Force stop an agent
  const handleForceStopAgent = useCallback(async (agentType: string) => {
    setStoppingAgentType(agentType);
    try {
      const response = await fetch(`/api/v1/enhancements/queue/force-stop-agent/${agentType}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to stop agent');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Force stop agent failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to stop agent');
    } finally {
      setStoppingAgentType(null);
    }
  }, [fetchQueueStatus]);

  // Clear the queue
  const handleClearQueue = useCallback(async () => {
    if (!confirm('Are you sure you want to clear all queued tasks? This cannot be undone.')) {
      return;
    }
    setClearingQueue(true);
    try {
      const response = await fetch('/api/v1/enhancements/queue/clear', {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to clear queue');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Clear queue failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to clear queue');
    } finally {
      setClearingQueue(false);
    }
  }, [fetchQueueStatus]);

  // Computed values
  const runningCount = queueStatus?.running_tasks.length || 0;
  const queuedCount = queueStatus?.queue.total_queued || 0;
  const totalCount = runningCount + queuedCount;
  const isProcessing = runningCount > 0;

  // Auto-refresh queue status
  useEffect(() => {
    fetchQueueStatus();
    if (autoRefresh) {
      const interval = setInterval(fetchQueueStatus, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [fetchQueueStatus, autoRefresh, refreshInterval]);

  return {
    // State
    queueStatus,
    loading,
    showPanel,
    stoppingTaskId,
    stoppingAgentType,
    clearingQueue,

    // Computed
    runningCount,
    queuedCount,
    totalCount,
    isProcessing,

    // Actions
    setShowPanel,
    fetchQueueStatus,
    handleForceStopTask,
    handleForceStopAgent,
    handleClearQueue,
  };
};
