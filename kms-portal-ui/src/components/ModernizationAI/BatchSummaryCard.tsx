/**
 * BatchSummaryCard — aggregate summary of batch analysis results.
 *
 * Shows: file count, feature count, support rate bar, risk breakdown, top issues.
 */

import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { BatchSummary } from '../../api/legacy.api';

interface BatchSummaryCardProps {
  summary: BatchSummary;
  isLoading?: boolean;
}

const RISK_COLORS: Record<string, string> = {
  HIGH: '#dc2626',
  MEDIUM: '#d97706',
  LOW: '#16a34a',
};

const BatchSummaryCard: React.FC<BatchSummaryCardProps> = ({ summary, isLoading }) => {
  const { t } = useTranslation();

  const ratePercent = Math.min(summary.overall_support_rate, 100);
  const rateColor = ratePercent >= 80 ? '#16a34a' : ratePercent >= 50 ? '#d97706' : '#dc2626';

  return (
    <div style={styles.card}>
      <h3 style={styles.title}>{t('legacy.summary.title')}</h3>

      {isLoading && <div style={styles.loadingBar} />}

      <div style={styles.statsRow}>
        <div style={styles.stat}>
          <span style={styles.statValue}>
            {summary.completed_files}/{summary.total_files}
          </span>
          <span style={styles.statLabel}>
            {t('legacy.summary.filesCompleted')}
          </span>
        </div>
        <div style={styles.stat}>
          <span style={styles.statValue}>{summary.total_features}</span>
          <span style={styles.statLabel}>
            {t('legacy.summary.featuresAnalyzed')}
          </span>
        </div>
        <div style={styles.stat}>
          <span style={styles.statValue}>{summary.total_incompatible}</span>
          <span style={styles.statLabel}>
            {t('legacy.summary.incompatibleItems')}
          </span>
        </div>
      </div>

      {/* Support rate bar */}
      <div style={styles.rateSection}>
        <div style={styles.rateHeader}>
          <span>{t('legacy.summary.supportRate')}</span>
          <span style={{ ...styles.rateValue, color: rateColor }}>
            {ratePercent.toFixed(1)}%
          </span>
        </div>
        <div style={styles.progressTrack}>
          <div
            style={{
              ...styles.progressFill,
              width: `${ratePercent}%`,
              backgroundColor: rateColor,
            }}
          />
        </div>
      </div>

      {/* Risk breakdown */}
      <div style={styles.riskSection}>
        <span style={styles.sectionLabel}>
          {t('legacy.summary.riskBreakdown')}
        </span>
        <div style={styles.riskBadges}>
          {(['HIGH', 'MEDIUM', 'LOW'] as const).map((level) => (
            <span
              key={level}
              style={{
                ...styles.riskBadge,
                backgroundColor: `${RISK_COLORS[level]}15`,
                color: RISK_COLORS[level],
                borderColor: `${RISK_COLORS[level]}40`,
              }}
            >
              {level}: {summary.risk_breakdown[level] ?? 0}
            </span>
          ))}
        </div>
      </div>

      {/* Top issues */}
      {summary.top_incompatible_items.length > 0 && (
        <div style={styles.issuesSection}>
          <span style={styles.sectionLabel}>
            {t('legacy.summary.topIssues')}
          </span>
          <ul style={styles.issueList}>
            {summary.top_incompatible_items.slice(0, 5).map((item, idx) => (
              <li key={idx} style={styles.issueItem}>
                <span
                  style={{
                    ...styles.issueDot,
                    backgroundColor: RISK_COLORS[item.risk] ?? '#6b7280',
                  }}
                />
                <span style={styles.issueText}>
                  {item.item}
                  {item.file_name && (
                    <span style={styles.issueFile}> ({item.file_name})</span>
                  )}
                </span>
                <span
                  style={{
                    ...styles.issueRisk,
                    color: RISK_COLORS[item.risk] ?? '#6b7280',
                  }}
                >
                  [{item.risk}]
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: 'var(--bg-secondary, #f9fafb)',
    border: '1px solid var(--border-color, #e5e7eb)',
    borderRadius: 12,
    padding: 20,
    marginBottom: 16,
  },
  title: {
    margin: '0 0 16px 0',
    fontSize: 16,
    fontWeight: 600,
    color: 'var(--text-primary, #111827)',
  },
  loadingBar: {
    height: 3,
    background: 'linear-gradient(90deg, #6366f1, #8b5cf6, #6366f1)',
    backgroundSize: '200% 100%',
    animation: 'shimmer 1.5s infinite',
    borderRadius: 2,
    marginBottom: 12,
  },
  statsRow: {
    display: 'flex',
    gap: 16,
    marginBottom: 16,
  },
  stat: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '8px 0',
    background: 'var(--bg-primary, #ffffff)',
    borderRadius: 8,
    border: '1px solid var(--border-color, #e5e7eb)',
  },
  statValue: {
    fontSize: 20,
    fontWeight: 700,
    color: 'var(--text-primary, #111827)',
  },
  statLabel: {
    fontSize: 11,
    color: 'var(--text-secondary, #6b7280)',
    marginTop: 2,
  },
  rateSection: {
    marginBottom: 14,
  },
  rateHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: 13,
    marginBottom: 6,
    color: 'var(--text-secondary, #6b7280)',
  },
  rateValue: {
    fontWeight: 700,
    fontSize: 14,
  },
  progressTrack: {
    height: 8,
    background: 'var(--bg-primary, #e5e7eb)',
    borderRadius: 4,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 4,
    transition: 'width 0.5s ease',
  },
  riskSection: {
    marginBottom: 14,
  },
  sectionLabel: {
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--text-secondary, #6b7280)',
    marginBottom: 6,
    display: 'block',
  },
  riskBadges: {
    display: 'flex',
    gap: 8,
    marginTop: 6,
  },
  riskBadge: {
    padding: '3px 10px',
    borderRadius: 12,
    fontSize: 12,
    fontWeight: 600,
    border: '1px solid',
  },
  issuesSection: {
    borderTop: '1px solid var(--border-color, #e5e7eb)',
    paddingTop: 12,
  },
  issueList: {
    listStyle: 'none',
    padding: 0,
    margin: '6px 0 0 0',
  },
  issueItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 0',
    fontSize: 13,
  },
  issueDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    flexShrink: 0,
  },
  issueText: {
    flex: 1,
    color: 'var(--text-primary, #111827)',
  },
  issueFile: {
    color: 'var(--text-secondary, #9ca3af)',
    fontSize: 12,
  },
  issueRisk: {
    fontSize: 11,
    fontWeight: 600,
  },
};

export default BatchSummaryCard;
