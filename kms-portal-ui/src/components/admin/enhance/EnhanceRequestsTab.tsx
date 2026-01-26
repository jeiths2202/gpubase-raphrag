/**
 * Enhance Requests Tab Component
 * Main container that composes all enhancement request sub-components
 */
import React, { useState } from 'react';
import { Loader2, Lightbulb, Clock, Bot, CheckCircle, AlertTriangle } from 'lucide-react';

// Sub-components
import { RequestCounter } from './RequestCounter';
import { AgentQueueMonitor } from './AgentQueueMonitor';
import { EnhanceRequestsFilter } from './EnhanceRequestsFilter';
import { EnhanceRequestsTable } from './EnhanceRequestsTable';
import { DeleteConfirmModal } from './DeleteConfirmModal';
import { EnhanceDetailModal } from './EnhanceDetailModal';

// Hooks
import { useEnhanceRequests } from './useEnhanceRequests';
import { useQueueMonitor } from './useQueueMonitor';

// KPICard component (reuse from parent or import)
interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  color?: string;
}

const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  subtitle,
  icon,
  color = 'var(--color-primary)',
}) => (
  <div className="admin-kpi-card">
    <div className="admin-kpi-icon" style={{ backgroundColor: `${color}15`, color }}>
      {icon}
    </div>
    <div className="admin-kpi-content">
      <div className="admin-kpi-title">{title}</div>
      <div className="admin-kpi-value">{value}</div>
      {subtitle && (
        <div className="admin-kpi-footer">
          <span className="admin-kpi-subtitle">{subtitle}</span>
        </div>
      )}
    </div>
  </div>
);

export const EnhanceRequestsTab: React.FC = () => {
  console.log('[EnhanceRequestsTab] Component rendering');

  // Local state for detail modal
  const [selectedDetailId, setSelectedDetailId] = useState<string | null>(null);

  // Use custom hooks for state management
  const {
    requests,
    loading,
    error,
    stats,
    pagination,
    searchQuery,
    statusFilter,
    executingId,
    deletingId,
    showDeleteConfirm,
    setSearchQuery,
    setStatusFilter,
    setPage,
    setShowDeleteConfirm,
    fetchRequests,
    handleExecute,
    handleDelete,
  } = useEnhanceRequests();

  const {
    queueStatus,
    loading: queueLoading,
    showPanel,
    stoppingTaskId,
    stoppingAgentType,
    clearingQueue,
    runningCount,
    queuedCount,
    isProcessing,
    setShowPanel,
    fetchQueueStatus,
    handleForceStopTask,
    handleForceStopAgent,
    handleClearQueue,
  } = useQueueMonitor();

  console.log('[EnhanceRequestsTab] Queue status:', { runningCount, queuedCount, isProcessing, queueStatus });

  // View details handler - opens modal instead of new window
  const handleViewDetails = (id: string) => {
    setSelectedDetailId(id);
  };

  // Handle action complete - refresh requests
  const handleActionComplete = () => {
    fetchRequests();
  };

  // Loading state
  if (loading && requests.length === 0) {
    return (
      <div className="admin-tab-content">
        <div className="admin-loading">
          <Loader2 size={24} className="spinning" />
          <span>Loading enhancement requests...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-tab-content">
      {/* Stats Cards */}
      {stats && (
        <section className="admin-kpi-grid">
          <KPICard
            title="Total Requests"
            value={stats.total}
            icon={<Lightbulb size={24} />}
            color="#6366f1"
          />
          <KPICard
            title="Pending Analysis"
            value={stats.pending}
            subtitle="Waiting for AI"
            icon={<Clock size={24} />}
            color="#f59e0b"
          />
          <KPICard
            title="Analyzed"
            value={stats.analyzed}
            subtitle="AI processed"
            icon={<Bot size={24} />}
            color="#22c55e"
          />
          <KPICard
            title="Implemented"
            value={stats.implemented}
            subtitle="Completed"
            icon={<CheckCircle size={24} />}
            color="#10b981"
          />
        </section>
      )}

      {/* Request Counter */}
      <RequestCounter
        runningCount={runningCount}
        queuedCount={queuedCount}
        isProcessing={isProcessing}
      />

      {/* Agent Queue Monitoring Panel */}
      <AgentQueueMonitor
        queueStatus={queueStatus}
        loading={queueLoading}
        showPanel={showPanel}
        stoppingTaskId={stoppingTaskId}
        stoppingAgentType={stoppingAgentType}
        clearingQueue={clearingQueue}
        onTogglePanel={() => setShowPanel(!showPanel)}
        onRefresh={fetchQueueStatus}
        onForceStopTask={handleForceStopTask}
        onForceStopAgent={handleForceStopAgent}
        onClearQueue={handleClearQueue}
      />

      {/* Filters */}
      <EnhanceRequestsFilter
        searchQuery={searchQuery}
        statusFilter={statusFilter}
        onSearchChange={setSearchQuery}
        onStatusChange={setStatusFilter}
        onRefresh={fetchRequests}
      />

      {/* Error State */}
      {error && (
        <div className="admin-error-message">
          <AlertTriangle size={20} />
          <span>{error}</span>
        </div>
      )}

      {/* Table with Pagination */}
      <EnhanceRequestsTable
        requests={requests}
        pagination={pagination}
        executingId={executingId}
        onExecute={handleExecute}
        onDelete={setShowDeleteConfirm}
        onViewDetails={handleViewDetails}
        onPageChange={setPage}
      />

      {/* Delete Confirmation Modal */}
      <DeleteConfirmModal
        isOpen={!!showDeleteConfirm}
        isDeleting={deletingId === showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(null)}
        onConfirm={() => showDeleteConfirm && handleDelete(showDeleteConfirm)}
      />

      {/* Enhancement Detail Modal */}
      <EnhanceDetailModal
        requestId={selectedDetailId}
        isOpen={!!selectedDetailId}
        onClose={() => setSelectedDetailId(null)}
        onActionComplete={handleActionComplete}
      />
    </div>
  );
};
