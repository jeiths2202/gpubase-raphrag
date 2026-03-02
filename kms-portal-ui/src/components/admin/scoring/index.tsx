/**
 * Admin Scoring Tab Component
 *
 * RAG Scoring Configuration Management as Admin Dashboard Tab
 * - View/Edit scoring parameters (RRF, BM25, Boost, Confidence)
 * - Real-time simulation with test queries
 * - Configuration history and rollback
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
import { useTranslation } from '../../../hooks/useTranslation';
import './ScoringTab.css';

// Types - must match backend scoring_config.py exactly
interface RRFConfig {
  k: number;
  neo4j_weight: number;  // Vector search weight
  postgres_weight: number;  // BM25 search weight
}

interface BM25Config {
  k1: number;
  b: number;
  min_score_threshold?: number;
  max_feature_lines?: number;
}

interface BoostConfig {
  title_match_boost: number;
  exact_phrase_boost: number;
  error_code_boost: number;
  source_count_bonus: number;
  title_match_enabled?: boolean;
  error_code_enabled?: boolean;
}

interface ConfidenceConfig {
  high_threshold: number;
  medium_threshold: number;
  low_threshold: number;
  score_high_threshold?: number;
  score_medium_threshold?: number;
  score_low_threshold?: number;
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

// Sub-tab configuration
type SubTabId = 'config' | 'simulate' | 'history';

const SUB_TABS = [
  { id: 'config' as SubTabId, labelKey: 'scoring.tabs.config', icon: <Sliders size={16} /> },
  { id: 'simulate' as SubTabId, labelKey: 'scoring.tabs.simulate', icon: <TestTube size={16} /> },
  { id: 'history' as SubTabId, labelKey: 'scoring.tabs.history', icon: <History size={16} /> },
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
  // Defensive check for undefined values
  const safeValue = value ?? min;
  const percentage = ((safeValue - min) / (max - min)) * 100;

  return (
    <div className="scoring-tab-param-slider">
      <div className="scoring-tab-param-header">
        <label className="scoring-tab-param-label">{label}</label>
        <span className="scoring-tab-param-value">
          {safeValue.toFixed(step < 1 ? 2 : 0)}{unit}
        </span>
      </div>
      {description && (
        <p className="scoring-tab-param-description">{description}</p>
      )}
      <div className="scoring-tab-slider-container">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={safeValue}
          onChange={(e) => onChange(parseFloat(e.target.value))}
          className="scoring-tab-slider"
          style={{
            background: `linear-gradient(to right, var(--color-primary) 0%, var(--color-primary) ${percentage}%, var(--color-border) ${percentage}%, var(--color-border) 100%)`,
          }}
        />
        <div className="scoring-tab-slider-range">
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
    <div className={`scoring-tab-config-section ${expanded ? 'expanded' : 'collapsed'}`}>
      <button
        className="scoring-tab-section-header"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="scoring-tab-section-title">
          {icon}
          <span>{title}</span>
        </div>
        {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {expanded && (
        <div className="scoring-tab-section-content">
          {children}
        </div>
      )}
    </div>
  );
};

// Main Scoring Tab Component
export const ScoringTab: React.FC = () => {
  const { t } = useTranslation();
  const [activeSubTab, setActiveSubTab] = useState<SubTabId>('config');
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
      setError(t('scoring.errors.loadFailed') || 'Failed to load configuration');
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
      setSuccess(t('scoring.success.saved') || 'Configuration saved');

      fetchHistory();
    } catch (err) {
      console.error('Failed to save config:', err);
      setError(t('scoring.errors.saveFailed') || 'Failed to save configuration');
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
      setSuccess(t('scoring.success.reset') || 'Reset to defaults');
    } catch (err) {
      console.error('Failed to reset config:', err);
      setError(t('scoring.errors.resetFailed') || 'Failed to reset configuration');
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
      setSuccess(t('scoring.success.rollback') || 'Rolled back successfully');
      fetchHistory();
    } catch (err) {
      console.error('Failed to rollback config:', err);
      setError(t('scoring.errors.rollbackFailed') || 'Failed to rollback');
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
      setError(t('scoring.errors.simulateFailed') || 'Simulation failed');
    } finally {
      setSimulating(false);
    }
  };

  // Check if config has changes
  const hasChanges = config && originalConfig &&
    JSON.stringify(config) !== JSON.stringify(originalConfig);

  // Update nested config value
  const updateConfig = (
    section: 'rrf' | 'bm25' | 'boost' | 'confidence',
    key: string,
    value: number
  ) => {
    if (!config) return;
    const currentSection = config[section] as unknown as Record<string, unknown>;
    setConfig({
      ...config,
      [section]: {
        ...currentSection,
        [key]: value,
      },
    } as ScoringConfig);
  };

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  useEffect(() => {
    if (activeSubTab === 'history') {
      fetchHistory();
    }
  }, [activeSubTab, fetchHistory]);

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
      <div className="scoring-tab-loading">
        <Loader2 className="spinning" size={32} />
        <span>Loading scoring configuration...</span>
      </div>
    );
  }

  // Error state (no config)
  if (error && !config) {
    return (
      <div className="scoring-tab-error">
        <AlertTriangle size={32} />
        <h3>Error Loading Configuration</h3>
        <p>{error}</p>
        <button onClick={fetchConfig} className="scoring-tab-btn scoring-tab-btn--primary">
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="scoring-tab-content">
      {/* Header */}
      <div className="scoring-tab-header">
        <div className="scoring-tab-header-info">
          <h3>
            <Settings size={20} />
            RAG Scoring Configuration
          </h3>
          <span className={`scoring-tab-source scoring-tab-source--${source}`}>
            {source}
          </span>
        </div>
        <div className="scoring-tab-header-actions">
          {hasChanges && (
            <button
              className="scoring-tab-btn scoring-tab-btn--secondary"
              onClick={() => setConfig(originalConfig)}
              disabled={saving}
            >
              <RotateCcw size={14} />
              Discard
            </button>
          )}
          <button
            className="scoring-tab-btn scoring-tab-btn--primary"
            onClick={handleSave}
            disabled={saving || !hasChanges}
          >
            {saving ? <Loader2 size={14} className="spinning" /> : <Save size={14} />}
            Save
          </button>
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="scoring-tab-alert scoring-tab-alert--error">
          <AlertTriangle size={14} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="scoring-tab-alert scoring-tab-alert--success">
          <CheckCircle size={14} />
          <span>{success}</span>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="scoring-tab-alert scoring-tab-alert--warning">
          <Info size={14} />
          <div>
            {warnings.map((w, i) => (
              <p key={i}>{w}</p>
            ))}
          </div>
        </div>
      )}

      {/* Sub-tabs */}
      <nav className="scoring-tab-subtabs">
        {SUB_TABS.map((tab) => (
          <button
            key={tab.id}
            className={`scoring-tab-subtab ${activeSubTab === tab.id ? 'scoring-tab-subtab--active' : ''}`}
            onClick={() => setActiveSubTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.id === 'config' ? 'Config' : tab.id === 'simulate' ? 'Simulate' : 'History'}</span>
          </button>
        ))}
      </nav>

      {/* Sub-tab Content */}
      <div className="scoring-tab-main">
        {/* Configuration Sub-tab */}
        {activeSubTab === 'config' && config && (
          <div className="scoring-tab-config-grid">
            {/* RRF Configuration */}
            <ConfigSection
              title="RRF (Reciprocal Rank Fusion)"
              icon={<GitCompare size={18} />}
            >
              <ParameterSlider
                label="K Parameter"
                value={config.rrf.k}
                min={1}
                max={100}
                step={1}
                description="Smoothing constant for RRF ranking"
                onChange={(v) => updateConfig('rrf', 'k', v)}
              />
              <ParameterSlider
                label="Neo4j (Vector) Weight"
                value={config.rrf.neo4j_weight}
                min={0}
                max={3}
                step={0.1}
                description="Weight for Neo4j vector similarity scores"
                onChange={(v) => updateConfig('rrf', 'neo4j_weight', v)}
              />
              <ParameterSlider
                label="PostgreSQL (BM25) Weight"
                value={config.rrf.postgres_weight}
                min={0}
                max={3}
                step={0.1}
                description="Weight for PostgreSQL BM25 keyword scores"
                onChange={(v) => updateConfig('rrf', 'postgres_weight', v)}
              />
            </ConfigSection>

            {/* BM25 Configuration */}
            <ConfigSection
              title="BM25 Parameters"
              icon={<Search size={18} />}
            >
              <ParameterSlider
                label="k1 (Term Frequency)"
                value={config.bm25.k1}
                min={0.5}
                max={3.0}
                step={0.1}
                description="Controls term frequency saturation"
                onChange={(v) => updateConfig('bm25', 'k1', v)}
              />
              <ParameterSlider
                label="b (Length Normalization)"
                value={config.bm25.b}
                min={0}
                max={1}
                step={0.05}
                description="Document length normalization factor"
                onChange={(v) => updateConfig('bm25', 'b', v)}
              />
            </ConfigSection>

            {/* Boost Configuration */}
            <ConfigSection
              title="Score Boosts"
              icon={<Sliders size={18} />}
            >
              <ParameterSlider
                label="Title Match Boost"
                value={config.boost.title_match_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description="Boost for title keyword matches"
                onChange={(v) => updateConfig('boost', 'title_match_boost', v)}
              />
              <ParameterSlider
                label="Exact Phrase Boost"
                value={config.boost.exact_phrase_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description="Boost for exact phrase matches"
                onChange={(v) => updateConfig('boost', 'exact_phrase_boost', v)}
              />
              <ParameterSlider
                label="Error Code Boost"
                value={config.boost.error_code_boost}
                min={1.0}
                max={3.0}
                step={0.1}
                description="Boost for error code matches"
                onChange={(v) => updateConfig('boost', 'error_code_boost', v)}
              />
              <ParameterSlider
                label="Source Count Bonus"
                value={config.boost.source_count_bonus}
                min={0}
                max={0.5}
                step={0.05}
                description="Bonus per additional source"
                onChange={(v) => updateConfig('boost', 'source_count_bonus', v)}
              />
            </ConfigSection>

            {/* Confidence Thresholds */}
            <ConfigSection
              title="Confidence Thresholds"
              icon={<CheckCircle size={18} />}
            >
              <ParameterSlider
                label="High Confidence"
                value={config.confidence.high_threshold}
                min={0.5}
                max={1.0}
                step={0.05}
                description="Threshold for high confidence answers"
                onChange={(v) => updateConfig('confidence', 'high_threshold', v)}
              />
              <ParameterSlider
                label="Medium Confidence"
                value={config.confidence.medium_threshold}
                min={0.3}
                max={0.8}
                step={0.05}
                description="Threshold for medium confidence answers"
                onChange={(v) => updateConfig('confidence', 'medium_threshold', v)}
              />
              <ParameterSlider
                label="Low Confidence"
                value={config.confidence.low_threshold}
                min={0.1}
                max={0.5}
                step={0.05}
                description="Threshold for low confidence answers"
                onChange={(v) => updateConfig('confidence', 'low_threshold', v)}
              />
            </ConfigSection>

            {/* Reset Button */}
            <div className="scoring-tab-reset-section">
              <button
                className="scoring-tab-btn scoring-tab-btn--danger"
                onClick={handleReset}
                disabled={saving}
              >
                <RotateCcw size={14} />
                Reset to Defaults
              </button>
              <p className="scoring-tab-reset-description">
                Reset all parameters to environment defaults
              </p>
            </div>
          </div>
        )}

        {/* Simulation Sub-tab */}
        {activeSubTab === 'simulate' && (
          <div className="scoring-tab-simulate">
            <div className="scoring-tab-simulate-input">
              <h4>Test Query Simulation</h4>
              <p className="scoring-tab-simulate-description">
                Enter a query to see how the current scoring configuration affects results
              </p>
              <div className="scoring-tab-simulate-form">
                <input
                  type="text"
                  value={simulateQuery}
                  onChange={(e) => setSimulateQuery(e.target.value)}
                  placeholder="Enter test query..."
                  className="scoring-tab-simulate-query"
                  onKeyDown={(e) => e.key === 'Enter' && handleSimulate()}
                />
                <button
                  className="scoring-tab-btn scoring-tab-btn--primary"
                  onClick={handleSimulate}
                  disabled={simulating || !simulateQuery.trim()}
                >
                  {simulating ? (
                    <Loader2 size={14} className="spinning" />
                  ) : (
                    <Play size={14} />
                  )}
                  Run
                </button>
              </div>
            </div>

            {simulationResult && (
              <div className="scoring-tab-simulate-results">
                <h4>Simulation Results</h4>

                {/* Steps */}
                <div className="scoring-tab-simulate-steps">
                  <h5>Processing Steps</h5>
                  {simulationResult.steps.map((step, i) => (
                    <div key={i} className="scoring-tab-simulate-step">
                      <div className="scoring-tab-step-header">
                        <span className="scoring-tab-step-number">{i + 1}</span>
                        <span className="scoring-tab-step-name">{step.name}</span>
                        <span className="scoring-tab-step-time">{step.duration_ms}ms</span>
                      </div>
                      <p className="scoring-tab-step-description">{step.description}</p>
                      <div className="scoring-tab-step-counts">
                        <span>In: {step.input_count}</span>
                        <span>Out: {step.output_count}</span>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Results */}
                <div className="scoring-tab-simulate-docs">
                  <h5>Top Results</h5>
                  <table className="scoring-tab-results-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Title</th>
                        <th>Final</th>
                        <th>Vector</th>
                        <th>BM25</th>
                        <th>Boost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulationResult.final_results.slice(0, 10).map((doc, i) => (
                        <tr key={doc.doc_id}>
                          <td>{i + 1}</td>
                          <td className="scoring-tab-doc-title" title={doc.title}>
                            {doc.title.length > 40 ? doc.title.slice(0, 37) + '...' : doc.title}
                          </td>
                          <td className="scoring-tab-score scoring-tab-score--final">
                            {doc.final_score.toFixed(4)}
                          </td>
                          <td className="scoring-tab-score">{doc.vector_score.toFixed(4)}</td>
                          <td className="scoring-tab-score">{doc.bm25_score.toFixed(4)}</td>
                          <td className="scoring-tab-score">×{doc.boost_applied.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="scoring-tab-simulate-summary">
                  <span className="scoring-tab-total-time">
                    Total Time: {simulationResult.total_duration_ms}ms
                  </span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* History Sub-tab */}
        {activeSubTab === 'history' && (
          <div className="scoring-tab-history">
            <div className="scoring-tab-history-header">
              <h4>Configuration History</h4>
              <button
                className="scoring-tab-btn scoring-tab-btn--secondary"
                onClick={fetchHistory}
                disabled={historyLoading}
              >
                <RefreshCw size={14} className={historyLoading ? 'spinning' : ''} />
                Refresh
              </button>
            </div>

            {historyLoading ? (
              <div className="scoring-tab-history-loading">
                <Loader2 className="spinning" size={20} />
                <span>Loading history...</span>
              </div>
            ) : history.length === 0 ? (
              <div className="scoring-tab-history-empty">
                <History size={32} />
                <p>No configuration history available</p>
              </div>
            ) : (
              <div className="scoring-tab-history-list">
                {history.map((entry) => (
                  <div key={entry.id} className="scoring-tab-history-item">
                    <div className="scoring-tab-history-info">
                      <div className="scoring-tab-history-meta">
                        <span className="scoring-tab-history-date">
                          <Clock size={12} />
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                        <span className="scoring-tab-history-user">
                          <User size={12} />
                          {entry.user_id || 'System'}
                        </span>
                      </div>
                      {entry.reason && (
                        <p className="scoring-tab-history-reason">{entry.reason}</p>
                      )}
                    </div>
                    <button
                      className="scoring-tab-btn scoring-tab-btn--secondary"
                      onClick={() => handleRollback(entry.id)}
                      disabled={saving}
                    >
                      <RotateCcw size={12} />
                      Rollback
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default ScoringTab;
