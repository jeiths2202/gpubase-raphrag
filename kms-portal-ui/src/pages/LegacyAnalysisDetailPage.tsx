/**
 * LegacyAnalysisDetailPage - Popup detail view for persisted analysis
 *
 * Opened via window.open() from Data Table row click.
 * Standalone page (no sidebar/main layout) for popup window.
 */

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  FileCode2,
  CheckCircle2,
  XCircle,
  Shield,
  Code2,
  ChevronDown,
  ChevronRight,
  Loader2,
  Info,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { getPersistedAnalysisDetail } from '../api/legacy.api';
import type { PersistedAnalysisDetail, IncompatibilityReport } from '../api/legacy.api';
import './LegacyAnalysisDetailPage.css';

type TabId = 'overview' | 'incompatibility' | 'source' | 'reports';

export const LegacyAnalysisDetailPage: React.FC = () => {
  const { analysisId } = useParams<{ analysisId: string }>();
  const { t } = useTranslation();

  const [detail, setDetail] = useState<PersistedAnalysisDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['summary', 'incompatibleItems']));

  useEffect(() => {
    if (!analysisId) return;
    setLoading(true);
    getPersistedAnalysisDetail(analysisId)
      .then((res) => {
        setDetail(res);
        // Set window title
        document.title = `${res.file_name} - Analysis Detail`;
      })
      .catch(() => setError('Failed to load analysis detail'))
      .finally(() => setLoading(false));
  }, [analysisId]);

  const toggleSection = (key: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="ladp-loading">
        <Loader2 size={32} className="ladp-spinner" />
        <p>{t('legacy.dataTable.loading')}</p>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="ladp-loading">
        <XCircle size={32} style={{ color: 'var(--color-error)' }} />
        <p>{error || 'Analysis not found'}</p>
      </div>
    );
  }

  const report: IncompatibilityReport | null = detail.incompatibility_report as IncompatibilityReport | null;
  const supportRateColor =
    detail.support_rate >= 90 ? 'var(--color-success, #22c55e)'
      : detail.support_rate >= 70 ? 'var(--color-warning, #f59e0b)'
        : 'var(--color-error, #ef4444)';

  return (
    <div className="ladp">
      {/* Header */}
      <div className="ladp-header">
        <div className="ladp-header-left">
          <FileCode2 size={20} />
          <div>
            <h1 className="ladp-title">{detail.file_name}</h1>
            <span className="ladp-subtitle">
              {detail.asset_type.toUpperCase()} &middot; {detail.loc_count} {t('legacy.lines')}
              {detail.target_product && ` \u00B7 ${detail.target_product}`}
              {detail.target_version && ` v${detail.target_version}`}
            </span>
          </div>
        </div>
        <div className="ladp-header-right">
          <div className="ladp-stat-card">
            <span className="ladp-stat-label">{t('legacy.dataTable.supportRate')}</span>
            <span className="ladp-stat-value" style={{ color: supportRateColor }}>
              {detail.support_rate.toFixed(1)}%
            </span>
          </div>
          <div className="ladp-stat-card">
            <span className="ladp-stat-label">{t('legacy.dataTable.features')}</span>
            <span className="ladp-stat-value">{detail.total_features}</span>
          </div>
          <div className="ladp-stat-card">
            <span className="ladp-stat-label">{t('legacy.dataTable.incompatible')}</span>
            <span className="ladp-stat-value" style={{ color: detail.incompatible_count > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
              {detail.incompatible_count}
            </span>
          </div>
          <div className="ladp-stat-card">
            <span className="ladp-stat-label">{t('legacy.dataTable.risk')}</span>
            <div style={{ display: 'flex', gap: 4 }}>
              {detail.risk_high > 0 && <span className="ladp-risk ladp-risk-h">{detail.risk_high}H</span>}
              {detail.risk_medium > 0 && <span className="ladp-risk ladp-risk-m">{detail.risk_medium}M</span>}
              {detail.risk_low > 0 && <span className="ladp-risk ladp-risk-l">{detail.risk_low}L</span>}
              {detail.risk_high === 0 && detail.risk_medium === 0 && detail.risk_low === 0 && (
                <span style={{ color: 'var(--color-success)' }}>-</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="ladp-tabs">
        {([
          { id: 'overview' as TabId, label: t('legacy.detail.tabOverview') },
          { id: 'incompatibility' as TabId, label: t('legacy.detail.tabIncompatibility') },
          { id: 'source' as TabId, label: t('legacy.detail.tabSource') },
          { id: 'reports' as TabId, label: t('legacy.detail.tabReports') },
        ]).map((tab) => (
          <button
            key={tab.id}
            className={`ladp-tab ${activeTab === tab.id ? 'ladp-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="ladp-content">
        {/* Overview tab */}
        {activeTab === 'overview' && (
          <div className="ladp-overview">
            {/* File Overview */}
            {report?.file_overview && (
              <div className="ladp-section">
                <h3><Info size={16} /> {t('legacy.report.fileOverview')}</h3>
                <div className="ladp-kv-grid">
                  <div className="ladp-kv">
                    <span className="ladp-kv-label">{t('legacy.report.fileName')}</span>
                    <span className="ladp-kv-value">{report.file_overview.file_name}</span>
                  </div>
                  <div className="ladp-kv">
                    <span className="ladp-kv-label">{t('legacy.report.format')}</span>
                    <span className="ladp-kv-value">{report.file_overview.format}</span>
                  </div>
                  <div className="ladp-kv">
                    <span className="ladp-kv-label">{t('legacy.report.purpose')}</span>
                    <span className="ladp-kv-value">{report.file_overview.purpose}</span>
                  </div>
                  <div className="ladp-kv">
                    <span className="ladp-kv-label">{t('legacy.report.program')}</span>
                    <span className="ladp-kv-value">{report.file_overview.program}</span>
                  </div>
                  <div className="ladp-kv">
                    <span className="ladp-kv-label">{t('legacy.report.totalLines')}</span>
                    <span className="ladp-kv-value">{report.file_overview.total_lines}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Summary */}
            {report?.summary && (
              <div className="ladp-section">
                <h3><Shield size={16} /> {t('legacy.report.analysisSummary')}</h3>
                <div className="ladp-summary-grid">
                  <div className="ladp-summary-card">
                    <span className="ladp-summary-num" style={{ color: 'var(--color-primary)' }}>
                      {report.summary.total_features}
                    </span>
                    <span className="ladp-summary-label">{t('legacy.dataTable.features')}</span>
                  </div>
                  <div className="ladp-summary-card">
                    <span className="ladp-summary-num" style={{ color: 'var(--color-success)' }}>
                      {report.summary.supported}
                    </span>
                    <span className="ladp-summary-label">{t('legacy.verdict.supported')}</span>
                  </div>
                  <div className="ladp-summary-card">
                    <span className="ladp-summary-num" style={{ color: 'var(--color-error)' }}>
                      {report.summary.incompatible}
                    </span>
                    <span className="ladp-summary-label">{t('legacy.verdict.incompatible')}</span>
                  </div>
                  <div className="ladp-summary-card">
                    <span className="ladp-summary-num" style={{ color: supportRateColor }}>
                      {report.summary.support_rate.toFixed(1)}%
                    </span>
                    <span className="ladp-summary-label">{t('legacy.dataTable.supportRate')}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Recommendations */}
            {report?.recommendations && report.recommendations.length > 0 && (
              <div className="ladp-section">
                <h3>{t('legacy.report.recommendations')}</h3>
                <ul className="ladp-recommendations">
                  {report.recommendations.map((rec, i) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Incompatibility tab */}
        {activeTab === 'incompatibility' && report && (
          <div className="ladp-incompat">
            {/* Incompatible Items */}
            {report.incompatible_items && report.incompatible_items.length > 0 && (
              <CollapsibleSection
                title={`${t('legacy.report.incompatibleFindings')} (${report.incompatible_items.length})`}
                sectionKey="incompatibleItems"
                expanded={expandedSections.has('incompatibleItems')}
                onToggle={toggleSection}
              >
                <table className="ladp-mini-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>{t('legacy.detail.item')}</th>
                      <th>{t('legacy.dataTable.risk')}</th>
                      <th>{t('legacy.detail.description')}</th>
                      <th>{t('legacy.detail.mitigation')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.incompatible_items.map((item) => (
                      <tr key={item.id}>
                        <td>{item.id}</td>
                        <td className="ladp-mono">{item.item}</td>
                        <td>
                          <span className={`ladp-risk ladp-risk-${item.risk.toLowerCase().charAt(0)}`}>
                            {item.risk}
                          </span>
                        </td>
                        <td>{item.description}</td>
                        <td>{item.mitigation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CollapsibleSection>
            )}

            {/* Parser Verification */}
            {report.parser_verification && report.parser_verification.length > 0 && (
              <CollapsibleSection
                title={`${t('legacy.report.parserVerification')} (${report.parser_verification.length})`}
                sectionKey="parserVerification"
                expanded={expandedSections.has('parserVerification')}
                onToggle={toggleSection}
              >
                <table className="ladp-mini-table">
                  <thead>
                    <tr>
                      <th>{t('legacy.detail.statement')}</th>
                      <th>OF7 Token</th>
                      <th>Type</th>
                      <th>{t('legacy.results.status')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.parser_verification.map((pv, i) => (
                      <tr key={i}>
                        <td className="ladp-mono">{pv.statement}</td>
                        <td className="ladp-mono">{pv.of7_token}</td>
                        <td>{pv.stmt_type}</td>
                        <td>
                          <VerdictBadge verdict={pv.support} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CollapsibleSection>
            )}

            {/* Capability Lookup */}
            {report.capability_lookup && report.capability_lookup.length > 0 && (
              <CollapsibleSection
                title={`${t('legacy.report.capabilityLookup')} (${report.capability_lookup.length})`}
                sectionKey="capabilityLookup"
                expanded={expandedSections.has('capabilityLookup')}
                onToggle={toggleSection}
              >
                <table className="ladp-mini-table">
                  <thead>
                    <tr>
                      <th>{t('legacy.dataTable.features')}</th>
                      <th>Key</th>
                      <th>{t('legacy.results.status')}</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.capability_lookup.map((cl, i) => (
                      <tr key={i}>
                        <td className="ladp-mono">{cl.feature}</td>
                        <td className="ladp-mono">{cl.capability_key}</td>
                        <td><VerdictBadge verdict={cl.status} /></td>
                        <td>{cl.notes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CollapsibleSection>
            )}

            {/* Line Analysis */}
            {report.line_analysis && report.line_analysis.length > 0 && (
              <CollapsibleSection
                title={`${t('legacy.report.lineAnalysis')} (${report.line_analysis.length})`}
                sectionKey="lineAnalysis"
                expanded={expandedSections.has('lineAnalysis')}
                onToggle={toggleSection}
              >
                <div className="ladp-line-analysis">
                  {report.line_analysis.map((la, i) => (
                    <div key={i} className={`ladp-line ladp-line-${la.verdict.toLowerCase()}`}>
                      <span className="ladp-line-num">{la.line}</span>
                      <span className="ladp-line-src">{la.source}</span>
                      <span className="ladp-line-type">{la.syntax_type}</span>
                      <VerdictBadge verdict={la.verdict} />
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {!report.incompatible_items?.length && !report.parser_verification?.length && (
              <div className="ladp-empty-tab">
                <CheckCircle2 size={24} style={{ color: 'var(--color-success)' }} />
                <p>{t('legacy.detail.noIncompatibility')}</p>
              </div>
            )}
          </div>
        )}

        {/* Source code tab */}
        {activeTab === 'source' && (
          <div className="ladp-source-tab">
            {detail.source_code ? (
              <pre className="ladp-source-code">{detail.source_code}</pre>
            ) : (
              <div className="ladp-empty-tab">
                <Code2 size={24} style={{ opacity: 0.3 }} />
                <p>{t('legacy.detail.noSource')}</p>
              </div>
            )}
          </div>
        )}

        {/* Reports tab */}
        {activeTab === 'reports' && (
          <div className="ladp-reports-tab">
            {detail.reports && Object.keys(detail.reports).length > 0 ? (
              Object.entries(detail.reports).map(([key, value]) => (
                <CollapsibleSection
                  key={key}
                  title={key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                  sectionKey={`report-${key}`}
                  expanded={expandedSections.has(`report-${key}`)}
                  onToggle={toggleSection}
                >
                  <pre className="ladp-report-json">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                </CollapsibleSection>
              ))
            ) : (
              <div className="ladp-empty-tab">
                <Info size={24} style={{ opacity: 0.3 }} />
                <p>{t('legacy.detail.noReports')}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// Collapsible section component
const CollapsibleSection: React.FC<{
  title: string;
  sectionKey: string;
  expanded: boolean;
  onToggle: (key: string) => void;
  children: React.ReactNode;
}> = ({ title, sectionKey, expanded, onToggle, children }) => (
  <div className="ladp-collapsible">
    <button className="ladp-collapsible-header" onClick={() => onToggle(sectionKey)}>
      {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      <span>{title}</span>
    </button>
    {expanded && <div className="ladp-collapsible-body">{children}</div>}
  </div>
);

// Verdict badge component
const VerdictBadge: React.FC<{ verdict: string }> = ({ verdict }) => {
  const upper = verdict.toUpperCase();
  let cls = 'ladp-verdict';
  if (upper === 'OK' || upper === 'SUPPORTED' || upper === 'COMPATIBLE') cls += ' ladp-verdict-ok';
  else if (upper === 'WARNING') cls += ' ladp-verdict-warn';
  else if (upper === 'INCOMPATIBLE' || upper === 'UNSUPPORTED') cls += ' ladp-verdict-err';
  else if (upper === 'SYNTAX_ERROR') cls += ' ladp-verdict-err';
  else cls += ' ladp-verdict-info';
  return <span className={cls}>{verdict}</span>;
};

export default LegacyAnalysisDetailPage;
