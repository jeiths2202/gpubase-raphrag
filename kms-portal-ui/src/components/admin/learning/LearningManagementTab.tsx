/**
 * Learning Management Tab
 * Smarter RAG 시스템의 학습 관리 UI
 * - Verified Knowledge Store 현황
 * - 학습 배치 관리
 * - 수동 학습 트리거
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
  BookOpen,
  Trash2,
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

export const LearningManagementTab: React.FC = () => {
  // State
  const [stats, setStats] = useState<VerifiedKnowledgeStats | null>(null);
  const [batches, setBatches] = useState<TrainingBatch[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [schedule, setSchedule] = useState<TrainingSchedule | null>(null);
  const [llmStatus, setLlmStatus] = useState<LearningLLMStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggerLoading, setTriggerLoading] = useState(false);
  const [reloadLoading, setReloadLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statsRes, batchesRes, dailyRes, scheduleRes, llmStatusRes] = await Promise.all([
        client.get('/verified-knowledge/stats/overview'),
        client.get('/verified-knowledge/training/batches?limit=10'),
        client.get('/verified-knowledge/stats/daily?days=14'),
        client.get('/verified-knowledge/training/schedule').catch(() => ({ data: null })),
        client.get('/verified-knowledge/learning-llm/status').catch(() => ({ data: null })),
      ]);

      setStats(statsRes.data);
      setBatches(batchesRes.data);
      setDailyStats(dailyRes.data);
      setSchedule(scheduleRes.data);
      setLlmStatus(llmStatusRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
        // Refresh data after a delay
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
        // Refresh LLM status
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

  // Format date
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('ko-KR');
  };

  // Get status badge
  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { color: string; icon: React.ReactNode }> = {
      completed: { color: 'green', icon: <CheckCircle size={14} /> },
      training: { color: 'blue', icon: <Loader2 size={14} className="spin" /> },
      pending: { color: 'yellow', icon: <Clock size={14} /> },
      failed: { color: 'red', icon: <XCircle size={14} /> },
      collecting: { color: 'purple', icon: <Database size={14} /> },
    };

    const config = statusConfig[status] || { color: 'gray', icon: <Clock size={14} /> };

    return (
      <span className={`status-badge status-badge--${config.color}`}>
        {config.icon}
        <span>{status}</span>
      </span>
    );
  };

  if (loading) {
    return (
      <div className="learning-tab loading">
        <Loader2 className="spin" size={32} />
        <span>Loading...</span>
      </div>
    );
  }

  return (
    <div className="learning-tab">
      {/* Header */}
      <div className="learning-header">
        <div className="learning-header__title">
          <Brain size={24} />
          <h2>Smarter RAG - Learning Management</h2>
        </div>
        <div className="learning-header__actions">
          <button
            className="btn btn-secondary"
            onClick={fetchData}
            disabled={loading}
          >
            <RefreshCw size={16} />
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
      </div>

      {/* Messages */}
      {error && (
        <div className="message message--error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}
      {successMessage && (
        <div className="message message--success">
          <CheckCircle size={16} />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Stats Cards */}
      <div className="stats-grid">
        <div className="stat-card stat-card--primary">
          <div className="stat-card__icon">
            <Database size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">{stats?.active_count || 0}</div>
            <div className="stat-card__label">Active Knowledge</div>
          </div>
        </div>

        <div className="stat-card stat-card--success">
          <div className="stat-card__icon">
            <ThumbsUp size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">{stats?.trained_count || 0}</div>
            <div className="stat-card__label">Trained</div>
          </div>
        </div>

        <div className="stat-card stat-card--warning">
          <div className="stat-card__icon">
            <Clock size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">{stats?.pending_training_count || 0}</div>
            <div className="stat-card__label">Pending Training</div>
          </div>
        </div>

        <div className="stat-card stat-card--danger">
          <div className="stat-card__icon">
            <Trash2 size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">{stats?.unlearn_pending_count || 0}</div>
            <div className="stat-card__label">Pending Unlearn</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-card__icon">
            <TrendingUp size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">
              {((stats?.avg_feedback_score || 0) * 100).toFixed(1)}%
            </div>
            <div className="stat-card__label">Avg Feedback Score</div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-card__icon">
            <BookOpen size={24} />
          </div>
          <div className="stat-card__content">
            <div className="stat-card__value">{stats?.total_usage_count || 0}</div>
            <div className="stat-card__label">Total Usage</div>
          </div>
        </div>
      </div>

      {/* Schedule Section */}
      <div className="section">
        <h3 className="section__title">학습 스케줄</h3>
        {schedule && (
          <div className="schedule-card">
            <div className="schedule-info">
              <div className="schedule-item">
                <span className="schedule-item__label">스케줄</span>
                <span className="schedule-item__value">{schedule.cron_expression} (매일 00:00)</span>
              </div>
              <div className="schedule-item">
                <span className="schedule-item__label">상태</span>
                <span className={`schedule-item__value ${schedule.is_enabled ? 'enabled' : 'disabled'}`}>
                  {schedule.is_enabled ? '활성화' : '비활성화'}
                </span>
              </div>
              <div className="schedule-item">
                <span className="schedule-item__label">다음 실행</span>
                <span className="schedule-item__value">{formatDate(schedule.next_run_at)}</span>
              </div>
              <div className="schedule-item">
                <span className="schedule-item__label">마지막 실행</span>
                <span className="schedule-item__value">
                  {formatDate(schedule.last_run_at)}
                  {schedule.last_status && ` (${schedule.last_status})`}
                </span>
              </div>
            </div>
            <div className="schedule-actions">
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={schedule.is_enabled}
                  onChange={handleToggleSchedule}
                />
                <span className="toggle__slider"></span>
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Learning LLM Status */}
      <div className="section">
        <h3 className="section__title">Learning LLM 상태</h3>
        <div className="schedule-card">
          <div className="schedule-info">
            <div className="schedule-item">
              <span className="schedule-item__label">서비스</span>
              <span className={`schedule-item__value ${llmStatus?.enabled ? 'enabled' : 'disabled'}`}>
                {llmStatus?.enabled ? '활성화' : '비활성화'}
              </span>
            </div>
            <div className="schedule-item">
              <span className="schedule-item__label">모델 로드</span>
              <span className={`schedule-item__value ${llmStatus?.is_loaded ? 'enabled' : 'disabled'}`}>
                {llmStatus?.is_loaded ? '로드됨' : '미로드'}
              </span>
            </div>
            <div className="schedule-item">
              <span className="schedule-item__label">베이스 모델</span>
              <span className="schedule-item__value">{llmStatus?.base_model || '-'}</span>
            </div>
            <div className="schedule-item">
              <span className="schedule-item__label">현재 어댑터</span>
              <span className="schedule-item__value">{llmStatus?.current_adapter || '없음'}</span>
            </div>
            <div className="schedule-item">
              <span className="schedule-item__label">사용 가능한 어댑터</span>
              <span className="schedule-item__value">{llmStatus?.available_adapters?.length || 0}개</span>
            </div>
          </div>
          <div className="schedule-actions">
            <button
              className="btn btn-secondary"
              onClick={() => handleReloadLLM()}
              disabled={reloadLoading || !llmStatus?.enabled || (llmStatus?.available_adapters?.length === 0)}
            >
              {reloadLoading ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}
              <span>어댑터 리로드</span>
            </button>
          </div>
        </div>
        {llmStatus?.available_adapters && llmStatus.available_adapters.length > 0 && (
          <div className="adapter-list" style={{ marginTop: 'var(--spacing-md)' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              최근 어댑터: {llmStatus.available_adapters.slice(0, 5).join(', ')}
            </span>
          </div>
        )}
      </div>

      {/* Training Batches */}
      <div className="section">
        <h3 className="section__title">최근 학습 배치</h3>
        <div className="batches-table">
          <table>
            <thead>
              <tr>
                <th>Batch ID</th>
                <th>상태</th>
                <th>샘플 수</th>
                <th>어댑터</th>
                <th>Loss</th>
                <th>시작</th>
                <th>완료</th>
              </tr>
            </thead>
            <tbody>
              {batches.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-row">
                    학습 배치가 없습니다
                  </td>
                </tr>
              ) : (
                batches.map((batch) => (
                  <tr key={batch.id}>
                    <td className="batch-id">{batch.batch_id}</td>
                    <td>{getStatusBadge(batch.status)}</td>
                    <td>
                      {batch.trained_samples} / {batch.total_samples}
                    </td>
                    <td>{batch.adapter_name || '-'}</td>
                    <td>{batch.eval_loss?.toFixed(4) || '-'}</td>
                    <td>{formatDate(batch.started_at)}</td>
                    <td>{formatDate(batch.completed_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Daily Stats Chart */}
      <div className="section">
        <h3 className="section__title">일별 통계 (최근 14일)</h3>
        <div className="daily-stats-chart">
          {dailyStats.length === 0 ? (
            <div className="empty-chart">데이터가 없습니다</div>
          ) : (
            <div className="chart-bars">
              {dailyStats.slice().reverse().map((day) => (
                <div key={day.date} className="chart-bar-group">
                  <div className="chart-bars-container">
                    <div
                      className="chart-bar chart-bar--new"
                      style={{ height: `${Math.min(day.new_entries * 10, 100)}%` }}
                      title={`New: ${day.new_entries}`}
                    />
                    <div
                      className="chart-bar chart-bar--trained"
                      style={{ height: `${Math.min(day.trained_entries * 10, 100)}%` }}
                      title={`Trained: ${day.trained_entries}`}
                    />
                  </div>
                  <div className="chart-label">{day.date.slice(5)}</div>
                </div>
              ))}
            </div>
          )}
          <div className="chart-legend">
            <span className="legend-item legend-item--new">New Entries</span>
            <span className="legend-item legend-item--trained">Trained</span>
          </div>
        </div>
      </div>

      {/* System Health */}
      <div className="section">
        <h3 className="section__title">시스템 상태</h3>
        <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div className="stat-card">
            <div className="stat-card__content">
              <div className="stat-card__label">RAG 응답 전략</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 'var(--spacing-sm)' }}>
                <div>Verified Knowledge: 최우선</div>
                <div>Learning LLM: 2순위</div>
                <div>Document RAG: 폴백</div>
              </div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card__content">
              <div className="stat-card__label">피드백 영향</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 'var(--spacing-sm)' }}>
                <div>👍 → VK Store 등록 → 학습</div>
                <div>👎 → VK Store 삭제 → 망각</div>
              </div>
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-card__content">
              <div className="stat-card__label">학습 효과</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: 'var(--spacing-sm)' }}>
                <div>동일 질문: VK Store 응답</div>
                <div>유사 질문: Learning LLM 생성</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* How it works */}
      <div className="section">
        <h3 className="section__title">Smarter RAG 동작 원리</h3>
        <div className="how-it-works">
          <div className="step">
            <div className="step__number">1</div>
            <div className="step__content">
              <h4>사용자 피드백 수집</h4>
              <p>사용자가 응답에 👍/👎 피드백을 제공합니다.</p>
            </div>
          </div>
          <div className="step">
            <div className="step__number">2</div>
            <div className="step__content">
              <h4>Verified Knowledge Store</h4>
              <p>👍 받은 응답은 자동으로 검증된 지식 저장소에 등록됩니다.</p>
            </div>
          </div>
          <div className="step">
            <div className="step__number">3</div>
            <div className="step__content">
              <h4>QLoRA 학습</h4>
              <p>매일 00:00 또는 수동 트리거로 검증된 지식을 학습합니다.</p>
            </div>
          </div>
          <div className="step">
            <div className="step__number">4</div>
            <div className="step__content">
              <h4>스마트 응답</h4>
              <p>학습된 지식으로 더 정확한 응답을 제공합니다.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LearningManagementTab;
