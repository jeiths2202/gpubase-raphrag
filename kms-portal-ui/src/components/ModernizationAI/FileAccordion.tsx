/**
 * FileAccordion — expandable list of per-file analysis results.
 *
 * Each file shows: name, type, support rate, risk badges.
 * Expanded state reveals the IncompatibilityReportView.
 */

import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { FileAnalysisResult } from '../../api/legacy.api';
import IncompatibilityReportView from './IncompatibilityReportView';

interface FileAccordionProps {
  fileResults: FileAnalysisResult[];
  expandedFiles: Set<string>;
  onToggle: (fileName: string) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

const RISK_COLORS: Record<string, string> = {
  HIGH: '#dc2626',
  MEDIUM: '#d97706',
  LOW: '#16a34a',
};

const FileAccordion: React.FC<FileAccordionProps> = ({
  fileResults,
  expandedFiles,
  onToggle,
  onExpandAll,
  onCollapseAll,
}) => {
  const { t } = useTranslation();

  return (
    <div style={styles.container}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        <button onClick={onExpandAll} style={styles.toolBtn}>
          {t('legacy.accordion.expandAll')}
        </button>
        <button onClick={onCollapseAll} style={styles.toolBtn}>
          {t('legacy.accordion.collapseAll')}
        </button>
      </div>

      {/* File items */}
      {fileResults.map((fr) => {
        const isExpanded = expandedFiles.has(fr.file_name);
        const rateColor = fr.support_rate >= 80 ? '#16a34a' : fr.support_rate >= 50 ? '#d97706' : '#dc2626';

        return (
          <div key={fr.file_name} style={styles.item}>
            {/* Header (click to toggle) */}
            <button
              onClick={() => onToggle(fr.file_name)}
              style={styles.itemHeader}
            >
              <span style={styles.arrow}>{isExpanded ? '\u25BC' : '\u25B6'}</span>
              <span style={styles.fileName}>{fr.file_name}</span>
              <span style={styles.assetType}>{fr.asset_type.toUpperCase()}</span>
              <span style={{ ...styles.rate, color: rateColor }}>
                {fr.support_rate.toFixed(1)}%
              </span>
              <span style={styles.riskMini}>
                {(['HIGH', 'MEDIUM', 'LOW'] as const).map((level) => {
                  const count = fr.risk_summary[level] ?? 0;
                  if (count === 0) return null;
                  return (
                    <span
                      key={level}
                      style={{
                        color: RISK_COLORS[level],
                        marginLeft: 6,
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                    >
                      {level[0]}:{count}
                    </span>
                  );
                })}
              </span>
              {fr.status === 'failed' && (
                <span style={styles.failBadge}>FAILED</span>
              )}
              {fr.status === 'in_progress' && (
                <span style={styles.progressBadge}>...</span>
              )}
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div style={styles.itemBody}>
                {fr.incompatibility_report ? (
                  <IncompatibilityReportView report={fr.incompatibility_report} />
                ) : fr.status === 'failed' ? (
                  <div style={styles.errorMsg}>
                    Analysis failed for this file.
                  </div>
                ) : (
                  <div style={styles.emptyMsg}>
                    No detailed report available.
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 1,
  },
  toolbar: {
    display: 'flex',
    gap: 8,
    marginBottom: 8,
  },
  toolBtn: {
    padding: '4px 12px',
    fontSize: 12,
    border: '1px solid var(--border-color, #d1d5db)',
    borderRadius: 6,
    background: 'var(--bg-primary, #ffffff)',
    color: 'var(--text-secondary, #6b7280)',
    cursor: 'pointer',
  },
  item: {
    border: '1px solid var(--border-color, #e5e7eb)',
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 4,
  },
  itemHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    width: '100%',
    padding: '10px 14px',
    border: 'none',
    background: 'var(--bg-secondary, #f9fafb)',
    cursor: 'pointer',
    textAlign: 'left' as const,
    fontSize: 13,
  },
  arrow: {
    fontSize: 10,
    color: 'var(--text-secondary, #9ca3af)',
    width: 14,
    flexShrink: 0,
  },
  fileName: {
    fontWeight: 600,
    color: 'var(--text-primary, #111827)',
    flex: 1,
    fontFamily: 'monospace',
  },
  assetType: {
    fontSize: 11,
    padding: '1px 8px',
    borderRadius: 10,
    background: 'var(--bg-primary, #e5e7eb)',
    color: 'var(--text-secondary, #6b7280)',
    fontWeight: 500,
  },
  rate: {
    fontWeight: 700,
    fontSize: 13,
    minWidth: 50,
    textAlign: 'right' as const,
  },
  riskMini: {
    display: 'flex',
    alignItems: 'center',
  },
  failBadge: {
    fontSize: 10,
    fontWeight: 700,
    color: '#dc2626',
    padding: '1px 6px',
    borderRadius: 8,
    backgroundColor: '#fee2e2',
  },
  progressBadge: {
    fontSize: 14,
    fontWeight: 700,
    color: '#6366f1',
  },
  itemBody: {
    padding: '12px 16px',
    borderTop: '1px solid var(--border-color, #e5e7eb)',
    background: 'var(--bg-primary, #ffffff)',
  },
  errorMsg: {
    color: '#dc2626',
    fontSize: 13,
    padding: 8,
  },
  emptyMsg: {
    color: 'var(--text-secondary, #9ca3af)',
    fontSize: 13,
    padding: 8,
  },
};

export default FileAccordion;
