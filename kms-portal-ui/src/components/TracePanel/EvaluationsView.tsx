/**
 * EvaluationsView Component
 *
 * Displays evaluation results for each task.
 */
import React from 'react';
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  TrendingUp,
} from 'lucide-react';
import type { EvaluationResult, DAGStructure } from '../../store/traceStore';
import './EvaluationsView.css';

interface EvaluationsViewProps {
  evaluations: Record<string, EvaluationResult>;
  dag: DAGStructure | null;
  t: (key: string) => string;
}

// Score color based on value
const getScoreColor = (score: number): string => {
  if (score >= 0.8) return 'var(--color-success)';
  if (score >= 0.6) return 'var(--color-warning)';
  return 'var(--color-error)';
};

// Score bar component
const ScoreBar: React.FC<{ score: number }> = ({ score }) => {
  const percentage = Math.round(score * 100);
  const color = getScoreColor(score);

  return (
    <div className="eval-score-bar">
      <div
        className="eval-score-bar__fill"
        style={{
          width: `${percentage}%`,
          backgroundColor: color,
        }}
      />
      <span className="eval-score-bar__label" style={{ color: percentage >= 50 ? '#fff' : color }}>
        {percentage}%
      </span>
    </div>
  );
};

export const EvaluationsView: React.FC<EvaluationsViewProps> = ({
  evaluations,
  dag,
  t,
}) => {
  const evalEntries = Object.entries(evaluations);

  if (evalEntries.length === 0) {
    return (
      <div className="eval-empty">
        <TrendingUp size={48} strokeWidth={1} />
        <p>{t('trace.noEvaluations') || 'No evaluations yet'}</p>
        <p className="eval-empty-hint">
          {t('trace.noEvaluationsHint') || 'Evaluations appear after tasks complete'}
        </p>
      </div>
    );
  }

  // Count summary
  const passed = evalEntries.filter(([, e]) => e.passed).length;
  const failed = evalEntries.length - passed;
  const avgScore =
    evalEntries.reduce((sum, [, e]) => sum + (e.score ?? 0), 0) / evalEntries.length;

  return (
    <div className="eval-view">
      {/* Summary */}
      <div className="eval-summary">
        <div className="eval-summary__item eval-summary__item--passed">
          <CheckCircle size={18} />
          <span className="eval-summary__count">{passed}</span>
          <span className="eval-summary__label">{t('trace.passed') || 'Passed'}</span>
        </div>
        <div className="eval-summary__item eval-summary__item--failed">
          <XCircle size={18} />
          <span className="eval-summary__count">{failed}</span>
          <span className="eval-summary__label">{t('trace.failed') || 'Failed'}</span>
        </div>
        <div className="eval-summary__item eval-summary__item--avg">
          <TrendingUp size={18} />
          <span className="eval-summary__count">{Math.round(avgScore * 100)}%</span>
          <span className="eval-summary__label">{t('trace.avgScore') || 'Avg Score'}</span>
        </div>
      </div>

      {/* Evaluation cards */}
      <div className="eval-list">
        {evalEntries.map(([taskId, evaluation]) => {
          const task = dag?.tasks.find((t) => t.task_id === taskId);

          return (
            <div
              key={taskId}
              className={`eval-card ${evaluation.passed ? 'eval-card--passed' : 'eval-card--failed'}`}
            >
              {/* Header */}
              <div className="eval-card__header">
                <div className="eval-card__status">
                  {evaluation.passed ? (
                    <CheckCircle size={18} className="eval-icon--passed" />
                  ) : (
                    <XCircle size={18} className="eval-icon--failed" />
                  )}
                  <span className={`eval-badge ${evaluation.passed ? 'eval-badge--passed' : 'eval-badge--failed'}`}>
                    {evaluation.passed ? t('trace.passed') || 'PASSED' : t('trace.failed') || 'FAILED'}
                  </span>
                </div>

                <span className="eval-card__task-id">{taskId}</span>
              </div>

              {/* Task info */}
              {task && (
                <div className="eval-card__task">
                  <span className="eval-card__agent">{task.agent_type}</span>
                  <p className="eval-card__description">
                    {task.description.substring(0, 100)}...
                  </p>
                </div>
              )}

              {/* Score */}
              {evaluation.score !== undefined && (
                <div className="eval-card__score">
                  <span className="eval-card__score-label">
                    {t('trace.score') || 'Score'}
                  </span>
                  <ScoreBar score={evaluation.score} />
                </div>
              )}

              {/* Issues */}
              {evaluation.issues.length > 0 && (
                <div className="eval-card__issues">
                  <span className="eval-card__issues-label">
                    <AlertTriangle size={14} />
                    {t('trace.issues') || 'Issues'}
                  </span>
                  <ul className="eval-card__issues-list">
                    {evaluation.issues.map((issue, idx) => (
                      <li key={idx}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Retry info */}
              {evaluation.retry_recommended && (
                <div className="eval-card__retry">
                  <RefreshCw size={14} />
                  <span>
                    {t('trace.retryRecommended') || 'Retry Recommended'}
                    {evaluation.retry_reason && `: ${evaluation.retry_reason}`}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default EvaluationsView;
