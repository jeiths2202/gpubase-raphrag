/**
 * IMS Progress Tracker Component
 *
 * Real-time progress tracking with SSE events
 */

import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Wifi,
  WifiOff,
  CheckCircle,
  XCircle,
  AlertCircle,
  Search,
  FileText,
  Link2,
  Clock,
} from 'lucide-react';
import { useSSEStream } from '../hooks/useSSEStream';
import { getJobStreamUrl } from '../services/ims-api';
import type { CompletionStats, ProgressStats, ActivityLogEntry, SSEEventData } from '../types';

interface IMSProgressTrackerProps {
  jobId: string;
  onComplete: (stats: CompletionStats) => void;
  onError: (error: string) => void;
  onViewResults: () => void;
  t: (key: string) => string;
}

const MAX_LOG_ENTRIES = 50;

export const IMSProgressTracker: React.FC<IMSProgressTrackerProps> = ({
  jobId,
  onComplete,
  onError,
  onViewResults,
  t,
}) => {
  const [stats, setStats] = useState<ProgressStats>({ found: 0, crawled: 0, related: 0 });
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(t('ims.progress.connecting'));
  const [logs, setLogs] = useState<ActivityLogEntry[]>([]);
  const [isCompleted, setIsCompleted] = useState(false);

  const startTimeRef = useRef(Date.now());
  const completedRef = useRef(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const statsRef = useRef(stats);

  // Keep statsRef in sync with stats
  useEffect(() => {
    statsRef.current = stats;
  }, [stats]);

  const streamUrl = getJobStreamUrl(jobId);
  const { data, isConnected, isReconnecting, error } = useSSEStream(streamUrl);

  // Add log entry
  const addLog = (message: string, type: ActivityLogEntry['type'] = 'info') => {
    const entry: ActivityLogEntry = {
      id: `log-${Date.now()}-${Math.random()}`,
      timestamp: new Date().toLocaleTimeString(),
      message,
      type,
    };

    setLogs((prev) => {
      const newLogs = [...prev, entry];
      return newLogs.slice(-MAX_LOG_ENTRIES);
    });
  };

  // Process SSE events
  useEffect(() => {
    if (!data) return;

    const event = data as SSEEventData;

    switch (event.event) {
      case 'job_started':
        setCurrentStep(t('ims.progress.authenticating'));
        addLog(t('ims.progress.jobStarted'), 'info');
        break;

      case 'authenticating':
        setCurrentStep(t('ims.progress.authenticating'));
        addLog(t('ims.progress.authenticating'), 'info');
        break;

      case 'authenticated':
        setProgress(10);
        addLog(t('ims.progress.authenticated'), 'success');
        break;

      case 'searching':
        setCurrentStep(t('ims.progress.searching'));
        setProgress(15);
        addLog(t('ims.progress.searching'), 'info');
        break;

      case 'search_completed':
        setStats((prev) => ({ ...prev, found: event.total_issues || 0 }));
        setProgress(20);
        addLog(`${t('ims.progress.searchCompleted')}: ${event.total_issues} ${t('ims.results.found').toLowerCase()}`, 'success');
        break;

      case 'crawling_issue':
        setCurrentStep(`${t('ims.progress.crawling')} (${event.issue_number}/${event.total_issues})`);
        setStats((prev) => ({ ...prev, crawled: event.issue_number || prev.crawled }));
        if (event.total_issues && event.issue_number) {
          const crawlProgress = 20 + (event.issue_number / event.total_issues) * 60;
          setProgress(Math.min(crawlProgress, 80));
        }
        if (event.issue_id) {
          addLog(`${t('ims.progress.crawlingIssue')}: ${event.issue_id}`, 'info');
        }
        break;

      case 'related_issues_found':
        const relatedCount = event.related_issues ?? event.related_count ?? 0;
        setStats((prev) => ({ ...prev, related: relatedCount + prev.related }));
        addLog(`${t('ims.progress.relatedFound')}: ${relatedCount}`, 'info');
        break;

      case 'processing_attachments':
        setCurrentStep(t('ims.progress.processing'));
        setProgress(85);
        addLog(t('ims.progress.processing'), 'info');
        break;

      case 'embedding':
        setCurrentStep(t('ims.progress.embedding'));
        setProgress(90);
        addLog(t('ims.progress.embedding'), 'info');
        break;

      case 'job_completed':
        if (!completedRef.current) {
          completedRef.current = true;
          setProgress(100);
          setCurrentStep(t('ims.progress.completed'));
          setIsCompleted(true);
          addLog(t('ims.progress.completed'), 'success');

          const duration = (Date.now() - startTimeRef.current) / 1000;
          const currentStats = statsRef.current;
          // Handle both backend field names (issues_found/issues_crawled) and frontend names (total_issues/crawled_issues)
          const foundCount = event.issues_found ?? event.total_issues ?? currentStats.found;
          const crawledCount = event.issues_crawled ?? event.crawled_issues ?? currentStats.crawled;
          const attachmentsCount = event.attachments_processed ?? event.attachments ?? 0;
          const finalStats: CompletionStats = {
            totalIssues: foundCount,
            successfulIssues: crawledCount,
            duration,
            outcome: 'success',
            relatedIssues: currentStats.related,
            attachments: attachmentsCount,
            resultIssueIds: event.result_issue_ids, // Pass crawled issue IDs for direct fetching
            progressSnapshot: {
              status: 'completed',
              progress: 100,
              currentStep: t('ims.progress.completed'),
              timestamp: new Date().toISOString(),
              issuesFound: foundCount,
              issuesCrawled: crawledCount,
              relatedCount: currentStats.related,
            },
          };
          onComplete(finalStats);
        }
        break;

      case 'job_failed':
      case 'error':
        setCurrentStep(t('ims.progress.failed'));
        addLog(event.error || event.message || t('ims.progress.failed'), 'error');
        onError(event.error || event.message || 'Unknown error');
        break;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Handle connection error
  useEffect(() => {
    if (error) {
      addLog(error, 'error');
    }
  }, [error]);

  return (
    <div className="ims-progress">
      {/* Connection Status */}
      <div className="ims-progress__status">
        <div className={`ims-progress__connection ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? <Wifi size={16} /> : <WifiOff size={16} />}
          <span>
            {isConnected
              ? t('ims.progress.connected')
              : isReconnecting
              ? t('ims.progress.reconnecting')
              : t('ims.progress.disconnected')}
          </span>
        </div>
        <div className="ims-progress__step">
          <Clock size={14} />
          {currentStep}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="ims-progress__bar-container">
        <motion.div
          className="ims-progress__bar"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ type: 'spring', stiffness: 50, damping: 15 }}
        />
        <span className="ims-progress__percentage">{Math.round(progress)}%</span>
      </div>

      {/* Stats Grid */}
      <div className="ims-progress__stats">
        <div className="ims-progress__stat">
          <Search size={18} />
          <div className="ims-progress__stat-content">
            <span className="ims-progress__stat-value">{stats.found}</span>
            <span className="ims-progress__stat-label">{t('ims.results.found')}</span>
          </div>
        </div>
        <div className="ims-progress__stat">
          <FileText size={18} />
          <div className="ims-progress__stat-content">
            <span className="ims-progress__stat-value">{stats.crawled}</span>
            <span className="ims-progress__stat-label">{t('ims.results.crawled')}</span>
          </div>
        </div>
        <div className="ims-progress__stat">
          <Link2 size={18} />
          <div className="ims-progress__stat-content">
            <span className="ims-progress__stat-value">{stats.related}</span>
            <span className="ims-progress__stat-label">{t('ims.results.related')}</span>
          </div>
        </div>
      </div>

      {/* Activity Log */}
      <div className="ims-progress__log">
        <div className="ims-progress__log-header">
          <span>{t('ims.progress.activityLog')}</span>
          <span className="ims-progress__log-count">{logs.length}</span>
        </div>
        <div className="ims-progress__log-content">
          {logs.map((log) => (
            <div key={log.id} className={`ims-progress__log-entry ims-progress__log-entry--${log.type}`}>
              <span className="ims-progress__log-time">{log.timestamp}</span>
              <span className="ims-progress__log-icon">
                {log.type === 'success' && <CheckCircle size={12} />}
                {log.type === 'error' && <XCircle size={12} />}
                {log.type === 'warning' && <AlertCircle size={12} />}
                {log.type === 'info' && <span className="ims-progress__log-dot" />}
              </span>
              <span className="ims-progress__log-message">{log.message}</span>
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* View Results Button */}
      {isCompleted && (
        <div className="ims-progress__actions">
          <button className="btn btn-primary" onClick={onViewResults}>
            {t('ims.progress.viewResults')}
          </button>
        </div>
      )}
    </div>
  );
};

export default IMSProgressTracker;
