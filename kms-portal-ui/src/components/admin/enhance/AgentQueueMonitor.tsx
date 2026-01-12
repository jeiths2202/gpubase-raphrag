/**
 * Agent Queue Monitor Component
 * Displays agent status cards, running tasks, queued tasks, and task history
 */
import React from 'react';
import {
  Cpu,
  RefreshCw,
  Zap,
  List,
  Clock,
  Loader2,
  Square,
  XCircle,
  Trash2,
  CheckCircle,
  PauseCircle,
} from 'lucide-react';
import type { QueueStatus, QueuedTask, AgentStatus } from './types';
import { getAgentDisplayName, getAgentIcon, formatDurationMs } from './utils';

interface AgentQueueMonitorProps {
  queueStatus: QueueStatus | null;
  loading: boolean;
  showPanel: boolean;
  stoppingTaskId: string | null;
  stoppingAgentType: string | null;
  clearingQueue: boolean;
  onTogglePanel: () => void;
  onRefresh: () => void;
  onForceStopTask: (taskId: string) => void;
  onForceStopAgent: (agentType: string) => void;
  onClearQueue: () => void;
}

// Agent Status Card Sub-component
const AgentStatusCard: React.FC<{
  agentType: string;
  status: AgentStatus;
  stoppingAgentType: string | null;
  onForceStop: (agentType: string) => void;
}> = ({ agentType, status, stoppingAgentType, onForceStop }) => (
  <div
    className={`admin-agent-card ${status.is_running ? 'admin-agent-card--running' : 'admin-agent-card--idle'}`}
  >
    <div className="admin-agent-card-header">
      <div className="admin-agent-icon">{getAgentIcon(agentType)}</div>
      <div className="admin-agent-info">
        <span className="admin-agent-name">{getAgentDisplayName(agentType)}</span>
        <span className={`admin-agent-status-badge ${status.is_running ? 'running' : 'idle'}`}>
          {status.is_running ? (
            <>
              <Zap size={12} />
              Running
            </>
          ) : (
            <>
              <PauseCircle size={12} />
              Idle
            </>
          )}
        </span>
      </div>
      {status.is_running && (
        <button
          className="admin-btn admin-btn--danger admin-btn--sm"
          onClick={() => onForceStop(agentType)}
          disabled={stoppingAgentType === agentType}
          title="Force Stop Agent"
        >
          {stoppingAgentType === agentType ? (
            <Loader2 size={14} className="spinning" />
          ) : (
            <Square size={14} />
          )}
        </button>
      )}
    </div>
    {status.is_running && status.current_task && (
      <div className="admin-agent-task-info">
        <span className="admin-agent-task-op">{status.current_task.operation}</span>
        <span className="admin-agent-task-duration">
          {formatDurationMs(status.current_task.duration_ms)}
        </span>
      </div>
    )}
    <div className="admin-agent-stats">
      <span>Processed: {status.total_processed}</span>
      <span>Failed: {status.total_failed}</span>
    </div>
  </div>
);

// Running Task Item Sub-component
const RunningTaskItem: React.FC<{
  task: QueuedTask;
  stoppingTaskId: string | null;
  onForceStop: (taskId: string) => void;
}> = ({ task, stoppingTaskId, onForceStop }) => (
  <div className="admin-queue-task admin-queue-task--running">
    <div className="admin-queue-task-icon">{getAgentIcon(task.agent_type)}</div>
    <div className="admin-queue-task-info">
      <span className="admin-queue-task-op">{task.operation}</span>
      <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
      <span className="admin-queue-task-id">Enhancement: {task.enhancement_id.slice(0, 8)}...</span>
    </div>
    <div className="admin-queue-task-duration">{formatDurationMs(task.duration_ms)}</div>
    <button
      className="admin-btn admin-btn--danger admin-btn--sm"
      onClick={() => onForceStop(task.id)}
      disabled={stoppingTaskId === task.id}
      title="Force Stop Task"
    >
      {stoppingTaskId === task.id ? (
        <Loader2 size={14} className="spinning" />
      ) : (
        <XCircle size={14} />
      )}
    </button>
  </div>
);

// Queued Task Item Sub-component
const QueuedTaskItem: React.FC<{
  task: QueuedTask;
  position: number;
}> = ({ task, position }) => (
  <div className="admin-queue-task admin-queue-task--queued">
    <div className="admin-queue-task-position">#{position}</div>
    <div className="admin-queue-task-icon">{getAgentIcon(task.agent_type)}</div>
    <div className="admin-queue-task-info">
      <span className="admin-queue-task-op">{task.operation}</span>
      <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
      <span className="admin-queue-task-id">Enhancement: {task.enhancement_id.slice(0, 8)}...</span>
    </div>
    <div className="admin-queue-task-user">by {task.user_name}</div>
  </div>
);

// History Task Item Sub-component
const HistoryTaskItem: React.FC<{
  task: QueuedTask;
}> = ({ task }) => (
  <div className={`admin-queue-task admin-queue-task--${task.status}`}>
    <div className="admin-queue-task-icon">
      {task.status === 'completed' ? (
        <CheckCircle size={16} className="text-success" />
      ) : task.status === 'failed' ? (
        <XCircle size={16} className="text-danger" />
      ) : task.status === 'cancelled' ? (
        <Square size={16} className="text-warning" />
      ) : (
        getAgentIcon(task.agent_type)
      )}
    </div>
    <div className="admin-queue-task-info">
      <span className="admin-queue-task-op">{task.operation}</span>
      <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
    </div>
    <div className="admin-queue-task-status">
      <span className={`admin-queue-status-badge admin-queue-status-badge--${task.status}`}>
        {task.status}
      </span>
    </div>
    <div className="admin-queue-task-duration">{formatDurationMs(task.duration_ms)}</div>
  </div>
);

export const AgentQueueMonitor: React.FC<AgentQueueMonitorProps> = ({
  queueStatus,
  loading,
  showPanel,
  stoppingTaskId,
  stoppingAgentType,
  clearingQueue,
  onTogglePanel,
  onRefresh,
  onForceStopTask,
  onForceStopAgent,
  onClearQueue,
}) => {
  return (
    <section className="admin-queue-monitoring">
      <div className="admin-queue-header">
        <h3 className="admin-section-title">
          <Cpu size={20} />
          Agent Queue Monitor
        </h3>
        <div className="admin-queue-actions">
          <button
            className="admin-btn admin-btn--secondary admin-btn--sm"
            onClick={onTogglePanel}
          >
            {showPanel ? 'Hide' : 'Show'} Details
          </button>
          <button
            className={`admin-btn admin-btn--sm ${loading ? 'admin-btn--loading' : ''}`}
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Agent Status Cards */}
      <div className="admin-agent-status-grid">
        {queueStatus &&
          Object.entries(queueStatus.agents).map(([agentType, status]) => (
            <AgentStatusCard
              key={agentType}
              agentType={agentType}
              status={status}
              stoppingAgentType={stoppingAgentType}
              onForceStop={onForceStopAgent}
            />
          ))}
      </div>

      {showPanel && (
        <>
          {/* Running Tasks */}
          {queueStatus && queueStatus.running_tasks.length > 0 && (
            <div className="admin-queue-section">
              <div className="admin-queue-section-header">
                <h4>
                  <Zap size={16} />
                  Running Tasks ({queueStatus.running_tasks.length})
                </h4>
              </div>
              <div className="admin-queue-tasks">
                {queueStatus.running_tasks.map((task) => (
                  <RunningTaskItem
                    key={task.id}
                    task={task}
                    stoppingTaskId={stoppingTaskId}
                    onForceStop={onForceStopTask}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Queued Tasks */}
          <div className="admin-queue-section">
            <div className="admin-queue-section-header">
              <h4>
                <List size={16} />
                Queued Tasks ({queueStatus?.queue.total_queued || 0})
              </h4>
              {queueStatus && queueStatus.queue.total_queued > 0 && (
                <button
                  className="admin-btn admin-btn--danger admin-btn--sm"
                  onClick={onClearQueue}
                  disabled={clearingQueue}
                  title="Clear All Queued Tasks"
                >
                  {clearingQueue ? (
                    <Loader2 size={14} className="spinning" />
                  ) : (
                    <>
                      <Trash2 size={14} />
                      Clear Queue
                    </>
                  )}
                </button>
              )}
            </div>
            {queueStatus && queueStatus.queue.tasks.length > 0 ? (
              <div className="admin-queue-tasks">
                {queueStatus.queue.tasks.map((task, index) => (
                  <QueuedTaskItem key={task.id} task={task} position={index + 1} />
                ))}
              </div>
            ) : (
              <div className="admin-queue-empty">
                <CheckCircle size={24} />
                <span>No tasks in queue</span>
              </div>
            )}
          </div>

          {/* Recent History */}
          {queueStatus && queueStatus.recent_history.length > 0 && (
            <div className="admin-queue-section">
              <div className="admin-queue-section-header">
                <h4>
                  <Clock size={16} />
                  Recent History
                </h4>
              </div>
              <div className="admin-queue-tasks">
                {queueStatus.recent_history.slice(0, 5).map((task) => (
                  <HistoryTaskItem key={task.id} task={task} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
};
