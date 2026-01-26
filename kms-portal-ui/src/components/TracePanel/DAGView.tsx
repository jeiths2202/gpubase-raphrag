/**
 * DAGView Component
 *
 * Visualizes the task DAG (Directed Acyclic Graph) structure.
 * Shows task nodes with status indicators and dependencies.
 */
import React from 'react';
import {
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Circle,
  ArrowRight,
  AlertCircle,
} from 'lucide-react';
import type { DAGStructure, CurrentTask, SpanStatus } from '../../store/traceStore';
import './DAGView.css';

interface DAGViewProps {
  dag: DAGStructure;
  currentTask: CurrentTask | null;
  t: (key: string) => string;
}

// Agent type colors
const AGENT_COLORS: Record<string, string> = {
  rag: '#3b82f6',      // Blue
  ims: '#8b5cf6',      // Purple
  vision: '#f59e0b',   // Amber
  code: '#10b981',     // Emerald
  planner: '#ec4899',  // Pink
  default: '#6b7280',  // Gray
};

// Status icons
const StatusIcon: React.FC<{ status: SpanStatus; size?: number }> = ({ status, size = 16 }) => {
  switch (status) {
    case 'completed':
      return <CheckCircle size={size} className="dag-status-icon dag-status-icon--completed" />;
    case 'failed':
      return <XCircle size={size} className="dag-status-icon dag-status-icon--failed" />;
    case 'running':
      return <Loader2 size={size} className="dag-status-icon dag-status-icon--running animate-spin" />;
    case 'pending':
      return <Circle size={size} className="dag-status-icon dag-status-icon--pending" />;
    case 'skipped':
      return <AlertCircle size={size} className="dag-status-icon dag-status-icon--skipped" />;
    default:
      return <Clock size={size} className="dag-status-icon dag-status-icon--pending" />;
  }
};

export const DAGView: React.FC<DAGViewProps> = ({ dag, currentTask, t }) => {
  const { tasks, execution_batches, parallelism_type } = dag;

  // Group tasks by batch for visualization
  const batchedTasks = execution_batches.map((batch, batchIndex) => ({
    batchIndex,
    tasks: batch.map((taskId) => tasks.find((t) => t.task_id === taskId)).filter(Boolean),
  }));

  // If no batches defined, create a single batch with all tasks
  const displayBatches = batchedTasks.length > 0
    ? batchedTasks
    : [{ batchIndex: 0, tasks }];

  return (
    <div className="dag-view">
      {/* Parallelism indicator */}
      <div className="dag-view__parallelism">
        <span className={`dag-parallelism-badge dag-parallelism-badge--${parallelism_type}`}>
          {parallelism_type === 'full' && t('trace.fullyParallel') || 'Fully Parallel'}
          {parallelism_type === 'partial' && t('trace.partiallyParallel') || 'Partially Parallel'}
          {parallelism_type === 'pipeline' && t('trace.pipeline') || 'Pipeline'}
          {parallelism_type === 'none' && t('trace.sequential') || 'Sequential'}
        </span>
      </div>

      {/* Batch flow visualization */}
      <div className="dag-flow">
        {displayBatches.map((batch, batchIdx) => (
          <React.Fragment key={batch.batchIndex}>
            {/* Batch container */}
            <div className="dag-batch">
              <div className="dag-batch__header">
                <span className="dag-batch__label">
                  {t('trace.batch') || 'Batch'} {batchIdx + 1}
                </span>
                <span className="dag-batch__count">
                  {batch.tasks.length} {batch.tasks.length === 1 ? 'task' : 'tasks'}
                </span>
              </div>

              <div className="dag-batch__tasks">
                {batch.tasks.map((task) => {
                  if (!task) return null;

                  const isCurrentTask = currentTask?.task_id === task.task_id;
                  const agentColor = AGENT_COLORS[task.agent_type] || AGENT_COLORS.default;

                  return (
                    <div
                      key={task.task_id}
                      className={`dag-task dag-task--${task.status} ${isCurrentTask ? 'dag-task--current' : ''}`}
                      style={{ '--agent-color': agentColor } as React.CSSProperties}
                    >
                      <div className="dag-task__header">
                        <StatusIcon status={task.status} />
                        <span className="dag-task__agent-badge">
                          {task.agent_type.toUpperCase()}
                        </span>
                      </div>

                      <div className="dag-task__body">
                        <p className="dag-task__description" title={task.description}>
                          {task.description.length > 60
                            ? task.description.substring(0, 60) + '...'
                            : task.description}
                        </p>
                      </div>

                      <div className="dag-task__footer">
                        <span className="dag-task__id">{task.task_id}</span>
                        {task.latency_ms && (
                          <span className="dag-task__latency">
                            {task.latency_ms}ms
                          </span>
                        )}
                      </div>

                      {/* Dependencies indicator */}
                      {task.dependencies.length > 0 && (
                        <div className="dag-task__deps">
                          <span title={`Depends on: ${task.dependencies.join(', ')}`}>
                            {task.dependencies.length} dep{task.dependencies.length > 1 ? 's' : ''}
                          </span>
                        </div>
                      )}

                      {/* Error message */}
                      {task.error && (
                        <div className="dag-task__error" title={task.error}>
                          {task.error.substring(0, 50)}...
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Arrow between batches */}
            {batchIdx < displayBatches.length - 1 && (
              <div className="dag-arrow">
                <ArrowRight size={24} />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Legend */}
      <div className="dag-legend">
        <div className="dag-legend__item">
          <Circle size={12} className="dag-status-icon--pending" />
          <span>{t('trace.pending') || 'Pending'}</span>
        </div>
        <div className="dag-legend__item">
          <Loader2 size={12} className="dag-status-icon--running" />
          <span>{t('trace.running') || 'Running'}</span>
        </div>
        <div className="dag-legend__item">
          <CheckCircle size={12} className="dag-status-icon--completed" />
          <span>{t('trace.completed') || 'Completed'}</span>
        </div>
        <div className="dag-legend__item">
          <XCircle size={12} className="dag-status-icon--failed" />
          <span>{t('trace.failed') || 'Failed'}</span>
        </div>
      </div>
    </div>
  );
};

export default DAGView;
