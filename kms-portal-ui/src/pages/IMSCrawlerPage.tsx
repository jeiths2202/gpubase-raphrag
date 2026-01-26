/**
 * IMS Crawler Page
 *
 * Phase 3: IMS Crawler management page with dashboard, job management,
 * settings panel, and real-time log viewer
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Play,
  Square,
  Pause,
  RotateCcw,
  Plus,
  RefreshCw,
  Settings,
  Activity,
  FileText,
  AlertCircle,
  CheckCircle,
  Clock,
  Globe,
  Trash2,
  Eye,
  X,
  ChevronUp,
  Loader2,
  Info,
  AlertTriangle,
  Bug,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './IMSCrawlerPage.css';

// Types
type CrawlerStatus = 'idle' | 'running' | 'paused' | 'completed' | 'failed';
type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'paused';
type LogLevel = 'info' | 'warning' | 'error' | 'debug';

interface CrawlerState {
  status: CrawlerStatus;
  progress: number;
  currentUrl: string | null;
  startTime: string | null;
  estimatedRemaining: number | null;
}

interface CrawlJob {
  id: string;
  name: string;
  url: string;
  description: string;
  status: JobStatus;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
  progress: number;
}

interface CrawlStats {
  totalDocuments: number;
  newDocuments: number;
  updatedDocuments: number;
  failedDocuments: number;
  lastUpdated: string;
}

interface CrawlerSettings {
  depth: number;
  interval: number;
  timeout: number;
  documentTypes: string[];
}

interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  source: string;
}

interface JobsResponse {
  items: CrawlJob[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

interface LogsResponse {
  items: LogEntry[];
  total: number;
}

// Status badge colors
const statusColors: Record<CrawlerStatus | JobStatus, string> = {
  idle: 'neutral',
  pending: 'neutral',
  running: 'primary',
  paused: 'warning',
  completed: 'success',
  failed: 'error',
};

// Status icons
const StatusIcon: React.FC<{ status: CrawlerStatus | JobStatus; size?: number }> = ({
  status,
  size = 16,
}) => {
  switch (status) {
    case 'running':
      return <Loader2 size={size} className="ims-icon-spin" />;
    case 'paused':
      return <Pause size={size} />;
    case 'completed':
      return <CheckCircle size={size} />;
    case 'failed':
      return <AlertCircle size={size} />;
    case 'pending':
      return <Clock size={size} />;
    default:
      return <Activity size={size} />;
  }
};

// Log level icons
const LogLevelIcon: React.FC<{ level: LogLevel; size?: number }> = ({ level, size = 14 }) => {
  switch (level) {
    case 'error':
      return <AlertCircle size={size} className="ims-log-icon--error" />;
    case 'warning':
      return <AlertTriangle size={size} className="ims-log-icon--warning" />;
    case 'debug':
      return <Bug size={size} className="ims-log-icon--debug" />;
    default:
      return <Info size={size} className="ims-log-icon--info" />;
  }
};

// Document type options
const DOCUMENT_TYPES = ['html', 'pdf', 'doc', 'docx', 'md', 'txt', 'json', 'xml'];

export const IMSCrawlerPage: React.FC = () => {
  const { t } = useTranslation();

  // State
  const [crawlerState, setCrawlerState] = useState<CrawlerState>({
    status: 'idle',
    progress: 0,
    currentUrl: null,
    startTime: null,
    estimatedRemaining: null,
  });
  const [stats, setStats] = useState<CrawlStats | null>(null);
  const [jobs, setJobs] = useState<CrawlJob[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [settings, setSettings] = useState<CrawlerSettings>({
    depth: 3,
    interval: 2,
    timeout: 30,
    documentTypes: ['html', 'pdf', 'doc', 'docx', 'md', 'txt'],
  });

  // UI State
  const [isLoading, setIsLoading] = useState(true);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [showNewJobModal, setShowNewJobModal] = useState(false);
  const [showJobDetailModal, setShowJobDetailModal] = useState<CrawlJob | null>(null);
  const [showSettingsPanel, setShowSettingsPanel] = useState(false);
  const [logFilter, setLogFilter] = useState<LogLevel | 'all'>('all');

  // Form state
  const [newJobForm, setNewJobForm] = useState({
    name: '',
    url: '',
    description: '',
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});

  // Refs
  const logContainerRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch crawler status
  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/ims/status');
      const data = await response.json();
      setCrawlerState(data);
    } catch (error) {
      console.error('Failed to fetch crawler status:', error);
    }
  }, []);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/ims/stats');
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  }, []);

  // Fetch jobs
  const fetchJobs = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/ims/jobs');
      const data: JobsResponse = await response.json();
      setJobs(data.items);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
    }
  }, []);

  // Fetch logs
  const fetchLogs = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (logFilter !== 'all') params.append('level', logFilter);
      params.append('limit', '50');

      const response = await fetch(`/api/v1/ims/logs?${params}`);
      const data: LogsResponse = await response.json();
      setLogs(data.items);
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    }
  }, [logFilter]);

  // Fetch settings
  const fetchSettings = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/ims/settings');
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error('Failed to fetch settings:', error);
    }
  }, []);

  // Initial data fetch
  useEffect(() => {
    const fetchAllData = async () => {
      setIsLoading(true);
      await Promise.all([fetchStatus(), fetchStats(), fetchJobs(), fetchLogs(), fetchSettings()]);
      setIsLoading(false);
    };
    fetchAllData();
  }, [fetchStatus, fetchStats, fetchJobs, fetchLogs, fetchSettings]);

  // Polling for status updates when running
  useEffect(() => {
    if (crawlerState.status === 'running') {
      pollingRef.current = setInterval(() => {
        fetchStatus();
        fetchLogs();
      }, 2000);
    } else {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [crawlerState.status, fetchStatus, fetchLogs]);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = 0;
    }
  }, [logs]);

  // Crawler control actions
  const handleStart = async () => {
    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/start', { method: 'POST' });
      if (response.ok) {
        await fetchStatus();
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to start crawler:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleStop = async () => {
    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/stop', { method: 'POST' });
      if (response.ok) {
        await fetchStatus();
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to stop crawler:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handlePause = async () => {
    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/pause', { method: 'POST' });
      if (response.ok) {
        await fetchStatus();
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to pause crawler:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleResume = async () => {
    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/resume', { method: 'POST' });
      if (response.ok) {
        await fetchStatus();
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to resume crawler:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Job management
  const validateNewJobForm = () => {
    const errors: Record<string, string> = {};

    if (!newJobForm.name.trim()) {
      errors.name = t('ims.newJobForm.validation.nameRequired');
    }

    if (!newJobForm.url.trim()) {
      errors.url = t('ims.newJobForm.validation.urlRequired');
    } else {
      try {
        new URL(newJobForm.url);
      } catch {
        errors.url = t('ims.newJobForm.validation.urlInvalid');
      }
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleCreateJob = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateNewJobForm()) return;

    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newJobForm),
      });

      if (response.ok) {
        await fetchJobs();
        await fetchLogs();
        setShowNewJobModal(false);
        setNewJobForm({ name: '', url: '', description: '' });
      }
    } catch (error) {
      console.error('Failed to create job:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    setIsActionLoading(true);
    try {
      const response = await fetch(`/api/v1/ims/jobs/${jobId}`, { method: 'DELETE' });
      if (response.ok) {
        await fetchJobs();
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to delete job:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  // Settings management
  const handleSaveSettings = async () => {
    setIsActionLoading(true);
    try {
      const response = await fetch('/api/v1/ims/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });

      if (response.ok) {
        await fetchLogs();
      }
    } catch (error) {
      console.error('Failed to save settings:', error);
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleResetSettings = () => {
    setSettings({
      depth: 3,
      interval: 2,
      timeout: 30,
      documentTypes: ['html', 'pdf', 'doc', 'docx', 'md', 'txt'],
    });
  };

  // Log management
  const handleClearLogs = async () => {
    try {
      const response = await fetch('/api/v1/ims/logs', { method: 'DELETE' });
      if (response.ok) {
        setLogs([]);
      }
    } catch (error) {
      console.error('Failed to clear logs:', error);
    }
  };

  // Format helpers
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatTime = (dateString: string) => {
    return new Date(dateString).toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatDuration = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) return `${hrs}h ${mins}m`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  // Refresh all data
  const handleRefreshAll = async () => {
    setIsLoading(true);
    await Promise.all([fetchStatus(), fetchStats(), fetchJobs(), fetchLogs()]);
    setIsLoading(false);
  };

  if (isLoading) {
    return (
      <div className="ims-page ims-page--loading">
        <Loader2 size={48} className="ims-icon-spin" />
        <p>Loading IMS Crawler...</p>
      </div>
    );
  }

  return (
    <div className="ims-page">
      {/* Page Header */}
      <header className="ims-header">
        <div className="ims-header__content">
          <h1 className="ims-header__title">{t('ims.title')}</h1>
          <p className="ims-header__description">{t('ims.description')}</p>
        </div>
        <div className="ims-header__actions">
          <button
            className="btn btn-secondary btn-icon"
            onClick={handleRefreshAll}
            disabled={isLoading}
          >
            <RefreshCw size={18} />
            {t('ims.actions.refresh')}
          </button>
          <button
            className="btn btn-secondary btn-icon"
            onClick={() => setShowSettingsPanel(!showSettingsPanel)}
          >
            <Settings size={18} />
            {t('ims.settings.title')}
          </button>
        </div>
      </header>

      {/* Stats Cards */}
      <section className="ims-stats">
        <div className="ims-stat-card">
          <div className="ims-stat-card__icon ims-stat-card__icon--primary">
            <FileText size={24} />
          </div>
          <div className="ims-stat-card__content">
            <span className="ims-stat-card__value">{stats?.totalDocuments ?? 0}</span>
            <span className="ims-stat-card__label">{t('ims.stats.totalCrawled')}</span>
          </div>
        </div>
        <div className="ims-stat-card">
          <div className="ims-stat-card__icon ims-stat-card__icon--success">
            <CheckCircle size={24} />
          </div>
          <div className="ims-stat-card__content">
            <span className="ims-stat-card__value">{stats?.newDocuments ?? 0}</span>
            <span className="ims-stat-card__label">{t('ims.stats.newDocuments')}</span>
          </div>
        </div>
        <div className="ims-stat-card">
          <div className="ims-stat-card__icon ims-stat-card__icon--warning">
            <RefreshCw size={24} />
          </div>
          <div className="ims-stat-card__content">
            <span className="ims-stat-card__value">{stats?.updatedDocuments ?? 0}</span>
            <span className="ims-stat-card__label">{t('ims.stats.updatedDocuments')}</span>
          </div>
        </div>
        <div className="ims-stat-card">
          <div className="ims-stat-card__icon ims-stat-card__icon--error">
            <AlertCircle size={24} />
          </div>
          <div className="ims-stat-card__content">
            <span className="ims-stat-card__value">{stats?.failedDocuments ?? 0}</span>
            <span className="ims-stat-card__label">{t('ims.stats.failedDocuments')}</span>
          </div>
        </div>
      </section>

      {/* Main Content Grid */}
      <div className="ims-content">
        {/* Left Column: Crawler Dashboard + Jobs */}
        <div className="ims-main">
          {/* Crawler Status Dashboard */}
          <section className="ims-card ims-dashboard">
            <div className="ims-card__header">
              <h2 className="ims-card__title">
                <Activity size={20} />
                {t('ims.crawler.title')}
              </h2>
              <div className={`ims-status-badge ims-status-badge--${statusColors[crawlerState.status]}`}>
                <StatusIcon status={crawlerState.status} size={14} />
                {t(`ims.crawler.status.${crawlerState.status}`)}
              </div>
            </div>

            {/* Progress Bar */}
            <div className="ims-progress">
              <div className="ims-progress__bar">
                <div
                  className="ims-progress__fill"
                  style={{ width: `${crawlerState.progress}%` }}
                />
              </div>
              <span className="ims-progress__text">{Math.round(crawlerState.progress)}%</span>
            </div>

            {/* Current URL */}
            {crawlerState.currentUrl && (
              <div className="ims-dashboard__info">
                <Globe size={16} />
                <span className="ims-dashboard__info-label">{t('ims.crawler.currentUrl')}:</span>
                <span className="ims-dashboard__info-value">{crawlerState.currentUrl}</span>
              </div>
            )}

            {/* Time Info */}
            {crawlerState.startTime && (
              <div className="ims-dashboard__info">
                <Clock size={16} />
                <span className="ims-dashboard__info-label">{t('ims.crawler.elapsedTime')}:</span>
                <span className="ims-dashboard__info-value">
                  {formatDuration(
                    Math.floor(
                      (Date.now() - new Date(crawlerState.startTime).getTime()) / 1000
                    )
                  )}
                </span>
                {crawlerState.estimatedRemaining && (
                  <>
                    <span className="ims-dashboard__info-separator">|</span>
                    <span className="ims-dashboard__info-label">
                      {t('ims.crawler.estimatedRemaining')}:
                    </span>
                    <span className="ims-dashboard__info-value">
                      {formatDuration(crawlerState.estimatedRemaining)}
                    </span>
                  </>
                )}
              </div>
            )}

            {/* Control Buttons */}
            <div className="ims-dashboard__controls">
              {crawlerState.status === 'idle' || crawlerState.status === 'completed' || crawlerState.status === 'failed' ? (
                <button
                  className="btn btn-primary btn-icon"
                  onClick={handleStart}
                  disabled={isActionLoading}
                >
                  <Play size={18} />
                  {t('ims.crawler.start')}
                </button>
              ) : crawlerState.status === 'running' ? (
                <>
                  <button
                    className="btn btn-warning btn-icon"
                    onClick={handlePause}
                    disabled={isActionLoading}
                  >
                    <Pause size={18} />
                    {t('ims.crawler.pause')}
                  </button>
                  <button
                    className="btn btn-error btn-icon"
                    onClick={handleStop}
                    disabled={isActionLoading}
                  >
                    <Square size={18} />
                    {t('ims.crawler.stop')}
                  </button>
                </>
              ) : crawlerState.status === 'paused' ? (
                <>
                  <button
                    className="btn btn-primary btn-icon"
                    onClick={handleResume}
                    disabled={isActionLoading}
                  >
                    <RotateCcw size={18} />
                    {t('ims.crawler.resume')}
                  </button>
                  <button
                    className="btn btn-error btn-icon"
                    onClick={handleStop}
                    disabled={isActionLoading}
                  >
                    <Square size={18} />
                    {t('ims.crawler.stop')}
                  </button>
                </>
              ) : null}
            </div>
          </section>

          {/* Jobs Table */}
          <section className="ims-card ims-jobs">
            <div className="ims-card__header">
              <h2 className="ims-card__title">
                <FileText size={20} />
                {t('ims.jobs.title')}
              </h2>
              <button
                className="btn btn-primary btn-sm btn-icon"
                onClick={() => setShowNewJobModal(true)}
              >
                <Plus size={16} />
                {t('ims.jobs.newJob')}
              </button>
            </div>

            {jobs.length === 0 ? (
              <div className="ims-jobs__empty">
                <FileText size={48} className="ims-jobs__empty-icon" />
                <h3>{t('ims.jobs.noJobs')}</h3>
                <p>{t('ims.jobs.createFirst')}</p>
                <button
                  className="btn btn-primary btn-icon"
                  onClick={() => setShowNewJobModal(true)}
                >
                  <Plus size={18} />
                  {t('ims.jobs.newJob')}
                </button>
              </div>
            ) : (
              <div className="ims-jobs__table-container">
                <table className="ims-jobs__table">
                  <thead>
                    <tr>
                      <th>{t('ims.jobs.id')}</th>
                      <th>{t('ims.jobs.url')}</th>
                      <th>{t('ims.jobs.status')}</th>
                      <th>{t('ims.jobs.documentCount')}</th>
                      <th>{t('ims.jobs.createdAt')}</th>
                      <th>{t('ims.jobs.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((job) => (
                      <tr key={job.id}>
                        <td className="ims-jobs__id">{job.id}</td>
                        <td className="ims-jobs__url">
                          <span className="ims-jobs__name">{job.name}</span>
                          <span className="ims-jobs__url-text">{job.url}</span>
                        </td>
                        <td>
                          <div className={`ims-status-badge ims-status-badge--${statusColors[job.status]}`}>
                            <StatusIcon status={job.status} size={12} />
                            {t(`ims.crawler.status.${job.status}`)}
                          </div>
                        </td>
                        <td>{job.documentCount}</td>
                        <td>{formatDate(job.createdAt)}</td>
                        <td className="ims-jobs__actions">
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => setShowJobDetailModal(job)}
                            title={t('ims.jobs.viewDetails')}
                          >
                            <Eye size={16} />
                          </button>
                          <button
                            className="btn btn-ghost btn-sm btn-error-ghost"
                            onClick={() => handleDeleteJob(job.id)}
                            title={t('ims.jobs.delete')}
                          >
                            <Trash2 size={16} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        {/* Right Column: Logs + Settings */}
        <aside className="ims-sidebar">
          {/* Settings Panel */}
          {showSettingsPanel && (
            <section className="ims-card ims-settings">
              <div className="ims-card__header">
                <h2 className="ims-card__title">
                  <Settings size={20} />
                  {t('ims.settings.title')}
                </h2>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setShowSettingsPanel(false)}
                >
                  <ChevronUp size={18} />
                </button>
              </div>

              <div className="ims-settings__form">
                <div className="ims-settings__field">
                  <label>
                    {t('ims.settings.depth')}
                    <span className="ims-settings__help">{t('ims.settings.depthHelp')}</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={settings.depth}
                    onChange={(e) =>
                      setSettings({ ...settings, depth: parseInt(e.target.value) || 1 })
                    }
                  />
                </div>

                <div className="ims-settings__field">
                  <label>
                    {t('ims.settings.interval')} (s)
                    <span className="ims-settings__help">{t('ims.settings.intervalHelp')}</span>
                  </label>
                  <input
                    type="number"
                    min="0.5"
                    max="60"
                    step="0.5"
                    value={settings.interval}
                    onChange={(e) =>
                      setSettings({ ...settings, interval: parseFloat(e.target.value) || 1 })
                    }
                  />
                </div>

                <div className="ims-settings__field">
                  <label>
                    {t('ims.settings.timeout')} (s)
                    <span className="ims-settings__help">{t('ims.settings.timeoutHelp')}</span>
                  </label>
                  <input
                    type="number"
                    min="5"
                    max="300"
                    value={settings.timeout}
                    onChange={(e) =>
                      setSettings({ ...settings, timeout: parseInt(e.target.value) || 30 })
                    }
                  />
                </div>

                <div className="ims-settings__field">
                  <label>
                    {t('ims.settings.documentTypes')}
                    <span className="ims-settings__help">{t('ims.settings.documentTypesHelp')}</span>
                  </label>
                  <div className="ims-settings__checkboxes">
                    {DOCUMENT_TYPES.map((type) => (
                      <label key={type} className="ims-settings__checkbox">
                        <input
                          type="checkbox"
                          checked={settings.documentTypes.includes(type)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSettings({
                                ...settings,
                                documentTypes: [...settings.documentTypes, type],
                              });
                            } else {
                              setSettings({
                                ...settings,
                                documentTypes: settings.documentTypes.filter((t) => t !== type),
                              });
                            }
                          }}
                        />
                        {type}
                      </label>
                    ))}
                  </div>
                </div>

                <div className="ims-settings__actions">
                  <button className="btn btn-secondary" onClick={handleResetSettings}>
                    {t('ims.settings.reset')}
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={handleSaveSettings}
                    disabled={isActionLoading}
                  >
                    {t('ims.settings.save')}
                  </button>
                </div>
              </div>
            </section>
          )}

          {/* Real-time Logs */}
          <section className="ims-card ims-logs">
            <div className="ims-card__header">
              <h2 className="ims-card__title">
                <Activity size={20} />
                {t('ims.logs.title')}
              </h2>
              <div className="ims-logs__header-actions">
                <select
                  className="ims-logs__filter"
                  value={logFilter}
                  onChange={(e) => setLogFilter(e.target.value as LogLevel | 'all')}
                >
                  <option value="all">All</option>
                  <option value="info">{t('ims.logs.levels.info')}</option>
                  <option value="warning">{t('ims.logs.levels.warning')}</option>
                  <option value="error">{t('ims.logs.levels.error')}</option>
                  <option value="debug">{t('ims.logs.levels.debug')}</option>
                </select>
                <button className="btn btn-ghost btn-sm" onClick={handleClearLogs}>
                  <Trash2 size={16} />
                </button>
              </div>
            </div>

            <div className="ims-logs__container" ref={logContainerRef}>
              {logs.length === 0 ? (
                <div className="ims-logs__empty">
                  <Activity size={32} />
                  <p>{t('ims.logs.noLogs')}</p>
                </div>
              ) : (
                logs.map((log) => (
                  <div key={log.id} className={`ims-log-entry ims-log-entry--${log.level}`}>
                    <span className="ims-log-entry__time">{formatTime(log.timestamp)}</span>
                    <LogLevelIcon level={log.level} />
                    <span className="ims-log-entry__source">[{log.source}]</span>
                    <span className="ims-log-entry__message">{log.message}</span>
                  </div>
                ))
              )}
            </div>
          </section>
        </aside>
      </div>

      {/* New Job Modal */}
      {showNewJobModal && (
        <div className="ims-modal-overlay" onClick={() => setShowNewJobModal(false)}>
          <div className="ims-modal" onClick={(e) => e.stopPropagation()}>
            <div className="ims-modal__header">
              <h2>{t('ims.newJobForm.title')}</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowNewJobModal(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreateJob} className="ims-modal__form">
              <div className="ims-form-field">
                <label htmlFor="job-name">{t('ims.newJobForm.jobName')}</label>
                <input
                  id="job-name"
                  type="text"
                  placeholder={t('ims.newJobForm.jobNamePlaceholder')}
                  value={newJobForm.name}
                  onChange={(e) => setNewJobForm({ ...newJobForm, name: e.target.value })}
                  className={formErrors.name ? 'error' : ''}
                />
                {formErrors.name && <span className="ims-form-error">{formErrors.name}</span>}
              </div>
              <div className="ims-form-field">
                <label htmlFor="job-url">{t('ims.newJobForm.targetUrl')}</label>
                <input
                  id="job-url"
                  type="url"
                  placeholder={t('ims.newJobForm.targetUrlPlaceholder')}
                  value={newJobForm.url}
                  onChange={(e) => setNewJobForm({ ...newJobForm, url: e.target.value })}
                  className={formErrors.url ? 'error' : ''}
                />
                {formErrors.url && <span className="ims-form-error">{formErrors.url}</span>}
              </div>
              <div className="ims-form-field">
                <label htmlFor="job-description">{t('ims.newJobForm.description')}</label>
                <textarea
                  id="job-description"
                  placeholder={t('ims.newJobForm.descriptionPlaceholder')}
                  value={newJobForm.description}
                  onChange={(e) => setNewJobForm({ ...newJobForm, description: e.target.value })}
                  rows={3}
                />
              </div>
              <div className="ims-modal__actions">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowNewJobModal(false)}
                >
                  {t('ims.newJobForm.cancel')}
                </button>
                <button type="submit" className="btn btn-primary" disabled={isActionLoading}>
                  {t('ims.newJobForm.create')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Job Detail Modal */}
      {showJobDetailModal && (
        <div className="ims-modal-overlay" onClick={() => setShowJobDetailModal(null)}>
          <div className="ims-modal ims-modal--large" onClick={(e) => e.stopPropagation()}>
            <div className="ims-modal__header">
              <h2>{t('ims.jobDetail.title')}: {showJobDetailModal.name}</h2>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowJobDetailModal(null)}>
                <X size={20} />
              </button>
            </div>
            <div className="ims-modal__content">
              <div className="ims-job-detail">
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.jobs.id')}:</span>
                  <span className="ims-job-detail__value">{showJobDetailModal.id}</span>
                </div>
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.jobs.url')}:</span>
                  <span className="ims-job-detail__value">{showJobDetailModal.url}</span>
                </div>
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.jobs.status')}:</span>
                  <div className={`ims-status-badge ims-status-badge--${statusColors[showJobDetailModal.status]}`}>
                    <StatusIcon status={showJobDetailModal.status} size={14} />
                    {t(`ims.crawler.status.${showJobDetailModal.status}`)}
                  </div>
                </div>
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.crawler.progress')}:</span>
                  <div className="ims-progress ims-progress--inline">
                    <div className="ims-progress__bar">
                      <div
                        className="ims-progress__fill"
                        style={{ width: `${showJobDetailModal.progress}%` }}
                      />
                    </div>
                    <span className="ims-progress__text">{showJobDetailModal.progress}%</span>
                  </div>
                </div>
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.jobs.documentCount')}:</span>
                  <span className="ims-job-detail__value">{showJobDetailModal.documentCount}</span>
                </div>
                <div className="ims-job-detail__row">
                  <span className="ims-job-detail__label">{t('ims.jobs.createdAt')}:</span>
                  <span className="ims-job-detail__value">{formatDate(showJobDetailModal.createdAt)}</span>
                </div>
                {showJobDetailModal.description && (
                  <div className="ims-job-detail__row">
                    <span className="ims-job-detail__label">{t('ims.newJobForm.description')}:</span>
                    <span className="ims-job-detail__value">{showJobDetailModal.description}</span>
                  </div>
                )}
              </div>
            </div>
            <div className="ims-modal__actions">
              <button className="btn btn-secondary" onClick={() => setShowJobDetailModal(null)}>
                {t('ims.jobDetail.close')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default IMSCrawlerPage;
