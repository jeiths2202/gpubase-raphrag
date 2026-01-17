/**
 * TimelineView Component
 *
 * Displays execution timeline with chronological events.
 */
import React, { useRef, useEffect } from 'react';
import {
  Play,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
  AlertTriangle,
  Zap,
} from 'lucide-react';
import type { TimelineEvent, DAGStructure } from '../../store/traceStore';
import './TimelineView.css';

interface TimelineViewProps {
  timeline: TimelineEvent[];
  dag: DAGStructure | null;
  t: (key: string) => string;
}

// Event type icons
const EventIcon: React.FC<{ event: string; size?: number }> = ({ event, size = 14 }) => {
  switch (event) {
    case 'task_start':
      return <Play size={size} className="timeline-icon timeline-icon--start" />;
    case 'task_complete':
      return <CheckCircle size={size} className="timeline-icon timeline-icon--complete" />;
    case 'task_failed':
    case 'task_timeout':
      return <XCircle size={size} className="timeline-icon timeline-icon--failed" />;
    case 'evaluation':
      return <Zap size={size} className="timeline-icon timeline-icon--eval" />;
    case 'retry':
      return <RefreshCw size={size} className="timeline-icon timeline-icon--retry" />;
    default:
      return <Clock size={size} className="timeline-icon timeline-icon--default" />;
  }
};

// Format timestamp
const formatTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  } catch {
    return '--:--:--';
  }
};

// Get event display name
const getEventName = (event: string, t: (key: string) => string): string => {
  const eventNames: Record<string, string> = {
    task_start: t('trace.event.taskStart') || 'Task Started',
    task_complete: t('trace.event.taskComplete') || 'Task Completed',
    task_failed: t('trace.event.taskFailed') || 'Task Failed',
    task_timeout: t('trace.event.taskTimeout') || 'Task Timeout',
    evaluation: t('trace.event.evaluation') || 'Evaluation',
    retry: t('trace.event.retry') || 'Retry',
  };
  return eventNames[event] || event;
};

export const TimelineView: React.FC<TimelineViewProps> = ({ timeline, dag, t }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [timeline.length]);

  if (timeline.length === 0) {
    return (
      <div className="timeline-empty">
        <Clock size={48} strokeWidth={1} />
        <p>{t('trace.noEvents') || 'No events yet'}</p>
      </div>
    );
  }

  // Calculate relative timing
  const firstTimestamp = timeline[0]?.timestamp ? new Date(timeline[0].timestamp).getTime() : 0;

  return (
    <div className="timeline-view" ref={containerRef}>
      <div className="timeline-track">
        {timeline.map((event, index) => {
          const eventTime = new Date(event.timestamp).getTime();
          const relativeTime = Math.round((eventTime - firstTimestamp) / 1000);

          const task = dag?.tasks.find((t) => t.task_id === event.task_id);
          const isSuccess = event.success === true;
          const isFailed = event.success === false;

          return (
            <div
              key={`${event.timestamp}-${index}`}
              className={`timeline-event ${isFailed ? 'timeline-event--failed' : ''} ${isSuccess ? 'timeline-event--success' : ''}`}
            >
              {/* Timeline dot and line */}
              <div className="timeline-marker">
                <div className={`timeline-dot ${event.event === 'task_complete' ? 'timeline-dot--success' : ''} ${event.event === 'task_failed' || event.event === 'task_timeout' ? 'timeline-dot--failed' : ''}`}>
                  <EventIcon event={event.event} />
                </div>
                {index < timeline.length - 1 && <div className="timeline-line" />}
              </div>

              {/* Event content */}
              <div className="timeline-content">
                <div className="timeline-header">
                  <span className="timeline-time">
                    {formatTime(event.timestamp)}
                    <span className="timeline-relative">+{relativeTime}s</span>
                  </span>
                  <span className={`timeline-event-type timeline-event-type--${event.event}`}>
                    {getEventName(event.event, t)}
                  </span>
                </div>

                {event.task_id && (
                  <div className="timeline-task">
                    <span className="timeline-task-id">{event.task_id}</span>
                    {event.agent_type && (
                      <span className="timeline-agent">{event.agent_type}</span>
                    )}
                  </div>
                )}

                {/* Task description */}
                {task && (
                  <p className="timeline-description">{task.description.substring(0, 80)}...</p>
                )}

                {/* Latency */}
                {event.latency_ms && (
                  <span className="timeline-latency">{event.latency_ms}ms</span>
                )}

                {/* Error */}
                {event.error && (
                  <div className="timeline-error">
                    <AlertTriangle size={12} />
                    <span>{event.error.substring(0, 100)}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TimelineView;
