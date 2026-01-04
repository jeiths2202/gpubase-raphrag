/**
 * IMS Crawl Job Progress Component
 * Real-time SSE-based progress tracking for crawl jobs
 */

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSSEStream, SSEEvent } from '../hooks/useSSEStream';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  jobId: string;
  t: TranslateFunction;
  onComplete?: (jobId: string) => void;
  onError?: (error: string) => void;
}

interface ProgressState {
  status: string;
  currentStep: string;
  progress: number;
  issuesFound: number;
  issuesCrawled: number;
  currentIssueId?: string;
  relatedCount?: number;
}

export const IMSCrawlJobProgress: React.FC<Props> = ({
  jobId,
  t,
  onComplete,
  onError
}) => {
  const [progressState, setProgressState] = useState<ProgressState>({
    status: 'pending',
    currentStep: 'Initializing...',
    progress: 0,
    issuesFound: 0,
    issuesCrawled: 0
  });

  const [logs, setLogs] = useState<string[]>([]);

  const { data, events, isConnected, isReconnecting, error } = useSSEStream(
    `/api/v1/ims-jobs/${jobId}/stream`,
    {
      autoConnect: true,
      onOpen: () => {
        console.log('SSE connected');
        addLog('Connected to job stream');
      },
      onClose: () => {
        console.log('SSE disconnected');
        addLog('Disconnected from job stream');
      },
      onError: (e) => {
        console.error('SSE error:', e);
        addLog('Connection error occurred');
      }
    }
  );

  const addLog = (message: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev, `[${timestamp}] ${message}`]);
  };

  // Process SSE events
  useEffect(() => {
    if (!data) return;

    const event = data.event;

    switch (event) {
      case 'job_started':
        setProgressState(prev => ({
          ...prev,
          status: 'running',
          currentStep: 'Starting job...'
        }));
        addLog('Job started');
        break;

      case 'authenticating':
        setProgressState(prev => ({
          ...prev,
          currentStep: 'Authenticating...'
        }));
        addLog('Authenticating with IMS system');
        break;

      case 'authenticated':
        setProgressState(prev => ({
          ...prev,
          currentStep: 'Authentication successful'
        }));
        addLog('Authentication successful');
        break;

      case 'searching':
        setProgressState(prev => ({
          ...prev,
          currentStep: `Searching: ${data.message || 'Executing search...'}`
        }));
        addLog(`Searching for issues`);
        break;

      case 'search_completed':
        setProgressState(prev => ({
          ...prev,
          issuesFound: data.total_issues || 0,
          currentStep: `Found ${data.total_issues} issues`
        }));
        addLog(`Found ${data.total_issues} issues`);
        break;

      case 'crawling_issue':
        setProgressState(prev => ({
          ...prev,
          currentStep: `Crawling issue ${data.issue_number}/${data.total_issues}`,
          progress: Math.round((data.issue_number / data.total_issues) * 100),
          currentIssueId: data.issue_id
        }));
        addLog(`Crawling issue: ${data.issue_id}`);
        break;

      case 'related_issues_found':
        setProgressState(prev => ({
          ...prev,
          relatedCount: (prev.relatedCount || 0) + data.related_count
        }));
        addLog(`Found ${data.related_count} related issues`);
        break;

      case 'issue_completed':
        setProgressState(prev => ({
          ...prev,
          issuesCrawled: data.crawled_count || prev.issuesCrawled + 1,
          progress: Math.round((data.issue_number / data.total_issues) * 100)
        }));
        break;

      case 'issue_failed':
        addLog(`Failed to crawl issue ${data.issue_id}: ${data.error}`);
        break;

      case 'job_completed':
        setProgressState(prev => ({
          ...prev,
          status: 'completed',
          currentStep: 'Job completed',
          progress: 100
        }));
        addLog(`Job completed: ${data.crawled_issues} issues crawled`);
        if (onComplete) {
          onComplete(jobId);
        }
        break;

      case 'job_failed':
        setProgressState(prev => ({
          ...prev,
          status: 'failed',
          currentStep: 'Job failed'
        }));
        addLog(`Job failed: ${data.error}`);
        if (onError) {
          onError(data.error);
        }
        break;

      case 'error':
        addLog(`Error: ${data.message}`);
        if (onError) {
          onError(data.message);
        }
        break;
    }
  }, [data, jobId, onComplete, onError]);

  // Handle connection errors
  useEffect(() => {
    if (error && onError) {
      onError(error);
    }
  }, [error, onError]);

  const getStatusColor = () => {
    switch (progressState.status) {
      case 'completed': return '#10b981';
      case 'failed': return '#ef4444';
      case 'running': return '#6366f1';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{
      padding: '24px',
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px',
      marginBottom: '20px'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '20px'
      }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
          Crawl Job Progress
        </h3>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          {isReconnecting && (
            <span style={{ fontSize: '13px', color: '#f59e0b' }}>
              Reconnecting...
            </span>
          )}
          <div style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: isConnected ? '#10b981' : '#6b7280'
          }} />
          <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>

      {/* Progress Bar */}
      <div style={{ marginBottom: '20px' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          marginBottom: '8px'
        }}>
          <span style={{ fontSize: '14px', fontWeight: 500 }}>
            {progressState.currentStep}
          </span>
          <span style={{
            fontSize: '14px',
            fontWeight: 600,
            color: getStatusColor()
          }}>
            {progressState.progress}%
          </span>
        </div>
        <div style={{
          width: '100%',
          height: '10px',
          background: 'var(--input-bg)',
          borderRadius: '5px',
          overflow: 'hidden'
        }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progressState.progress}%` }}
            transition={{ duration: 0.3 }}
            style={{
              height: '100%',
              background: getStatusColor(),
              borderRadius: '5px'
            }}
          />
        </div>
      </div>

      {/* Statistics */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: '16px',
        marginBottom: '20px'
      }}>
        <StatCard
          label="Issues Found"
          value={progressState.issuesFound}
          icon="🔍"
        />
        <StatCard
          label="Issues Crawled"
          value={progressState.issuesCrawled}
          icon="✓"
        />
        {progressState.relatedCount !== undefined && (
          <StatCard
            label="Related Issues"
            value={progressState.relatedCount}
            icon="🔗"
          />
        )}
        {progressState.currentIssueId && (
          <StatCard
            label="Current Issue"
            value={progressState.currentIssueId}
            icon="📝"
          />
        )}
      </div>

      {/* Event Log */}
      <details style={{ marginTop: '20px' }}>
        <summary style={{
          cursor: 'pointer',
          fontSize: '14px',
          fontWeight: 500,
          color: 'var(--text-secondary)',
          padding: '8px',
          borderRadius: '6px',
          background: 'var(--input-bg)'
        }}>
          Event Log ({logs.length})
        </summary>
        <div style={{
          marginTop: '12px',
          maxHeight: '200px',
          overflowY: 'auto',
          fontSize: '12px',
          fontFamily: 'monospace',
          background: 'var(--bg)',
          padding: '12px',
          borderRadius: '6px'
        }}>
          <AnimatePresence>
            {logs.map((log, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                style={{
                  padding: '4px 0',
                  color: 'var(--text-secondary)'
                }}
              >
                {log}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </details>
    </div>
  );
};

interface StatCardProps {
  label: string;
  value: string | number;
  icon: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon }) => (
  <div style={{
    padding: '12px',
    background: 'var(--input-bg)',
    borderRadius: '8px'
  }}>
    <div style={{
      fontSize: '20px',
      marginBottom: '4px'
    }}>
      {icon}
    </div>
    <div style={{
      fontSize: '20px',
      fontWeight: 600,
      marginBottom: '2px'
    }}>
      {value}
    </div>
    <div style={{
      fontSize: '12px',
      color: 'var(--text-secondary)'
    }}>
      {label}
    </div>
  </div>
);
