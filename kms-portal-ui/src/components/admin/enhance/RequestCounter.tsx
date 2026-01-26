/**
 * Request Counter Component
 * Displays the current count of running and queued tasks
 */
import React from 'react';
import { Activity, Zap, List, Loader2, CheckCircle } from 'lucide-react';

interface RequestCounterProps {
  runningCount: number;
  queuedCount: number;
  isProcessing: boolean;
}

export const RequestCounter: React.FC<RequestCounterProps> = ({
  runningCount,
  queuedCount,
  isProcessing,
}) => {
  const totalCount = runningCount + queuedCount;

  return (
    <section className="admin-request-counter-section">
      <div className="admin-request-counter">
        <div className="admin-request-counter-icon">
          <Activity size={32} />
        </div>
        <div className="admin-request-counter-info">
          <span className="admin-request-counter-label">Request Counter</span>
          <span className="admin-request-counter-value">{totalCount}</span>
          <span className="admin-request-counter-detail">
            <span className="counter-running">
              <Zap size={14} />
              {runningCount} Running
            </span>
            <span className="counter-queued">
              <List size={14} />
              {queuedCount} Queued
            </span>
          </span>
        </div>
        <div className="admin-request-counter-indicator">
          {isProcessing ? (
            <span className="indicator-active">
              <Loader2 size={20} className="spinning" />
              Processing
            </span>
          ) : (
            <span className="indicator-idle">
              <CheckCircle size={20} />
              Idle
            </span>
          )}
        </div>
      </div>
    </section>
  );
};
