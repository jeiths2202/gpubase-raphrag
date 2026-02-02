/**
 * Admin Scoring Configuration Page
 *
 * RAG Scoring Configuration Management UI
 * - View/Edit scoring parameters (RRF, BM25, Boost, Confidence)
 * - Real-time simulation with test queries
 * - Configuration history and rollback
 * - Parameter metadata with descriptions
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Settings,
  RefreshCw,
  Save,
  RotateCcw,
  Play,
  History,
  AlertTriangle,
  CheckCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Info,
  Sliders,
  Search,
  GitCompare,
  TestTube,
  Clock,
  User,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './AdminScoringPage.css';

// Types
interface RRFConfig {
  k: number;
  vector_weight: number;
  graph_weight: number;
  bm25_weight: number;
}

interface BM25Config {
  k1: number;
  b: number;
  avg_doc_length: number;
}

interface BoostConfig {
  title_match_boost: number;
  exact_phrase_boost: number;
  error_code_boost: number;
  source_count_bonus: number;
}

interface ConfidenceConfig {
  high_threshold: number;
  medium_threshold: number;
  low_threshold: number;
}

interface ScoringConfig {
  rrf: RRFConfig;
  bm25: BM25Config;
  boost: BoostConfig;
  confidence: ConfidenceConfig;
}

interface ConfigHistory {
  id: string;
  config: ScoringConfig;
  user_id: string;
  reason: string | null;
  created_at: string;
}

interface ParameterMeta {
  description: string;
  min: number;
  max: number;
  step: number;
  unit?: string;
  effect?: string;
}

interface SimulationResult {
  query: string;
  config: ScoringConfig;
  steps: Array<{
    name: string;
    description: string;
    input_count: number;
    output_count: number;
    duration_ms: number;
    details: Record<string, unknown>;
  }>;
  final_results: Array<{
    doc_id: string;
    title: string;
    final_score: number;
    vector_score: number;
    bm25_score: number;
    graph_score: number;
    boost_applied: number;
  }>;
  total_duration_ms: number;
}

// Tab configuration
type TabId = 'config' | 'simulate' | 'history';

const TABS = [
  { id: 'config' as TabId, labelKey: 'scoring.tabs.config', icon: <Sliders size={18} /> },
  { id: 'simulate' as TabId, labelKey: 'scoring.tabs.simulate', icon: <TestTube size={18} /> },
  { id: 'history' as TabId, labelKey: 'scoring.tabs.history', icon: <History size={18} /> },
];

// Parameter Slider Component
interface ParameterSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  description?: string;
  onChange: (value: number) => void;
}

const ParameterSlider: React.FC<ParameterSliderProps> = ({
  label,
  value,
  min,
  max,
  step,
  unit = '',
  description,
  onChange,
}) => {
  const percentage = ((value - min) / (max - min)) * 100;

  return (
    <div className="scoring-param-slider">
      <div className="scoring-param-header">
        <label className="scoring-param-label">{label}</label>
        <span className="scoring-param-value">
          {value.toFixed(step < 1 ? 2 : 0)}{unit}
        </span>
      </div>
      {description && (
        <p className="scoring-param-description">{description}</p>
      )}
      <div className="scoring-slider-container">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="scoring-slider"
          style={{
            background: `linear-gradient(to right, var(--color-primary) 0%, var(--color-primary) ${percentage}%, var(--color-border) ${percentage}%, var(--color-border) 100%)`,
          }}
        />
        <div className="scoring-slider-range">
          <span>{min}</span>
          <span>{max}</span>
        </div>
      </div>
    </div>
  );
};

// Configuration Section Component
interface ConfigSectionProps {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}

const ConfigSection: React.FC<ConfigSectionProps> = ({
  title,
  icon,
  children,
  defaultExpanded = true,
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`scoring-config-section ${expanded ? 'expanded' : 'collapsed'}`}>
      <button
        className="scoring-section-header"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="scoring-section-title">
          {icon}
          <span>{title}</span>
        </div>
        {expanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
      </button>
      {expanded && (
        <div className="scoring-section-content">
          {children}
        </div>
      )}
    </div>
  );
};

// Main Component
export const AdminScoringPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<TabId>('config');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [config, setConfig] = useState<ScoringConfig | null>(null);
  const [originalConfig, setOriginalConfig] = useState<ScoringConfig | null>(null);
  const [source, setSource] = useState<string>('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [history, setHistory] = useState<ConfigHistory[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Simulation state
  const [simulateQuery, setSimulateQuery] = useState('');
  const [simulating, setSimulating] = useState(false);
  const [simulationResult, setSimulationResult] = useState<SimulationResult | null>(null);

  // Fetch current config
  const fetchConfig = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/admin/scoring/config', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setConfig(result.config);
      setOriginalConfig(result.config);
      setSource(result.source || 'unknown');
      setWarnings(result.warnings || []);
      setError(null);
    } catch (err) {
      console.error('Failed to load scoring config:', err);
      setError(t('scoring.errors.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  // Fetch configuration history
  const fetchHistory = useCallback(async () => {
    try {
      setHistoryLoading(true);
      const response = await fetch('/api/v1/admin/scoring/config/history?limit=20', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setHistory(result || []);
    } catch (err) {
      console.error('Failed to load config history:', err);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  // Save config
  const handleSave = async () => {
    if (!config) return;

    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const response = await fetch('/api/v1/admin/scoring/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          config,
          reason: 'Updated via Admin UI',
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setConfig(result.config);
      setOriginalConfig(result.config);
      setSource(result.source || 'runtime');
      setWarnings(result.warnings || []);
      setSuccess(t('scoring.success.saved'));

      // Refresh history
      fetchHistory();
    } catch (err) {
      console.error('Failed to save config:', err);
      setError(t('scoring.errors.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  // Reset to defaults
  const handleReset = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const response = await fetch('/api/v1/admin/scoring/config/reset', {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setConfig(result.config);
      setOriginalConfig(result.config);
      setSource(result.source || 'environment');
      setWarnings(result.warnings || []);
      setSuccess(t('scoring.success.reset'));
    } catch (err) {
      console.error('Failed to reset config:', err);
      setError(t('scoring.errors.resetFailed'));
    } finally {
      setSaving(false);
    }
  };

  // Rollback to history version
  const handleRollback = async (historyId: string) => {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      const response = await fetch(`/api/v1/admin/scoring/config/rollback/${historyId}`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setConfig(result.config);
      setOriginalConfig(result.config);
      setSource(result.source || 'rollback');
      setWarnings(result.warnings || []);
      setSuccess(t('scoring.success.rollback'));
      fetchHistory();
    } catch (err) {
      console.error('Failed to rollback config:', err);
      setError(t('scoring.errors.rollbackFailed'));
    } finally {
      setSaving(false);
    }
  };

  // Run simulation
  const handleSimulate = async () => {
    if (!simulateQuery.trim()) return;

    try {
      setSimulating(true);
      setError(null);

      const response = await fetch('/api/v1/admin/scoring/simulate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          query: simulateQuery,
          config: config,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setSimulationResult(result);
    } catch (err) {
      console.error('Failed to run simulation:', err);
      setError(t('scoring.errors.simulateFailed'));
    } finally {
      setSimulating(false);
    }
  };

  // Check if config has changes
  const hasChanges = config && originalConfig &&
    JSON.stringify(config) !== JSON.stringify(originalConfig);

  // Update nested config value
  const updateConfig = <K extends keyof ScoringConfig>(
    section: K,
    key: keyof ScoringConfig[K],
    value: number
  ) => {
    if (!config) return;
    setConfig({
      ...config,
      [section]: {
        ...config[section],
        [key]: value,
      },
    });
  };

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (activeTab === 'history') {
      fetchHistory();
    }
  }, [activeTab, fetchHistory]);

  // Clear messages after timeout
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  // Loading state
  if (loading) {
    return (
      <div className="scoring-page scoring-page--loading">
        <Loader2 className="scoring-loading-spinner" size={48} />
        <p>{t('scoring.loading')}</p>
      </div>
    );
  }

  // Error state (no config)
  if (error && !config) {
    return (
      <div className="scoring-page scoring-page--error">
        <AlertTriangle size={48} />
        <h2>{t('scoring.errors.title')}</h2>
        <p>{error}</p>
        <button onClick={fetchConfig} className="scoring-retry-btn">
          <RefreshCw size={16} />
          {t('common.retry')}
        </button>
      </div>
    );
  }

  return (
    <div className="scoring-page">
      {/* Header */}
      <header className="scoring-header">
        <div className="scoring-header-info">
          <h1>
            <Settings size={28} />
            {t('scoring.title')}
          </h1>
          <p className="scoring-subtitle">{t('scoring.subtitle')}</p>
          <div className="scoring-source-badge">
            <span className={`scoring-source scoring-source--${source}`}>
              {t(`scoring.source.${source}`)}
            </span>
          </div>
        </div>
        <div className="scoring-header-actions">
          {hasChanges && (
            <button
              className="scoring-btn scoring-btn--secondary"
              onClick={() => setConfig(originalConfig)}
              disabled={saving}
            >
              <RotateCcw size={16} />
              {t('common.discard')}
            </button>
          )}
          <button
            className="scoring-btn scoring-btn--primary"
            onClick={handleSave}
            disabled={saving || !hasChanges}
          >
            {saving ? <Loader2 size={16} className="spinning" /> : <Save size={16} />}
            {t('common.save')}
          </button>
        </div>
      </header>

      {/* Alerts */}
      {error && (
        <div className="scoring-alert scoring-alert--error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="scoring-alert scoring-alert--success">
          <CheckCircle size={16} />
          <span>{success}</span>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="scoring-alert scoring-alert--warning">
          <Info size={16} />
          <div>
            {warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        </div>
      )}

      {/* Tabs */}
      <nav className="scoring-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`scoring-tab ${activeTab === tab.id ? 'scoring-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{t(tab.labelKey)}</span>
          </button>
        ))}
      </nav>

      {/* Tab Content */}
      <main className="scoring-content">
        {/* Configuration Tab */}
        {activeTab === 'config' && config && (
          <div className="scoring-config-grid">
            {/* RRF Configuration */}
            <ConfigSection
              title={t('scoring.sections.rrf')}
              icon={<GitCompare size={20} />}
            >
              <ParameterSlider
                label={t('scoring.params.rrf.k')}
                value={config.rrf.k}
                min={1}
                max={100}
                step={1}
                description={t('scoring.params.rrf.k_desc')}
                onChange={(v) => updateConfig('rrf', 'k', v)}
              />
              <ParameterSlider
                label={t('scoring.params.rrf.vector_weight')}
                value={config.rrf.vector_weight}
                min={0}
                max={1}
                step={0.05}
                description={t('scoring.params.rrf.vector_weight_desc')}
                onChange={(v) => updateConfig('rrf', 'vector_weight', v)}
              />
              <ParameterSlider
                label={t('scoring.params.rrf.graph_weight')}
                value={config.rrf.graph_weight}
                min={0}
                max={1}
                step={0.05}
                description={t('scoring.params.rrf.graph_weight_desc')}
                onChange={(v) => updateConfig('rrf', 'graph_weight', v)}
              />
              <ParameterSlider
                label={t('scoring.params.rrf.bm25_weight')}
                value={config.rrf.bm25_weight}
                min={0}
                max={1}
                step={0.05}
                description={t('scoring.params.rrf.bm25_weight_desc')}
                onChange={(v) => updateConfig('rrf', 'bm25_weight', v)}
              />
            </ConfigSection>

            {/* BM25 Configuration */}
            <ConfigSection
              title={t('scoring.sections.bm25')}
              icon={<Search size={20} />}
            >
              <ParameterSlider
                label={t('scoring.params.bm25.k1')}
                value={config.bm25.k1}
                min={0.5}
                max={3.0}
                step={0.1}
                description={t('scoring.params.bm25.k1_desc')}
                onChange={(v) => updateConfig('bm25', 'k1', v)}
              />
              <ParameterSlider
                label={t('scoring.params.bm25.b')}
                value={config.bm25.b}
                min={0}
                max={1}
                step={0.05}
                description={t('scoring.params.bm25.b_desc')}
                onChange={(v) => updateConfig('bm25', 'b', v)}
              />
              <ParameterSlider
                label={t('scoring.params.bm25.avg_doc_length')}
                value={config.bm25.avg_doc_length}
                min={100}
                max={2000}
                step={50}
                description={t('scoring.params.bm25.avg_doc_length_desc')}
                onChange={(v) => updateConfig('bm25', 'avg_doc_length', v)}
              />
            </ConfigSection>

            {/* Boost Configuration */}
            <ConfigSection
              title={t('scoring.sections.boost')}
              icon={<Sliders size={20} />}
            >
              <ParameterSlider
                label={t('scoring.params.boost.title_match')}
                value={config.boost.title_match_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description={t('scoring.params.boost.title_match_desc')}
                onChange={(v) => updateConfig('boost', 'title_match_boost', v)}
              />
              <ParameterSlider
                label={t('scoring.params.boost.exact_phrase')}
                value={config.boost.exact_phrase_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description={t('scoring.params.boost.exact_phrase_desc')}
                onChange={(v) => updateConfig('boost', 'exact_phrase_boost', v)}
              />
              <ParameterSlider
                label={t('scoring.params.boost.error_code')}
                value={config.boost.error_code_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description={t('scoring.params.boost.error_code_desc')}
                onChange={(v) => updateConfig('boost', 'error_code_boost', v)}
              />
              <ParameterSlider
                label={t('scoring.params.boost.source_count')}
                value={config.boost.source_count_bonus}
                min={0}
                max={0.5}
                step={0.05}
                description={t('scoring.params.boost.source_count_desc')}
                onChange={(v) => updateConfig('boost', 'source_count_bonus', v)}
              />
            </ConfigSection>

            {/* Confidence Thresholds */}
            <ConfigSection
              title={t('scoring.sections.confidence')}
              icon={<CheckCircle size={20} />}
            >
              <ParameterSlider
                label={t('scoring.params.confidence.high')}
                value={config.confidence.high_threshold}
                min={0.5}
                max={1.0}
                step={0.05}
                description={t('scoring.params.confidence.high_desc')}
                onChange={(v) => updateConfig('confidence', 'high_threshold', v)}
              />
              <ParameterSlider
                label={t('scoring.params.confidence.medium')}
                value={config.confidence.medium_threshold}
                min={0.3}
                max={0.8}
                step={0.05}
                description={t('scoring.params.confidence.medium_desc')}
                onChange={(v) => updateConfig('confidence', 'medium_threshold', v)}
              />
              <ParameterSlider
                label={t('scoring.params.confidence.low')}
                value={config.confidence.low_threshold}
                min={0.1}
                max={0.5}
                step={0.05}
                description={t('scoring.params.confidence.low_desc')}
                onChange={(v) => updateConfig('confidence', 'low_threshold', v)}
              />
            </ConfigSection>

            {/* Reset Button */}
            <div className="scoring-reset-section">
              <button
                className="scoring-btn scoring-btn--danger"
                onClick={handleReset}
                disabled={saving}
              >
                <RotateCcw size={16} />
                {t('scoring.resetToDefaults')}
              </button>
              <p className="scoring-reset-description">
                {t('scoring.resetDescription')}
              </p>
            </div>
          </div>
        )}

        {/* Simulation Tab */}
        {activeTab === 'simulate' && (
          <div className="scoring-simulate">
            <div className="scoring-simulate-input">
              <h3>{t('scoring.simulate.title')}</h3>
              <p className="scoring-simulate-description">
                {t('scoring.simulate.description')}
              </p>
              <div className="scoring-simulate-form">
                <input
                  type="text"
                  value={simulateQuery}
                  onChange={(e) => setSimulateQuery(e.target.value)}
                  placeholder={t('scoring.simulate.placeholder')}
                  className="scoring-simulate-query"
                  onKeyDown={(e) => e.key === 'Enter' && handleSimulate()}
                />
                <button
                  className="scoring-btn scoring-btn--primary"
                  onClick={handleSimulate}
                  disabled={simulating || !simulateQuery.trim()}
                >
                  {simulating ? (
                    <Loader2 size={16} className="spinning" />
                  ) : (
                    <Play size={16} />
                  )}
                  {t('scoring.simulate.run')}
                </button>
              </div>
            </div>

            {simulationResult && (
              <div className="scoring-simulate-results">
                <h4>{t('scoring.simulate.results')}</h4>

                {/* Steps */}
                <div className="scoring-simulate-steps">
                  <h5>{t('scoring.simulate.steps')}</h5>
                  {simulationResult.steps.map((step, i) => (
                    <div key={i} className="scoring-simulate-step">
                      <div className="scoring-step-header">
                        <span className="scoring-step-number">{i + 1}</span>
                        <span className="scoring-step-name">{step.name}</span>
                        <span className="scoring-step-time">{step.duration_ms}ms</span>
                      </div>
                      <p className="scoring-step-description">{step.description}</p>
                      <div className="scoring-step-counts">
                        <span>In: {step.input_count}</span>
                        <span>Out: {step.output_count}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Results */}
                <div className="scoring-simulate-docs">
                  <h5>{t('scoring.simulate.topResults')}</h5>
                  <table className="scoring-results-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>{t('scoring.simulate.docTitle')}</th>
                        <th>{t('scoring.simulate.finalScore')}</th>
                        <th>{t('scoring.simulate.vectorScore')}</th>
                        <th>{t('scoring.simulate.bm25Score')}</th>
                        <th>{t('scoring.simulate.boost')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulationResult.final_results.slice(0, 10).map((doc, i) => (
                        <tr key={doc.doc_id}>
                          <td>{i + 1}</td>
                          <td className="scoring-doc-title" title={doc.title}>
                            {doc.title.length > 50 ? doc.title.slice(0, 47) + '...' : doc.title}
                          </td>
                          <td className="scoring-score scoring-score--final">
                            {doc.final_score.toFixed(4)}
                          </td>
                          <td className="scoring-score">{doc.vector_score.toFixed(4)}</td>
                          <td className="scoring-score">{doc.bm25_score.toFixed(4)}</td>
                          <td className="scoring-score">×{doc.boost_applied.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="scoring-simulate-summary">
                  <span className="scoring-total-time">
                    {t('scoring.simulate.totalTime')}: {simulationResult.total_duration_ms}ms
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <div className="scoring-history">
            <div className="scoring-history-header">
              <h3>{t('scoring.history.title')}</h3>
              <button
                className="scoring-btn scoring-btn--secondary"
                onClick={fetchHistory}
                disabled={historyLoading}
              >
                <RefreshCw size={16} className={historyLoading ? 'spinning' : ''} />
                {t('common.refresh')}
              </button>
            </div>

            {historyLoading ? (
              <div className="scoring-history-loading">
                <Loader2 className="spinning" size={24} />
                <span>{t('common.loading')}</span>
              </div>
            ) : history.length === 0 ? (
              <div className="scoring-history-empty">
                <History size={48} />
                <p>{t('scoring.history.empty')}</p>
              </div>
            ) : (
              <div className="scoring-history-list">
                {history.map((entry) => (
                  <div key={entry.id} className="scoring-history-item">
                    <div className="scoring-history-info">
                      <div className="scoring-history-meta">
                        <span className="scoring-history-date">
                          <Clock size={14} />
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                        <span className="scoring-history-user">
                          <User size={14} />
                          {entry.user_id || 'System'}
                        </span>
                      </div>
                      {entry.reason && (
                        <p className="scoring-history-reason">{entry.reason}</p>
                      )}
                    </div>
                    <button
                      className="scoring-btn scoring-btn--secondary"
                      onClick={() => handleRollback(entry.id)}
                      disabled={saving}
                    >
                      <RotateCcw size={14} />
                      {t('scoring.history.rollback')}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
};

export default AdminScoringPage;
