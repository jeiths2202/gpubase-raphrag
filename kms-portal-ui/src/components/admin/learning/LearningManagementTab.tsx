/**
 * Learning Management Tab
 * Premium UI for Smarter RAG Learning System
 *
 * Features:
 * - Verified Knowledge Store management
 * - Training batch monitoring
 * - Learning LLM status
 * - Daily statistics visualization
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Brain,
  Play,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  Database,
  Loader2,
  AlertTriangle,
  ThumbsUp,
  Trash2,
  Zap,
  Calendar,
  Cpu,
  Layers,
  Activity,
  Settings,
  ChevronRight,
  Sparkles,
  BarChart3,
  Info,
  Monitor,
  Thermometer,
  HardDrive,
  Terminal,
  Server,
} from 'lucide-react';
import client from '../../../api/client';
import './LearningManagementTab.css';

// Types
interface VerifiedKnowledgeStats {
  total_count: number;
  active_count: number;
  deprecated_count: number;
  trained_count: number;
  pending_training_count: number;
  unlearn_pending_count: number;
  avg_feedback_score: number;
  avg_usage_count: number;
  total_usage_count: number;
  category_count: number;
}

interface PendingKnowledge {
  id: string;
  question: string;
  answer: string;
  feedback_score: number;
  thumbs_up_count: number;
  thumbs_down_count: number;
  category: string | null;
  created_at: string;
}

interface TrainingBatch {
  id: string;
  batch_id: string;
  total_samples: number;
  trained_samples: number;
  status: string;
  adapter_name: string | null;
  eval_loss: number | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

interface DailyStats {
  date: string;
  new_entries: number;
  trained_entries: number;
  avg_score: number;
}

interface TrainingSchedule {
  cron_expression: string;
  is_enabled: boolean;
  last_run_at: string | null;
  last_batch_id: string | null;
  last_status: string | null;
  next_run_at: string | null;
  min_samples_required: number;
  auto_deploy: boolean;
}

interface LearningLLMStatus {
  enabled: boolean;
  is_initialized: boolean;
  is_loaded: boolean;
  base_model: string;
  current_adapter: string | null;
  available_adapters: string[];
  thresholds: {
    min_confidence: number;
    high_confidence: number;
  };
}

interface GPUInfo {
  index: number;
  name: string;
  memory_used: number;
  memory_total: number;
  memory_percent: number;
  utilization: number;
  temperature: number;
  power_draw: number;
  power_limit: number;
}

interface GPUStatus {
  available: boolean;
  gpu_count: number;
  gpus: GPUInfo[];
  error?: string;
}

interface TrainingProgress {
  is_training: boolean;
  process: {
    pid: number;
    cpu_percent: number;
    memory_percent: number;
  } | null;
  current_batch_id: string | null;
  log_file: string | null;
  log_lines: string[];
  progress: {
    stage: string;
    percent: number;
    current_step?: number;
    total_steps?: number;
    has_error?: boolean;
  } | null;
  error?: string;
}

// Status Indicator Component
const StatusDot: React.FC<{ status: 'active' | 'inactive' | 'warning' | 'error'; size?: number }> = ({
  status,
  size = 8
}) => {
  const colors = {
    active: '#22c55e',
    inactive: '#64748b',
    warning: '#f59e0b',
    error: '#ef4444',
  };

  return (
    <span
      className="status-dot"
      style={{
        width: size,
        height: size,
        backgroundColor: colors[status],
        boxShadow: status === 'active' ? `0 0 8px ${colors[status]}50` : 'none',
      }}
    />
  );
};

// Badge Component
const Badge: React.FC<{
  variant: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  children: React.ReactNode;
  icon?: React.ReactNode;
}> = ({ variant, children, icon }) => (
  <span className={`premium-badge premium-badge--${variant}`}>
    {icon}
    {children}
  </span>
);

// Tooltip wrapper
const Tooltip: React.FC<{ content: string; children: React.ReactNode }> = ({ content, children }) => (
  <span className="tooltip-wrapper" data-tooltip={content}>
    {children}
  </span>
);

export const LearningManagementTab: React.FC = () => {
  // State
  const [stats, setStats] = useState<VerifiedKnowledgeStats | null>(null);
  const [batches, setBatches] = useState<TrainingBatch[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [schedule, setSchedule] = useState<TrainingSchedule | null>(null);
  const [llmStatus, setLlmStatus] = useState<LearningLLMStatus | null>(null);
  const [pendingItems, setPendingItems] = useState<PendingKnowledge[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [gpuStatus, setGpuStatus] = useState<GPUStatus | null>(null);
  const [trainingProgress, setTrainingProgress] = useState<TrainingProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [reloadLoading, setReloadLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsRes, batchesRes, dailyRes, scheduleRes, llmStatusRes, pendingRes] = await Promise.all([
        client.get('/verified-knowledge/stats/overview'),
        client.get('/verified-knowledge/training/batches?limit=10'),
        client.get('/verified-knowledge/stats/daily?days=14'),
        client.get('/verified-knowledge/training/schedule').catch(() => ({ data: null })),
        client.get('/verified-knowledge/learning-llm/status').catch(() => ({ data: null })),
        client.get('/verified-knowledge?is_trained=false&status=active&limit=50').catch(() => ({ data: [] })),
      ]);

      setStats(statsRes.data);
      setBatches(batchesRes.data);
      setDailyStats(dailyRes.data);
      setSchedule(scheduleRes.data);
      setLlmStatus(llmStatusRes.data);
      setPendingItems(pendingRes.data || []);
      setSelectedIds(new Set());
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch GPU and training progress
  const fetchMonitoringData = useCallback(async () => {
    try {
      const [gpuRes, progressRes] = await Promise.all([
        client.get('/verified-knowledge/monitor/gpu').catch(() => ({ data: null })),
        client.get('/verified-knowledge/monitor/training-progress').catch(() => ({ data: null })),
      ]);
      setGpuStatus(gpuRes.data);
      setTrainingProgress(progressRes.data);
    } catch (err) {
      console.error('Failed to fetch monitoring data:', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    fetchMonitoringData();
  }, [fetchData, fetchMonitoringData]);

  // Auto-refresh when training is active
  useEffect(() => {
    let interval: ReturnType<typeof setInterval> | null = null;

    if (autoRefresh || trainingProgress?.is_training) {
      interval = setInterval(() => {
        fetchMonitoringData();
      }, 3000); // Refresh every 3 seconds
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, trainingProgress?.is_training, fetchMonitoringData]);

  // Trigger training
  const handleTriggerTraining = async () => {
    try {
      setTriggerLoading(true);
      setError(null);
      setSuccessMessage(null);

      const response = await client.post('/verified-knowledge/training/trigger', {
        min_feedback_score: 0.8,
        min_thumbs_up: 1,
        limit: 1000,
        run_async: true,
      });

      if (response.data.success) {
        setSuccessMessage(`학습이 시작되었습니다. Batch ID: ${response.data.batch_id}`);
        setTimeout(fetchData, 2000);
      } else {
        setError(response.data.message);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to trigger training');
    } finally {
      setTriggerLoading(false);
    }
  };

  // Toggle schedule
  const handleToggleSchedule = async () => {
    if (!schedule) return;

    try {
      await client.patch('/verified-knowledge/training/schedule', {
        is_enabled: !schedule.is_enabled,
      });
      setSchedule({ ...schedule, is_enabled: !schedule.is_enabled });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update schedule');
    }
  };

  // Toggle item selection
  const handleToggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  // Toggle select all
  const handleToggleSelectAll = () => {
    if (selectedIds.size === pendingItems.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(pendingItems.map(item => item.id)));
    }
  };

  // Delete single item
  const handleDeleteItem = async (id: string) => {
    if (!confirm('이 항목을 삭제하시겠습니까?')) return;

    try {
      setDeleteLoading(id);
      await client.delete(`/verified-knowledge/${id}?reason=Admin deleted from dashboard`);
      setPendingItems(prev => prev.filter(item => item.id !== id));
      setSelectedIds(prev => {
        const newSet = new Set(prev);
        newSet.delete(id);
        return newSet;
      });
      setSuccessMessage('항목이 삭제되었습니다.');
      // Refresh stats
      const statsRes = await client.get('/verified-knowledge/stats/overview');
      setStats(statsRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete item');
    } finally {
      setDeleteLoading(null);
    }
  };

  // Delete selected items
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`선택된 ${selectedIds.size}개 항목을 삭제하시겠습니까?`)) return;

    try {
      setDeleteLoading('batch');
      const deletePromises = Array.from(selectedIds).map(id =>
        client.delete(`/verified-knowledge/${id}?reason=Admin bulk deleted from dashboard`)
      );
      await Promise.all(deletePromises);
      setPendingItems(prev => prev.filter(item => !selectedIds.has(item.id)));
      setSelectedIds(new Set());
      setSuccessMessage(`${deletePromises.length}개 항목이 삭제되었습니다.`);
      // Refresh stats
      const statsRes = await client.get('/verified-knowledge/stats/overview');
      setStats(statsRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete items');
    } finally {
      setDeleteLoading(null);
    }
  };

  // Reload Learning LLM adapter
  const handleReloadLLM = async (adapterName?: string) => {
    try {
      setReloadLoading(true);
      setError(null);
      setSuccessMessage(null);

      const response = await client.post('/verified-knowledge/learning-llm/reload', {
        adapter_name: adapterName || null,
      });

      if (response.data.success) {
        setSuccessMessage(`Learning LLM 어댑터 리로드 완료: ${response.data.adapter_name}`);
        const statusRes = await client.get('/verified-knowledge/learning-llm/status');
        setLlmStatus(statusRes.data);
      } else {
        setError('Learning LLM 리로드 실패');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reload Learning LLM');
    } finally {
      setReloadLoading(false);
    }
  };

  // Format helpers
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Get status config
  const getStatusConfig = (status: string) => {
    const configs: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
      completed: { color: 'success', icon: <CheckCircle size={14} />, label: 'Completed' },
      training: { color: 'info', icon: <Loader2 size={14} className="spin" />, label: 'Training' },
      pending: { color: 'warning', icon: <Clock size={14} />, label: 'Pending' },
      failed: { color: 'error', icon: <XCircle size={14} />, label: 'Failed' },
      collecting: { color: 'info', icon: <Database size={14} />, label: 'Collecting' },
    };
    return configs[status] || { color: 'neutral', icon: <Clock size={14} />, label: status };
  };

  // Calculate max value for chart scaling
  const maxChartValue = Math.max(
    ...dailyStats.map(d => Math.max(d.new_entries, d.trained_entries)),
    1
  );

  if (loading) {
    return (
      <div className="learning-tab learning-tab--loading">
        <div className="loading-content">
          <div className="loading-spinner">
            <Brain className="spin" size={32} />
          </div>
          <span>Loading Learning System...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="learning-tab premium">
      {/* Header */}
      <header className="learning-header">
        <div className="learning-header__title">
          <div className="learning-header__icon">
            <Brain size={28} />
          </div>
          <div>
            <h2>Smarter RAG - Learning Management</h2>
            <p className="learning-header__subtitle">
              AI 시스템이 지속적으로 학습하고 개선됩니다
            </p>
          </div>
        </div>
        <div className="learning-header__actions">
          <button className="btn btn-ghost" onClick={fetchData} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
            <span>새로고침</span>
          </button>
          <button
            className="btn btn-primary"
            onClick={handleTriggerTraining}
            disabled={triggerLoading || (stats?.pending_training_count === 0 && stats?.unlearn_pending_count === 0)}
          >
            {triggerLoading ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
            <span>수동 학습 시작</span>
          </button>
        </div>
      </header>

      {/* Messages */}
      {error && (
        <div className="alert alert--error">
          <AlertTriangle size={18} />
          <span>{error}</span>
          <button className="alert__close" onClick={() => setError(null)}>×</button>
        </div>
      )}
      {successMessage && (
        <div className="alert alert--success">
          <CheckCircle size={18} />
          <span>{successMessage}</span>
          <button className="alert__close" onClick={() => setSuccessMessage(null)}>×</button>
        </div>
      )}

      {/* Stats Overview Cards */}
      <section className="stats-overview">
        <div className="stat-card stat-card--primary">
          <div className="stat-card__icon">
            <Database size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">{stats?.active_count || 0}</span>
            <span className="stat-card__label">Active Knowledge</span>
          </div>
          <div className="stat-card__decoration" />
        </div>

        <div className="stat-card stat-card--success">
          <div className="stat-card__icon">
            <ThumbsUp size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">{stats?.trained_count || 0}</span>
            <span className="stat-card__label">Trained</span>
          </div>
          <div className="stat-card__decoration" />
        </div>

        <div className="stat-card stat-card--warning">
          <div className="stat-card__icon">
            <Clock size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">{stats?.pending_training_count || 0}</span>
            <span className="stat-card__label">Pending Training</span>
          </div>
          <div className="stat-card__decoration" />
        </div>

        <div className="stat-card stat-card--danger">
          <div className="stat-card__icon">
            <Trash2 size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">{stats?.unlearn_pending_count || 0}</span>
            <span className="stat-card__label">Pending Unlearn</span>
          </div>
          <div className="stat-card__decoration" />
        </div>

        <div className="stat-card">
          <div className="stat-card__icon">
            <TrendingUp size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">
              {((stats?.avg_feedback_score || 0) * 100).toFixed(0)}%
            </span>
            <span className="stat-card__label">Avg Score</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-card__icon">
            <Activity size={22} />
          </div>
          <div className="stat-card__content">
            <span className="stat-card__value">{stats?.total_usage_count || 0}</span>
            <span className="stat-card__label">Total Usage</span>
          </div>
        </div>
      </section>

      {/* Main Grid: Schedule & LLM Status */}
      <section className="main-grid">
        {/* Learning Schedule Card */}
        <div className="premium-card">
          <div className="premium-card__header">
            <div className="premium-card__title">
              <Calendar size={18} />
              <span>학습 스케줄</span>
            </div>
            {schedule && (
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={schedule.is_enabled}
                  onChange={handleToggleSchedule}
                />
                <span className="toggle-switch__slider" />
              </label>
            )}
          </div>

          {schedule ? (
            <div className="premium-card__body">
              <div className="schedule-status">
                <StatusDot status={schedule.is_enabled ? 'active' : 'inactive'} size={10} />
                <span className={schedule.is_enabled ? 'text-success' : 'text-muted'}>
                  {schedule.is_enabled ? '자동 학습 활성화' : '자동 학습 비활성화'}
                </span>
              </div>

              <div className="info-grid">
                <div className="info-item">
                  <span className="info-item__label">
                    <Clock size={14} />
                    스케줄
                  </span>
                  <Tooltip content="Cron 표현식으로 설정된 자동 학습 시간">
                    <span className="info-item__value mono">
                      {schedule.cron_expression}
                      <span className="text-muted"> (매일 00:00)</span>
                    </span>
                  </Tooltip>
                </div>

                <div className="info-item">
                  <span className="info-item__label">
                    <ChevronRight size={14} />
                    다음 실행
                  </span>
                  <span className="info-item__value">
                    {schedule.next_run_at ? formatDate(schedule.next_run_at) : '스케줄 비활성화'}
                  </span>
                </div>

                <div className="info-item">
                  <span className="info-item__label">
                    <CheckCircle size={14} />
                    마지막 실행
                  </span>
                  <span className="info-item__value">
                    {schedule.last_run_at ? (
                      <>
                        {formatDate(schedule.last_run_at)}
                        {schedule.last_status && (
                          <Badge
                            variant={schedule.last_status === 'completed' ? 'success' : 'warning'}
                          >
                            {schedule.last_status}
                          </Badge>
                        )}
                      </>
                    ) : (
                      <span className="text-muted">실행 기록 없음</span>
                    )}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="premium-card__body">
              <div className="empty-state empty-state--small">
                <Settings size={24} />
                <span>스케줄 설정이 없습니다</span>
              </div>
            </div>
          )}
        </div>

        {/* Learning LLM Status Card */}
        <div className="premium-card">
          <div className="premium-card__header">
            <div className="premium-card__title">
              <Cpu size={18} />
              <span>Learning LLM 상태</span>
            </div>
            <button
              className="btn btn-sm btn-ghost"
              onClick={() => handleReloadLLM()}
              disabled={reloadLoading || !llmStatus?.enabled || (llmStatus?.available_adapters?.length === 0)}
            >
              {reloadLoading ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
              <span>리로드</span>
            </button>
          </div>

          <div className="premium-card__body">
            {llmStatus ? (
              <>
                <div className="llm-status-row">
                  <div className="llm-status-item">
                    <span className="llm-status-item__label">서비스</span>
                    <div className="llm-status-item__value">
                      <StatusDot status={llmStatus.enabled ? 'active' : 'inactive'} />
                      <span>{llmStatus.enabled ? '활성화' : '비활성화'}</span>
                    </div>
                  </div>

                  <div className="llm-status-item">
                    <span className="llm-status-item__label">모델</span>
                    <div className="llm-status-item__value">
                      <StatusDot status={llmStatus.is_loaded ? 'active' : 'inactive'} />
                      <span>{llmStatus.is_loaded ? '로드됨' : '미로드'}</span>
                    </div>
                  </div>
                </div>

                <div className="info-grid">
                  <div className="info-item info-item--full">
                    <span className="info-item__label">
                      <Layers size={14} />
                      베이스 모델
                    </span>
                    <span className="info-item__value mono">
                      {llmStatus.base_model || '-'}
                    </span>
                  </div>

                  <div className="info-item">
                    <span className="info-item__label">
                      <Zap size={14} />
                      현재 어댑터
                    </span>
                    <span className="info-item__value">
                      {llmStatus.current_adapter ? (
                        <Badge variant="success" icon={<CheckCircle size={12} />}>
                          {llmStatus.current_adapter}
                        </Badge>
                      ) : (
                        <span className="text-muted">없음</span>
                      )}
                    </span>
                  </div>

                  <div className="info-item">
                    <span className="info-item__label">
                      <Database size={14} />
                      사용 가능한 어댑터
                    </span>
                    <span className="info-item__value">
                      <Badge variant="info">
                        {llmStatus.available_adapters?.length || 0}개
                      </Badge>
                    </span>
                  </div>
                </div>

                {llmStatus.available_adapters && llmStatus.available_adapters.length > 0 && (
                  <div className="adapter-list">
                    <span className="adapter-list__label">최근 어댑터:</span>
                    <div className="adapter-list__items">
                      {llmStatus.available_adapters.slice(0, 3).map((adapter, i) => (
                        <span key={i} className="adapter-tag">{adapter}</span>
                      ))}
                      {llmStatus.available_adapters.length > 3 && (
                        <span className="adapter-tag adapter-tag--more">
                          +{llmStatus.available_adapters.length - 3}
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="empty-state empty-state--small">
                <Cpu size={24} />
                <span>LLM 상태를 불러올 수 없습니다</span>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* GPU Monitoring & Training Progress Section */}
      {(gpuStatus?.available || trainingProgress?.is_training) && (
        <section className="monitoring-section">
          <div className="monitoring-header">
            <h3 className="section-title">
              <Monitor size={18} />
              실시간 모니터링
            </h3>
            <div className="monitoring-controls">
              <label className="auto-refresh-toggle">
                <input
                  type="checkbox"
                  checked={autoRefresh || trainingProgress?.is_training || false}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span>자동 새로고침</span>
                {(autoRefresh || trainingProgress?.is_training) && (
                  <Loader2 size={12} className="spin" />
                )}
              </label>
              <button className="btn btn-sm btn-ghost" onClick={fetchMonitoringData}>
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          <div className="monitoring-grid">
            {/* GPU Cards */}
            {gpuStatus?.available && gpuStatus.gpus.map((gpu) => (
              <div key={gpu.index} className="gpu-card">
                <div className="gpu-card__header">
                  <Server size={16} />
                  <span>GPU {gpu.index}</span>
                  <span className="gpu-name">{gpu.name.replace('NVIDIA ', '')}</span>
                </div>
                <div className="gpu-card__body">
                  <div className="gpu-metric">
                    <div className="gpu-metric__header">
                      <HardDrive size={14} />
                      <span>메모리</span>
                      <span className="gpu-metric__value">
                        {(gpu.memory_used / 1024).toFixed(1)}GB / {(gpu.memory_total / 1024).toFixed(0)}GB
                      </span>
                    </div>
                    <div className="gpu-progress-bar">
                      <div
                        className={`gpu-progress-bar__fill ${gpu.memory_percent > 90 ? 'critical' : gpu.memory_percent > 70 ? 'warning' : ''}`}
                        style={{ width: `${gpu.memory_percent}%` }}
                      />
                    </div>
                    <span className="gpu-metric__percent">{gpu.memory_percent}%</span>
                  </div>

                  <div className="gpu-metric">
                    <div className="gpu-metric__header">
                      <Activity size={14} />
                      <span>사용률</span>
                      <span className="gpu-metric__value">{gpu.utilization}%</span>
                    </div>
                    <div className="gpu-progress-bar">
                      <div
                        className={`gpu-progress-bar__fill utilization ${gpu.utilization > 90 ? 'critical' : ''}`}
                        style={{ width: `${gpu.utilization}%` }}
                      />
                    </div>
                  </div>

                  <div className="gpu-stats-row">
                    <div className="gpu-stat">
                      <Thermometer size={12} />
                      <span>{gpu.temperature}°C</span>
                    </div>
                    <div className="gpu-stat">
                      <Zap size={12} />
                      <span>{gpu.power_draw.toFixed(0)}W / {gpu.power_limit.toFixed(0)}W</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Training Progress Card */}
            {trainingProgress && (
              <div className={`training-progress-card ${trainingProgress.is_training ? 'active' : ''}`}>
                <div className="training-progress-card__header">
                  <Brain size={16} className={trainingProgress.is_training ? 'spin' : ''} />
                  <span>학습 진행 상황</span>
                  {trainingProgress.is_training && (
                    <Badge variant="success" icon={<Activity size={10} />}>진행 중</Badge>
                  )}
                </div>
                <div className="training-progress-card__body">
                  {trainingProgress.is_training ? (
                    <>
                      <div className="training-info">
                        <div className="training-info__item">
                          <span className="label">Batch ID</span>
                          <code>{trainingProgress.current_batch_id || '-'}</code>
                        </div>
                        {trainingProgress.process && (
                          <>
                            <div className="training-info__item">
                              <span className="label">CPU</span>
                              <span>{trainingProgress.process.cpu_percent}%</span>
                            </div>
                            <div className="training-info__item">
                              <span className="label">MEM</span>
                              <span>{trainingProgress.process.memory_percent}%</span>
                            </div>
                          </>
                        )}
                      </div>

                      {trainingProgress.progress && (
                        <div className="training-stage">
                          <div className="training-stage__header">
                            <span className="stage-name">
                              {trainingProgress.progress.stage === 'downloading' && '모델 다운로드'}
                              {trainingProgress.progress.stage === 'loading_model' && '모델 로딩'}
                              {trainingProgress.progress.stage === 'initializing' && '초기화'}
                              {trainingProgress.progress.stage === 'training' && 'QLoRA 학습'}
                              {trainingProgress.progress.stage === 'completed' && '완료'}
                            </span>
                            <span className="stage-percent">{trainingProgress.progress.percent}%</span>
                          </div>
                          <div className="training-progress-bar">
                            <div
                              className="training-progress-bar__fill"
                              style={{ width: `${trainingProgress.progress.percent}%` }}
                            />
                          </div>
                          {trainingProgress.progress.current_step && (
                            <span className="stage-steps">
                              Step {trainingProgress.progress.current_step} / {trainingProgress.progress.total_steps}
                            </span>
                          )}
                        </div>
                      )}

                      {/* Log Output */}
                      <div className="training-log">
                        <div className="training-log__header">
                          <Terminal size={12} />
                          <span>로그 출력</span>
                        </div>
                        <div className="training-log__content">
                          {trainingProgress.log_lines.slice(-10).map((line, i) => (
                            <div key={i} className={`log-line ${line.includes('Error') || line.includes('Traceback') ? 'error' : ''}`}>
                              {line}
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="training-idle">
                      <Brain size={32} />
                      <span>대기 중</span>
                      <p>학습을 시작하면 진행 상황이 여기에 표시됩니다.</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Pending Training Items */}
      <section className="premium-card">
        <div className="premium-card__header">
          <div className="premium-card__title">
            <Clock size={18} />
            <span>학습 대기 항목</span>
            <Badge variant="warning">{pendingItems.length}개</Badge>
          </div>
          <div className="header-actions">
            {selectedIds.size > 0 && (
              <>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={handleDeleteSelected}
                  disabled={deleteLoading === 'batch'}
                >
                  {deleteLoading === 'batch' ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                  <span>선택 삭제 ({selectedIds.size})</span>
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleTriggerTraining}
                  disabled={triggerLoading}
                >
                  {triggerLoading ? <Loader2 size={14} className="spin" /> : <Play size={14} />}
                  <span>선택 학습</span>
                </button>
              </>
            )}
          </div>
        </div>

        <div className="premium-card__body premium-card__body--no-padding">
          {pendingItems.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state__icon">
                <Clock size={32} />
              </div>
              <h4>학습 대기 항목이 없습니다</h4>
              <p>사용자가 👍 피드백을 보내면 여기에 표시됩니다.</p>
            </div>
          ) : (
            <div className="pending-table">
              <table>
                <thead>
                  <tr>
                    <th className="th-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === pendingItems.length && pendingItems.length > 0}
                        onChange={handleToggleSelectAll}
                      />
                    </th>
                    <th>질문</th>
                    <th>답변</th>
                    <th>점수</th>
                    <th>👍</th>
                    <th>카테고리</th>
                    <th>생성일</th>
                    <th>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingItems.map((item) => (
                    <tr key={item.id} className={selectedIds.has(item.id) ? 'selected' : ''}>
                      <td className="td-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(item.id)}
                          onChange={() => handleToggleSelect(item.id)}
                        />
                      </td>
                      <td className="td-question">
                        <Tooltip content={item.question}>
                          <span className="truncate-text">{item.question}</span>
                        </Tooltip>
                      </td>
                      <td className="td-answer">
                        <Tooltip content={item.answer.slice(0, 200) + (item.answer.length > 200 ? '...' : '')}>
                          <span className="truncate-text">{item.answer}</span>
                        </Tooltip>
                      </td>
                      <td>
                        <Badge variant={item.feedback_score >= 0.8 ? 'success' : 'warning'}>
                          {(item.feedback_score * 100).toFixed(0)}%
                        </Badge>
                      </td>
                      <td className="td-thumbs">
                        <span className="thumbs-count">
                          <ThumbsUp size={12} />
                          {item.thumbs_up_count}
                        </span>
                      </td>
                      <td>
                        {item.category ? (
                          <span className="category-tag">{item.category}</span>
                        ) : (
                          <span className="text-muted">-</span>
                        )}
                      </td>
                      <td className="text-muted text-sm">
                        {formatDate(item.created_at)}
                      </td>
                      <td>
                        <button
                          className="btn-icon btn-icon--danger"
                          onClick={() => handleDeleteItem(item.id)}
                          disabled={deleteLoading === item.id}
                          title="삭제"
                        >
                          {deleteLoading === item.id ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Training Batches */}
      <section className="premium-card">
        <div className="premium-card__header">
          <div className="premium-card__title">
            <Sparkles size={18} />
            <span>최근 학습 배치</span>
          </div>
          <span className="text-muted text-sm">{batches.length}개 배치</span>
        </div>

        <div className="premium-card__body premium-card__body--no-padding">
          {batches.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state__icon">
                <Sparkles size={32} />
              </div>
              <h4>학습 배치가 없습니다</h4>
              <p>첫 번째 학습을 시작하면 여기에 배치 기록이 표시됩니다.</p>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleTriggerTraining}
                disabled={triggerLoading || (stats?.pending_training_count === 0)}
              >
                <Play size={14} />
                <span>학습 시작하기</span>
              </button>
            </div>
          ) : (
            <div className="batch-table">
              <table>
                <thead>
                  <tr>
                    <th>Batch ID</th>
                    <th>상태</th>
                    <th>진행률</th>
                    <th>어댑터</th>
                    <th>Loss</th>
                    <th>시작</th>
                    <th>완료</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((batch) => {
                    const config = getStatusConfig(batch.status);
                    const progress = batch.total_samples > 0
                      ? Math.round((batch.trained_samples / batch.total_samples) * 100)
                      : 0;

                    return (
                      <tr key={batch.id}>
                        <td>
                          <code className="batch-id">{batch.batch_id}</code>
                        </td>
                        <td>
                          <Badge
                            variant={config.color as any}
                            icon={config.icon}
                          >
                            {config.label}
                          </Badge>
                        </td>
                        <td>
                          <div className="progress-cell">
                            <div className="progress-bar">
                              <div
                                className="progress-bar__fill"
                                style={{ width: `${progress}%` }}
                              />
                            </div>
                            <span className="progress-text">
                              {batch.trained_samples}/{batch.total_samples}
                            </span>
                          </div>
                        </td>
                        <td>
                          {batch.adapter_name ? (
                            <span className="adapter-tag">{batch.adapter_name}</span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {batch.eval_loss ? (
                            <span className="mono">{batch.eval_loss.toFixed(4)}</span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td className="text-muted">{formatDate(batch.started_at)}</td>
                        <td className="text-muted">{formatDate(batch.completed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Daily Statistics Chart */}
      <section className="premium-card">
        <div className="premium-card__header">
          <div className="premium-card__title">
            <BarChart3 size={18} />
            <span>일별 통계</span>
            <span className="text-muted text-sm">(최근 14일)</span>
          </div>
          <div className="chart-legend">
            <span className="legend-item">
              <span className="legend-dot legend-dot--new" />
              New Entries
            </span>
            <span className="legend-item">
              <span className="legend-dot legend-dot--trained" />
              Trained
            </span>
          </div>
        </div>

        <div className="premium-card__body">
          {dailyStats.length === 0 ? (
            <div className="empty-state empty-state--small">
              <BarChart3 size={24} />
              <span>통계 데이터가 없습니다</span>
            </div>
          ) : (
            <div className="chart-container">
              <div className="bar-chart">
                {dailyStats.slice().reverse().map((day, index) => (
                  <div key={day.date} className="bar-group">
                    <div className="bars">
                      <Tooltip content={`New: ${day.new_entries}`}>
                        <div
                          className="bar bar--new"
                          style={{
                            height: `${(day.new_entries / maxChartValue) * 100}%`,
                            animationDelay: `${index * 30}ms`
                          }}
                        />
                      </Tooltip>
                      <Tooltip content={`Trained: ${day.trained_entries}`}>
                        <div
                          className="bar bar--trained"
                          style={{
                            height: `${(day.trained_entries / maxChartValue) * 100}%`,
                            animationDelay: `${index * 30 + 15}ms`
                          }}
                        />
                      </Tooltip>
                    </div>
                    <span className="bar-label">{day.date.slice(5)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* How It Works Section */}
      <section className="how-it-works">
        <h3 className="section-title">
          <Info size={18} />
          Smarter RAG 동작 원리
        </h3>
        <div className="workflow-cards">
          <div className="workflow-card">
            <div className="workflow-card__number">1</div>
            <div className="workflow-card__content">
              <h4>피드백 수집</h4>
              <p>사용자의 👍/👎 피드백을 실시간으로 수집합니다.</p>
            </div>
          </div>
          <div className="workflow-card">
            <div className="workflow-card__number">2</div>
            <div className="workflow-card__content">
              <h4>검증된 지식 저장</h4>
              <p>👍 받은 응답은 Verified Knowledge Store에 등록됩니다.</p>
            </div>
          </div>
          <div className="workflow-card">
            <div className="workflow-card__number">3</div>
            <div className="workflow-card__content">
              <h4>QLoRA 학습</h4>
              <p>매일 자동으로 또는 수동으로 검증된 지식을 학습합니다.</p>
            </div>
          </div>
          <div className="workflow-card">
            <div className="workflow-card__number">4</div>
            <div className="workflow-card__content">
              <h4>스마트 응답</h4>
              <p>학습된 지식으로 더 정확하고 일관된 응답을 제공합니다.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LearningManagementTab;
