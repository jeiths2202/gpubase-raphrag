/**
 * IncompatibilityReportView — renders the 7-section incompatibility report.
 *
 * Sections: file_overview, parser_verification, line_analysis, capability_lookup,
 *           incompatible_items, recommendations, summary
 */

import React from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import type { IncompatibilityReport } from '../../api/legacy.api';

interface IncompatibilityReportViewProps {
  report: IncompatibilityReport;
}

const VERDICT_STYLES: Record<string, { bg: string; color: string; label: string }> = {
  OK: { bg: '#dcfce7', color: '#166534', label: 'OK' },
  SUPPORTED: { bg: '#dcfce7', color: '#166534', label: 'Supported' },
  WARNING: { bg: '#fef9c3', color: '#854d0e', label: 'Warning' },
  INCOMPATIBLE: { bg: '#fee2e2', color: '#991b1b', label: 'Incompatible' },
  SYNTAX_ERROR: { bg: '#ede9fe', color: '#5b21b6', label: 'Syntax Error' },
  NOT_FOUND: { bg: '#f3f4f6', color: '#6b7280', label: 'Not Found' },
  UNKNOWN: { bg: '#f3f4f6', color: '#6b7280', label: 'Unknown' },
};

const RISK_COLORS: Record<string, string> = {
  HIGH: '#dc2626',
  MEDIUM: '#d97706',
  LOW: '#16a34a',
};

const IncompatibilityReportView: React.FC<IncompatibilityReportViewProps> = ({ report }) => {
  const { t } = useTranslation();

  return (
    <div style={styles.container}>
      {/* Section 1: File Overview */}
      <Section title={t('legacy.report.fileOverview')}>
        <div style={styles.overviewGrid}>
          <InfoRow label={t('legacy.report.fileName')} value={report.file_overview.file_name} />
          <InfoRow label={t('legacy.report.format')} value={report.file_overview.format} />
          <InfoRow label={t('legacy.report.purpose')} value={report.file_overview.purpose} />
          {report.file_overview.program && (
            <InfoRow label={t('legacy.report.program')} value={report.file_overview.program} />
          )}
          <InfoRow label={t('legacy.report.totalLines')} value={String(report.file_overview.total_lines)} />
        </div>
      </Section>

      {/* Section 2: Parser Verification */}
      {report.parser_verification.length > 0 && (
        <Section title={t('legacy.report.parserVerification')}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Statement</th>
                <th style={styles.th}>OF7 Token</th>
                <th style={styles.th}>Type</th>
                <th style={styles.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {report.parser_verification.map((pv, idx) => {
                const vs = VERDICT_STYLES[pv.support] ?? VERDICT_STYLES.UNKNOWN;
                return (
                  <tr key={idx}>
                    <td style={styles.td}><code>{pv.statement}</code></td>
                    <td style={styles.td}><code style={styles.token}>{pv.of7_token}</code></td>
                    <td style={styles.td}>{pv.stmt_type}</td>
                    <td style={styles.td}>
                      <VerdictBadge label={vs.label} bg={vs.bg} color={vs.color} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Section>
      )}

      {/* Section 3: Line Analysis (show only non-OK or first 30) */}
      {report.line_analysis.length > 0 && (
        <Section title={t('legacy.report.lineAnalysis')}>
          <div style={styles.lineList}>
            {report.line_analysis
              .filter((la) => la.verdict !== 'OK')
              .slice(0, 30)
              .map((la, idx) => {
                const vs = VERDICT_STYLES[la.verdict] ?? VERDICT_STYLES.UNKNOWN;
                return (
                  <div key={idx} style={{ ...styles.lineRow, borderLeftColor: vs.color }}>
                    <span style={styles.lineNum}>L{la.line}</span>
                    <code style={styles.lineSource}>{la.source}</code>
                    <VerdictBadge label={vs.label} bg={vs.bg} color={vs.color} />
                  </div>
                );
              })}
            {report.line_analysis.filter((la) => la.verdict === 'OK').length > 0 && (
              <div style={styles.okSummary}>
                {report.line_analysis.filter((la) => la.verdict === 'OK').length} lines OK
              </div>
            )}
          </div>
        </Section>
      )}

      {/* Section 4: Capability Lookup (non-SUPPORTED only) */}
      {report.capability_lookup.length > 0 && (
        <Section title={t('legacy.report.capabilityLookup')}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Feature</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Notes</th>
              </tr>
            </thead>
            <tbody>
              {report.capability_lookup
                .filter((cl) => cl.status !== 'SUPPORTED' && cl.status !== 'FULL')
                .slice(0, 20)
                .map((cl, idx) => {
                  const vs = VERDICT_STYLES[cl.status] ?? VERDICT_STYLES.UNKNOWN;
                  return (
                    <tr key={idx}>
                      <td style={styles.td}><code>{cl.feature}</code></td>
                      <td style={styles.td}>
                        <VerdictBadge label={vs.label} bg={vs.bg} color={vs.color} />
                      </td>
                      <td style={styles.td}>{cl.notes}</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </Section>
      )}

      {/* Section 5: Incompatible Items */}
      {report.incompatible_items.length > 0 && (
        <Section title={t('legacy.report.incompatibleFindings')}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>#</th>
                <th style={styles.th}>Item</th>
                <th style={styles.th}>Risk</th>
                <th style={styles.th}>Description</th>
                <th style={styles.th}>Mitigation</th>
              </tr>
            </thead>
            <tbody>
              {report.incompatible_items.map((item) => (
                <tr key={item.id}>
                  <td style={styles.td}>{item.id}</td>
                  <td style={styles.td}><code>{item.item}</code></td>
                  <td style={styles.td}>
                    <span style={{ ...styles.riskBadge, color: RISK_COLORS[item.risk] ?? '#6b7280' }}>
                      {item.risk}
                    </span>
                  </td>
                  <td style={styles.td}>{item.description}</td>
                  <td style={styles.td}>{item.mitigation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {/* Section 6: Recommendations */}
      {report.recommendations.length > 0 && (
        <Section title={t('legacy.report.recommendations')}>
          <ul style={styles.recList}>
            {report.recommendations.map((rec, idx) => (
              <li key={idx} style={styles.recItem}>{rec}</li>
            ))}
          </ul>
        </Section>
      )}

      {/* Section 7: Summary */}
      <Section title={t('legacy.report.analysisSummary')}>
        <div style={styles.summaryGrid}>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Features</span>
            <span style={styles.summaryValue}>{report.summary.total_features}</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Supported</span>
            <span style={{ ...styles.summaryValue, color: '#16a34a' }}>{report.summary.supported}</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Incompatible</span>
            <span style={{ ...styles.summaryValue, color: '#dc2626' }}>{report.summary.incompatible}</span>
          </div>
          <div style={styles.summaryItem}>
            <span style={styles.summaryLabel}>Rate</span>
            <span style={styles.summaryValue}>{report.summary.support_rate}%</span>
          </div>
        </div>
      </Section>
    </div>
  );
};

// Sub-components

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div style={styles.section}>
    <h4 style={styles.sectionTitle}>{title}</h4>
    {children}
  </div>
);

const VerdictBadge: React.FC<{ label: string; bg: string; color: string }> = ({ label, bg, color }) => (
  <span style={{ ...styles.badge, backgroundColor: bg, color }}>{label}</span>
);

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div style={styles.infoRow}>
    <span style={styles.infoLabel}>{label}</span>
    <span style={styles.infoValue}>{value}</span>
  </div>
);

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  section: {
    padding: '10px 0',
    borderBottom: '1px solid var(--border-color, #f3f4f6)',
  },
  sectionTitle: {
    margin: '0 0 8px 0',
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--text-primary, #374151)',
  },
  overviewGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
  infoRow: {
    display: 'flex',
    gap: 12,
    fontSize: 13,
  },
  infoLabel: {
    width: 80,
    color: 'var(--text-secondary, #6b7280)',
    flexShrink: 0,
  },
  infoValue: {
    color: 'var(--text-primary, #111827)',
    fontWeight: 500,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: 12,
  },
  th: {
    textAlign: 'left' as const,
    padding: '6px 8px',
    background: 'var(--bg-primary, #f9fafb)',
    borderBottom: '1px solid var(--border-color, #e5e7eb)',
    fontWeight: 600,
    color: 'var(--text-secondary, #6b7280)',
    fontSize: 11,
  },
  td: {
    padding: '5px 8px',
    borderBottom: '1px solid var(--border-color, #f3f4f6)',
    verticalAlign: 'top' as const,
    color: 'var(--text-primary, #374151)',
  },
  token: {
    fontSize: 11,
    color: '#7c3aed',
  },
  badge: {
    display: 'inline-block',
    padding: '1px 8px',
    borderRadius: 10,
    fontSize: 11,
    fontWeight: 600,
  },
  riskBadge: {
    fontWeight: 700,
    fontSize: 12,
  },
  lineList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  lineRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '3px 8px',
    borderLeft: '3px solid',
    fontSize: 12,
    background: 'var(--bg-primary, #ffffff)',
    borderRadius: '0 4px 4px 0',
  },
  lineNum: {
    width: 36,
    color: 'var(--text-secondary, #9ca3af)',
    fontFamily: 'monospace',
    flexShrink: 0,
  },
  lineSource: {
    flex: 1,
    fontFamily: 'monospace',
    fontSize: 11,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
    color: 'var(--text-primary, #374151)',
  },
  okSummary: {
    textAlign: 'center' as const,
    color: '#16a34a',
    fontSize: 12,
    padding: 4,
  },
  recList: {
    margin: 0,
    paddingLeft: 16,
  },
  recItem: {
    fontSize: 13,
    color: 'var(--text-primary, #374151)',
    padding: '2px 0',
  },
  summaryGrid: {
    display: 'flex',
    gap: 12,
  },
  summaryItem: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: 8,
    background: 'var(--bg-primary, #ffffff)',
    borderRadius: 8,
    border: '1px solid var(--border-color, #e5e7eb)',
  },
  summaryLabel: {
    fontSize: 11,
    color: 'var(--text-secondary, #6b7280)',
  },
  summaryValue: {
    fontSize: 18,
    fontWeight: 700,
    color: 'var(--text-primary, #111827)',
  },
};

export default IncompatibilityReportView;
