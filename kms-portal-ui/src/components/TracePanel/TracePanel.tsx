/**
 * TracePanel Component
 *
 * Right-side panel for agent execution trace visualization.
 * Displays DAG structure, timeline, and evaluation details.
 */
import React, { useRef, useCallback, useState, useEffect } from 'react';
import {
  X,
  GitBranch,
  Clock,
  CheckCircle2,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useTraceStore, type ViewMode } from '../../store/traceStore';
import { DAGView } from './DAGView';
import { TimelineView } from './TimelineView';
import { EvaluationsView } from './EvaluationsView';
import './TracePanel.css';

// Panel size constraints
const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 800;

interface TracePanelProps {
  t: (key: string) => string;
}

export const TracePanel: React.FC<TracePanelProps> = ({ t }) => {
  const {
    panel,
    currentTrace,
    closePanel,
    setPanelWidth,
    setViewMode,
  } = useTraceStore();

  const panelRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Resize handlers
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !panelRef.current) return;

      const panelRect = panelRef.current.getBoundingClientRect();
      const newWidth = panelRect.right - e.clientX;
      const clampedWidth = Math.min(Math.max(newWidth, MIN_PANEL_WIDTH), MAX_PANEL_WIDTH);
      setPanelWidth(clampedWidth);
    },
    [isDragging, setPanelWidth]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Attach global mouse listeners for resize
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Don't render if panel is closed
  if (!panel.isOpen) {
    return null;
  }

  const { dag, timeline, evaluations, currentTask } = currentTrace;

  // Count stats
  const totalTasks = dag?.tasks.length ?? 0;
  const completedTasks = dag?.tasks.filter((t) => t.status === 'completed').length ?? 0;
  const failedTasks = dag?.tasks.filter((t) => t.status === 'failed').length ?? 0;
  const runningTasks = dag?.tasks.filter((t) => t.status === 'running').length ?? 0;

  const tabs: { id: ViewMode; label: string; icon: React.ReactNode }[] = [
    { id: 'dag', label: 'DAG', icon: <GitBranch size={14} /> },
    { id: 'timeline', label: t('trace.timeline') || 'Timeline', icon: <Clock size={14} /> },
    { id: 'details', label: t('trace.evaluations') || 'Evaluations', icon: <CheckCircle2 size={14} /> },
  ];

  return (
    <div
      ref={panelRef}
      className={`trace-panel ${isFullscreen ? 'trace-panel--fullscreen' : ''}`}
      style={{ width: isFullscreen ? '100%' : panel.width }}
    >
      {/* Resize handle */}
      {!isFullscreen && (
        <div
          className="trace-panel__resize-handle"
          onMouseDown={handleMouseDown}
        />
      )}

      {/* Header */}
      <div className="trace-panel__header">
        <div className="trace-panel__title">
          <GitBranch size={18} />
          <span>{t('trace.executionTrace') || 'Execution Trace'}</span>
        </div>

        <div className="trace-panel__header-actions">
          <button
            className="trace-panel__icon-btn"
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <button
            className="trace-panel__icon-btn"
            onClick={closePanel}
            title="Close"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {dag && (
        <div className="trace-panel__stats">
          <div className="trace-panel__stat">
            <span className="trace-panel__stat-label">{t('trace.total') || 'Total'}</span>
            <span className="trace-panel__stat-value">{totalTasks}</span>
          </div>
          <div className="trace-panel__stat trace-panel__stat--running">
            <span className="trace-panel__stat-label">{t('trace.running') || 'Running'}</span>
            <span className="trace-panel__stat-value">{runningTasks}</span>
          </div>
          <div className="trace-panel__stat trace-panel__stat--completed">
            <span className="trace-panel__stat-label">{t('trace.completed') || 'Done'}</span>
            <span className="trace-panel__stat-value">{completedTasks}</span>
          </div>
          <div className="trace-panel__stat trace-panel__stat--failed">
            <span className="trace-panel__stat-label">{t('trace.failed') || 'Failed'}</span>
            <span className="trace-panel__stat-value">{failedTasks}</span>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="trace-panel__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`trace-panel__tab ${panel.viewMode === tab.id ? 'trace-panel__tab--active' : ''}`}
            onClick={() => setViewMode(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="trace-panel__content">
        {!dag ? (
          <div className="trace-panel__empty">
            <GitBranch size={48} strokeWidth={1} />
            <p>{t('trace.noData') || 'No trace data available'}</p>
            <p className="trace-panel__empty-hint">
              {t('trace.noDataHint') || 'Trace data will appear when an enterprise multi-agent task runs'}
            </p>
          </div>
        ) : (
          <>
            {panel.viewMode === 'dag' && (
              <DAGView dag={dag} currentTask={currentTask} t={t} />
            )}
            {panel.viewMode === 'timeline' && (
              <TimelineView timeline={timeline} dag={dag} t={t} />
            )}
            {panel.viewMode === 'details' && (
              <EvaluationsView evaluations={evaluations} dag={dag} t={t} />
            )}
          </>
        )}
      </div>

      {/* Footer */}
      {dag && (
        <div className="trace-panel__footer">
          <span className="trace-panel__parallelism">
            {t('trace.parallelism') || 'Parallelism'}: {dag.parallelism_type}
          </span>
          <span className="trace-panel__events">
            {timeline.length} {t('trace.events') || 'events'}
          </span>
        </div>
      )}
    </div>
  );
};

export default TracePanel;
