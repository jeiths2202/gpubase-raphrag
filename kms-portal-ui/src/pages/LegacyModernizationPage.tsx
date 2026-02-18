/**
 * Legacy Modernization Page
 *
 * COBOL/JCL/MAP/ASM 레거시 코드 분석 인터페이스
 * - 소스 코드 입력/업로드
 * - 11-Agent 파이프라인 실시간 진행률
 * - 9종 보고서 조회
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  Play,
  Loader2,
  FileCode2,
  Activity,
  CheckCircle2,
  XCircle,
  FileText,
  ChevronRight,
  X,
  Upload,
  Code2,
  BarChart3,
  Clock,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { ModernizationAIAssistant } from '../components/ModernizationAI';
import {
  startAnalysis,
  getAnalysisStatus,
  getAnalysisResults,
  getReportList,
  getReport,
  getProducts,
} from '../api/legacy.api';
import type {
  AnalysisResponse,
  AnalysisStatus,
  AnalysisResults,
  ReportListItem,
  ReportDetail,
  PipelineStatus,
  LegacyAssetType,
  ProductFamilyInfo,
} from '../api/legacy.api';
import './LegacyModernizationPage.css';

// Pipeline step definitions
const PIPELINE_STEPS: { status: PipelineStatus; labelKey: string }[] = [
  { status: 'parsing', labelKey: 'legacy.pipeline.parsing' },
  { status: 'domain_analysis', labelKey: 'legacy.pipeline.domainAnalysis' },
  { status: 'knowledge_enrichment', labelKey: 'legacy.pipeline.knowledgeEnrichment' },
  { status: 'review', labelKey: 'legacy.pipeline.review' },
  { status: 'qa_check', labelKey: 'legacy.pipeline.qaCheck' },
  { status: 'e2e_validation', labelKey: 'legacy.pipeline.e2eValidation' },
  { status: 'risk_assessment', labelKey: 'legacy.pipeline.riskAssessment' },
  { status: 'competitor_analysis', labelKey: 'legacy.pipeline.competitorAnalysis' },
  { status: 'report_generation', labelKey: 'legacy.pipeline.reportGeneration' },
];

// Detect language from file extension
function detectLanguage(fileName: string): LegacyAssetType {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (['cob', 'cbl', 'cobol'].includes(ext)) return 'cobol';
  if (['jcl', 'proc'].includes(ext)) return 'jcl';
  if (['map', 'bms'].includes(ext)) return 'map';
  if (['asm', 's'].includes(ext)) return 'asm';
  return 'cobol';
}

// Get step state relative to current pipeline status
function getStepState(
  step: PipelineStatus,
  current: PipelineStatus
): 'pending' | 'active' | 'completed' | 'failed' {
  if (current === 'failed') {
    const idx = PIPELINE_STEPS.findIndex((s) => s.status === step);
    const curIdx = PIPELINE_STEPS.findIndex((s) => s.status === current);
    if (idx < curIdx) return 'completed';
    if (idx === curIdx) return 'failed';
    return 'pending';
  }
  if (current === 'completed') return 'completed';

  const order = ['pending', ...PIPELINE_STEPS.map((s) => s.status), 'completed'];
  const stepIdx = order.indexOf(step);
  const curIdx = order.indexOf(current);

  if (stepIdx < curIdx) return 'completed';
  if (stepIdx === curIdx) return 'active';
  return 'pending';
}

export const LegacyModernizationPage: React.FC = () => {
  const { t } = useTranslation();

  // Source code state
  const [fileName, setFileName] = useState('SAMPLE.COB');
  const [sourceCode, setSourceCode] = useState('');
  const [vendor, setVendor] = useState('openframe');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Product/version selector state
  const [productFamilies, setProductFamilies] = useState<ProductFamilyInfo[]>([]);
  const [selectedFamily, setSelectedFamily] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [selectedVersion, setSelectedVersion] = useState('');

  // Analysis state
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>('pending');
  const [progressPercent, setProgressPercent] = useState(0);
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Results state
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<ReportDetail | null>(null);
  const [workspace, setWorkspace] = useState<AnalysisResults['workspace'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Polling ref
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup polling
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, []);

  // Load products on mount
  useEffect(() => {
    getProducts(undefined, 'en')
      .then((res) => setProductFamilies(res.families))
      .catch(() => {});
  }, []);

  // Poll for status updates
  const startPolling = useCallback(
    (id: string) => {
      if (pollingRef.current) clearInterval(pollingRef.current);

      pollingRef.current = setInterval(async () => {
        try {
          const status: AnalysisStatus = await getAnalysisStatus(id);
          setPipelineStatus(status.status);
          setProgressPercent(status.progress_percent);
          setCurrentAgent(status.current_agent);
          setElapsedSeconds(status.elapsed_seconds);

          if (status.status === 'completed' || status.status === 'failed') {
            if (pollingRef.current) clearInterval(pollingRef.current);
            setIsAnalyzing(false);

            if (status.status === 'completed') {
              // Fetch results
              const [results, reportList] = await Promise.all([
                getAnalysisResults(id),
                getReportList(id),
              ]);
              setWorkspace(results.workspace);
              setReports(reportList.reports || []);
            }
          }
        } catch {
          // Silent retry
        }
      }, 3000);
    },
    []
  );

  // Start analysis
  const handleAnalyze = useCallback(async () => {
    if (!sourceCode.trim()) return;

    setError(null);
    setIsAnalyzing(true);
    setPipelineStatus('pending');
    setProgressPercent(0);
    setReports([]);
    setSelectedReport(null);
    setWorkspace(null);

    try {
      const response: AnalysisResponse = await startAnalysis({
        file_name: fileName,
        source_code: sourceCode,
        vendors: [vendor],
        ...(selectedProduct && selectedVersion
          ? { target_product: selectedProduct, target_version: selectedVersion }
          : {}),
      });

      setAnalysisId(response.analysis_id);
      setPipelineStatus(response.status as PipelineStatus);
      startPolling(response.analysis_id);
    } catch (err: unknown) {
      setIsAnalyzing(false);
      setError(
        err instanceof Error ? err.message : t('legacy.errors.analyzeFailed')
      );
    }
  }, [sourceCode, fileName, vendor, startPolling, t]);

  // Handle file upload
  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      setFileName(file.name);
      const reader = new FileReader();
      reader.onload = (ev) => {
        setSourceCode((ev.target?.result as string) || '');
      };
      reader.readAsText(file);
    },
    []
  );

  // View report detail
  const handleViewReport = useCallback(
    async (reportType: string) => {
      if (!analysisId) return;
      try {
        const detail = await getReport(analysisId, reportType as any);
        setSelectedReport(detail);
      } catch {
        // Silently handle
      }
    },
    [analysisId]
  );

  const detectedLang = detectLanguage(fileName);
  const lineCount = sourceCode.split('\n').length;
  const charCount = sourceCode.length;

  return (
    <div className="legacy-mod">
      {/* Header */}
      <div className="legacy-mod-header">
        <div className="legacy-mod-header-title">
          <h1>{t('legacy.title')}</h1>
          <p className="legacy-mod-header-subtitle">
            {t('legacy.subtitle')}
          </p>
        </div>
        <div className="legacy-mod-header-actions">
          {analysisId && (
            <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)' }}>
              ID: {analysisId.slice(0, 8)}...
            </span>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="legacy-mod-content">
        {/* Left: Code Editor */}
        <div className="legacy-mod-left">
          {/* Editor */}
          <div className="legacy-mod-editor-section">
            <div className="legacy-mod-editor-header">
              <div className="legacy-mod-editor-header-left">
                <FileCode2 size={16} />
                <input
                  className="legacy-mod-filename-input"
                  value={fileName}
                  onChange={(e) => setFileName(e.target.value)}
                  placeholder="FILENAME.COB"
                />
                <span className="legacy-mod-lang-badge">
                  <Code2 size={10} />
                  {detectedLang.toUpperCase()}
                </span>
              </div>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={14} />
                {t('legacy.upload')}
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".cob,.cbl,.cobol,.jcl,.proc,.map,.bms,.asm,.s,.txt"
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
            </div>

            <textarea
              className="legacy-mod-editor-textarea"
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
              placeholder={t('legacy.codePlaceholder')}
              spellCheck={false}
            />

            <div className="legacy-mod-editor-footer">
              <span>
                {lineCount} {t('legacy.lines')} &middot; {charCount} {t('legacy.chars')}
              </span>
              <span>{detectedLang.toUpperCase()}</span>
            </div>
          </div>

          {/* Options bar */}
          <div className="legacy-mod-options">
            <label style={{ fontSize: '0.8125rem', fontWeight: 500 }}>
              {t('legacy.targetVendor')}:
            </label>
            <select
              className="legacy-mod-vendor-select"
              value={vendor}
              onChange={(e) => setVendor(e.target.value)}
            >
              <option value="openframe">OpenFrame</option>
              <option value="microfocus">Micro Focus</option>
              <option value="ibm">IBM zOS</option>
            </select>

            {vendor === 'openframe' && productFamilies.length > 0 && (
              <>
                <label style={{ fontSize: '0.8125rem', fontWeight: 500, marginLeft: '0.5rem' }}>
                  {t('legacy.targetProduct')}:
                </label>
                <select
                  className="legacy-mod-vendor-select"
                  value={selectedFamily}
                  onChange={(e) => {
                    setSelectedFamily(e.target.value);
                    setSelectedProduct('');
                    setSelectedVersion('');
                  }}
                >
                  <option value="">{t('legacy.selectFamily')}</option>
                  {productFamilies.map((f) => (
                    <option key={f.family} value={f.family}>
                      {f.display_name}
                    </option>
                  ))}
                </select>

                {selectedFamily && (() => {
                  const family = productFamilies.find((f) => f.family === selectedFamily);
                  if (!family) return null;
                  // unique product ids within this family
                  const productIds = [...new Set(family.versions.map((v) => v.product))];
                  return (
                    <select
                      className="legacy-mod-vendor-select"
                      value={selectedProduct}
                      onChange={(e) => {
                        setSelectedProduct(e.target.value);
                        setSelectedVersion('');
                      }}
                    >
                      <option value="">{t('legacy.selectProduct')}</option>
                      {productIds.map((pid) => {
                        const pv = family.versions.find((v) => v.product === pid);
                        return (
                          <option key={pid} value={pid}>
                            {pv?.display_name?.replace(/ \d+\.\d+$/, '') || pid}
                          </option>
                        );
                      })}
                    </select>
                  );
                })()}

                {selectedProduct && (() => {
                  const family = productFamilies.find((f) => f.family === selectedFamily);
                  if (!family) return null;
                  const versions = family.versions.filter((v) => v.product === selectedProduct);
                  return (
                    <select
                      className="legacy-mod-vendor-select"
                      value={selectedVersion}
                      onChange={(e) => setSelectedVersion(e.target.value)}
                    >
                      <option value="">{t('legacy.selectVersion')}</option>
                      {versions.map((v) => (
                        <option key={v.version} value={v.version}>
                          v{v.version}
                        </option>
                      ))}
                    </select>
                  );
                })()}
              </>
            )}

            <button
              className="legacy-mod-analyze-btn"
              onClick={handleAnalyze}
              disabled={isAnalyzing || !sourceCode.trim()}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 size={16} className="legacy-mod-spinner" />
                  {t('legacy.analyzing')}
                </>
              ) : (
                <>
                  <Play size={16} />
                  {t('legacy.startAnalysis')}
                </>
              )}
            </button>
          </div>

          {/* Error display */}
          {error && (
            <div
              style={{
                padding: '0.75rem 1rem',
                background: 'var(--color-error-light, rgba(239, 68, 68, 0.1))',
                border: '1px solid var(--color-error, #ef4444)',
                borderRadius: 'var(--radius-sm, 6px)',
                color: 'var(--color-error)',
                fontSize: '0.8125rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <XCircle size={16} />
              {error}
            </div>
          )}
        </div>

        {/* Right: Pipeline & Results */}
        <div className="legacy-mod-right">
          {/* Pipeline Progress */}
          <div className="legacy-mod-pipeline">
            <div className="legacy-mod-pipeline-title">
              <Activity size={16} />
              {t('legacy.pipeline.title')}
            </div>

            <div className="legacy-mod-pipeline-steps">
              {PIPELINE_STEPS.map((step) => {
                const state = getStepState(step.status, pipelineStatus);
                return (
                  <div
                    key={step.status}
                    className={`legacy-mod-step legacy-mod-step--${state}`}
                  >
                    <span className="legacy-mod-step-icon">
                      {state === 'completed' && <CheckCircle2 size={16} />}
                      {state === 'active' && <span className="active-dot" />}
                      {state === 'failed' && <XCircle size={16} />}
                      {state === 'pending' && <span className="pending-dot" />}
                    </span>
                    <span>{t(step.labelKey)}</span>
                  </div>
                );
              })}
            </div>

            {/* Progress bar */}
            {(isAnalyzing || pipelineStatus === 'completed') && (
              <div className="legacy-mod-progress">
                <div className="legacy-mod-progress-bar-bg">
                  <div
                    className="legacy-mod-progress-bar-fill"
                    style={{
                      width: `${pipelineStatus === 'completed' ? 100 : progressPercent}%`,
                    }}
                  />
                </div>
                <div className="legacy-mod-progress-text">
                  <span>
                    {pipelineStatus === 'completed'
                      ? '100%'
                      : `${Math.round(progressPercent)}%`}
                    {currentAgent && isAnalyzing && (
                      <span style={{ marginLeft: '0.5rem', opacity: 0.7 }}>
                        ({currentAgent})
                      </span>
                    )}
                  </span>
                  <span>
                    <Clock size={10} style={{ display: 'inline', verticalAlign: 'middle' }} />{' '}
                    {Math.round(elapsedSeconds)}s
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Results */}
          <div className="legacy-mod-results">
            <div className="legacy-mod-results-title">
              <BarChart3 size={16} />
              {t('legacy.results.title')}
            </div>

            {/* Workspace info */}
            {workspace && (
              <div className="legacy-mod-workspace">
                <div className="legacy-mod-workspace-item">
                  <span className="legacy-mod-workspace-label">
                    {t('legacy.results.assetType')}
                  </span>
                  <span className="legacy-mod-workspace-value">
                    {workspace.asset_type?.toUpperCase()}
                  </span>
                </div>
                <div className="legacy-mod-workspace-item">
                  <span className="legacy-mod-workspace-label">
                    {t('legacy.results.loc')}
                  </span>
                  <span className="legacy-mod-workspace-value">
                    {workspace.loc_count}
                  </span>
                </div>
                <div className="legacy-mod-workspace-item">
                  <span className="legacy-mod-workspace-label">
                    {t('legacy.results.status')}
                  </span>
                  <span className="legacy-mod-workspace-value">
                    {workspace.pipeline_status}
                  </span>
                </div>
                <div className="legacy-mod-workspace-item">
                  <span className="legacy-mod-workspace-label">
                    {t('legacy.results.qaStatus')}
                  </span>
                  <span className="legacy-mod-workspace-value">
                    {workspace.qa_passed === null
                      ? '—'
                      : workspace.qa_passed
                      ? 'PASSED'
                      : 'FAILED'}
                  </span>
                </div>
              </div>
            )}

            {/* Report list */}
            {reports.length > 0 ? (
              reports.map((r) => (
                <div
                  key={r.report_type}
                  className="legacy-mod-report-item"
                  onClick={() => handleViewReport(r.report_type)}
                >
                  <FileText
                    size={16}
                    className="legacy-mod-report-item-icon"
                  />
                  <span className="legacy-mod-report-item-name">{r.title}</span>
                  <ChevronRight size={14} />
                </div>
              ))
            ) : (
              <div className="legacy-mod-empty">
                <FileText size={32} className="legacy-mod-empty-icon" />
                <p className="legacy-mod-empty-text">
                  {t('legacy.results.empty')}
                </p>
              </div>
            )}

            {/* Report detail */}
            {selectedReport && (
              <div className="legacy-mod-report-detail">
                <div className="legacy-mod-report-detail-header">
                  <h4>{selectedReport.title}</h4>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setSelectedReport(null)}
                  >
                    <X size={14} />
                  </button>
                </div>
                <div className="legacy-mod-report-detail-content">
                  {JSON.stringify(selectedReport.content, null, 2)}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Modernization AI Assistant */}
      <ModernizationAIAssistant
        analysisContext={analysisId ? {
          analysisId,
          fileName,
          assetType: detectLanguage(fileName),
          sourceCodeSnippet: sourceCode.slice(0, 2000),
          targetProduct: selectedProduct || undefined,
        } : undefined}
      />
    </div>
  );
};

export default LegacyModernizationPage;
