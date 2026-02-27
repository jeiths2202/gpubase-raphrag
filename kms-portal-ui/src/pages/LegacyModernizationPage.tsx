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
  X,
  Upload,
  Code2,
  Clock,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { ModernizationAIAssistant } from '../components/ModernizationAI';
import {
  startAnalysis,
  getAnalysisStatus,
  getProducts,
  startBatchAnalysis,
  getBatchResults,
  streamBatchEvents,
} from '../api/legacy.api';
import type {
  AnalysisResponse,
  AnalysisStatus,
  PipelineStatus,
  LegacyAssetType,
  ProductFamilyInfo,
  FileItem,
  BatchSummary,
  FileAnalysisResult,
  BatchSSEEvent,
} from '../api/legacy.api';
import BatchSummaryCard from '../components/ModernizationAI/BatchSummaryCard';
import FileAccordion from '../components/ModernizationAI/FileAccordion';
import AnalysisDataTable from '../components/ModernizationAI/AnalysisDataTable';
import './LegacyModernizationPage.css';

// Pipeline step definitions - matches backend PipelineStatus enum + AgentRole
const PIPELINE_STEPS: { status: PipelineStatus; labelKey: string; agentKey: string }[] = [
  { status: 'parsing', labelKey: 'legacy.pipeline.parsing', agentKey: 'legacy.pipeline.agents.domainExpert' },
  { status: 'knowledge_enrichment', labelKey: 'legacy.pipeline.knowledgeEnrichment', agentKey: 'legacy.pipeline.agents.legacyKnowledge' },
  { status: 'compatibility_analysis', labelKey: 'legacy.pipeline.compatibilityAnalysis', agentKey: 'legacy.pipeline.agents.competitorIntel' },
  { status: 'risk_assessment', labelKey: 'legacy.pipeline.riskAssessment', agentKey: 'legacy.pipeline.agents.riskIntel' },
  { status: 'reviewing', labelKey: 'legacy.pipeline.reviewing', agentKey: 'legacy.pipeline.agents.reviewer' },
  { status: 'qa_validation', labelKey: 'legacy.pipeline.qaValidation', agentKey: 'legacy.pipeline.agents.qa' },
  { status: 'e2e_testing', labelKey: 'legacy.pipeline.e2eTesting', agentKey: 'legacy.pipeline.agents.e2eTest' },
  { status: 'report_generation', labelKey: 'legacy.pipeline.reportGeneration', agentKey: 'legacy.pipeline.agents.reportGenerator' },
];

// XSP JCL statement prefixes (Fujitsu OSIV/XSP)
const XSP_PATTERNS = ['\\ JOB', '\\ EX ', '\\ FD ', '\\ JEND', '/EXPAN', '/ SET', '/ DEFEND'];

// Detect language from file extension + content heuristics
function detectLanguage(fileName: string, sourceContent?: string): LegacyAssetType {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  if (['cob', 'cbl', 'cobol'].includes(ext)) return 'cobol';
  if (['jcl', 'proc'].includes(ext)) return 'jcl';
  if (['map', 'bms'].includes(ext)) return 'map';
  if (['asm', 's'].includes(ext)) return 'asm';

  // Content-based detection when extension is ambiguous
  if (sourceContent) {
    const upper = sourceContent.slice(0, 1000).toUpperCase();
    // XSP JCL: \ JOB, \ EX, \ FD, /EXPAN, / SET, / DEFEND
    if (XSP_PATTERNS.some((pat) => upper.includes(pat))) return 'jcl';
    // MVS JCL: // JOB, // EXEC
    if (upper.trimStart().startsWith('//') && (upper.includes('JOB') || upper.includes('EXEC'))) return 'jcl';
    // COBOL
    if (upper.includes('IDENTIFICATION DIVISION') || upper.includes('PROCEDURE DIVISION')) return 'cobol';
    // MAP (BMS)
    if (upper.includes('DFHMSD') || upper.includes('DFHMDI')) return 'map';
    // ASM
    if (upper.includes(' CSECT') || upper.includes(' USING ')) return 'asm';
  }

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
  const [error, setError] = useState<string | null>(null);

  // Batch analysis state
  const [uploadedFiles, setUploadedFiles] = useState<FileItem[]>([]);
  const [_batchId, setBatchId] = useState<string | null>(null);
  const [batchSummary, setBatchSummary] = useState<BatchSummary | null>(null);
  const [fileResults, setFileResults] = useState<FileAnalysisResult[]>([]);
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [isBatchMode, setIsBatchMode] = useState(false);
  const batchEventSourceRef = useRef<EventSource | null>(null);

  // Data Table refresh trigger - increment when new analysis completes
  const [dataTableRefresh, setDataTableRefresh] = useState(0);

  // Polling ref
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup polling + batch SSE
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (batchEventSourceRef.current) batchEventSourceRef.current.close();
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
              // Refresh Data Table to show new persisted result
              setDataTableRefresh((prev) => prev + 1);
            }
          }
        } catch {
          // Silent retry
        }
      }, 3000);
    },
    []
  );

  // Batch SSE subscription
  const subscribeBatchSSE = useCallback((id: string) => {
    if (batchEventSourceRef.current) batchEventSourceRef.current.close();

    const es = streamBatchEvents(
      id,
      (event: BatchSSEEvent) => {
        if (event.event === 'file_completed') {
          setFileResults((prev) =>
            prev.map((f) =>
              f.file_name === event.data.file_name
                ? {
                    ...f,
                    status: 'completed' as const,
                    support_rate: event.data.support_rate ?? f.support_rate,
                    incompatible_count: event.data.incompatible_count ?? f.incompatible_count,
                  }
                : f
            )
          );
        } else if (event.event === 'file_failed') {
          setFileResults((prev) =>
            prev.map((f) =>
              f.file_name === event.data.file_name
                ? { ...f, status: 'failed' as const }
                : f
            )
          );
        } else if (event.event === 'batch_completed') {
          setIsAnalyzing(false);
          // Fetch full results
          getBatchResults(id).then((results) => {
            setBatchSummary(results.summary);
            setFileResults(results.file_results);
          }).catch(() => {});
          // Refresh Data Table
          setDataTableRefresh((prev) => prev + 1);
        }
      },
      () => {
        // On error, stop
        setIsAnalyzing(false);
      }
    );

    batchEventSourceRef.current = es;
  }, []);

  // Start analysis (single or batch)
  const handleAnalyze = useCallback(async () => {
    setError(null);
    setIsAnalyzing(true);
    setPipelineStatus('pending');
    setProgressPercent(0);
    setBatchSummary(null);
    setFileResults([]);

    const targetOpts = selectedProduct && selectedVersion
      ? { target_product: selectedProduct, target_version: selectedVersion }
      : {};

    try {
      if (isBatchMode && uploadedFiles.length > 1) {
        // Batch mode
        const response = await startBatchAnalysis({
          files: uploadedFiles,
          vendors: [vendor],
          ...targetOpts,
        });

        setBatchId(response.batch_id);
        // Initialize file results as in_progress
        setFileResults(
          uploadedFiles.map((f) => ({
            file_name: f.file_name,
            analysis_id: '',
            status: 'in_progress' as const,
            asset_type: detectLanguage(f.file_name, f.source_code),
            total_features: 0,
            supported_count: 0,
            incompatible_count: 0,
            support_rate: 0,
            risk_summary: {},
            incompatibility_report: null,
          }))
        );
        subscribeBatchSSE(response.batch_id);
      } else {
        // Single file mode
        if (!sourceCode.trim()) {
          setIsAnalyzing(false);
          return;
        }
        const response: AnalysisResponse = await startAnalysis({
          file_name: fileName,
          source_code: sourceCode,
          vendors: [vendor],
          ...targetOpts,
        });

        setAnalysisId(response.analysis_id);
        setPipelineStatus(response.status as PipelineStatus);
        startPolling(response.analysis_id);
      }
    } catch (err: unknown) {
      setIsAnalyzing(false);
      setError(
        err instanceof Error ? err.message : t('legacy.errors.analyzeFailed')
      );
    }
  }, [sourceCode, fileName, vendor, startPolling, t, isBatchMode, uploadedFiles, selectedProduct, selectedVersion, subscribeBatchSSE]);

  // Handle single file upload (existing)
  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;

      if (files.length === 1) {
        // Single file: set in editor
        const file = files[0];
        setFileName(file.name);
        const reader = new FileReader();
        reader.onload = (ev) => {
          setSourceCode((ev.target?.result as string) || '');
        };
        reader.readAsText(file);
        setUploadedFiles([]);
        setIsBatchMode(false);
      } else {
        // Multiple files: batch mode
        const filePromises = Array.from(files).slice(0, 10).map(
          (file) =>
            new Promise<FileItem>((resolve) => {
              const reader = new FileReader();
              reader.onload = (ev) => {
                resolve({
                  file_name: file.name,
                  source_code: (ev.target?.result as string) || '',
                });
              };
              reader.readAsText(file);
            })
        );
        Promise.all(filePromises).then((items) => {
          setUploadedFiles(items);
          setIsBatchMode(true);
          if (items.length > 0) {
            setFileName(items[0].file_name);
            setSourceCode(items[0].source_code);
          }
        });
      }
    },
    []
  );

  // Remove a file from batch
  const handleRemoveFile = useCallback((fileName: string) => {
    setUploadedFiles((prev) => {
      const next = prev.filter((f) => f.file_name !== fileName);
      if (next.length <= 1) setIsBatchMode(false);
      return next;
    });
  }, []);

  const detectedLang = detectLanguage(fileName, sourceCode);
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
                multiple
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
            </div>

            {/* Batch file list */}
            {isBatchMode && uploadedFiles.length > 1 && (
              <div className="legacy-mod-batch-files">
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', marginBottom: 6 }}>
                  {uploadedFiles.length} {t('legacy.batch.filesSelected')}
                  {' '}(Max: 10)
                  <button
                    style={{ marginLeft: 8, fontSize: '0.7rem', color: '#dc2626', background: 'none', border: 'none', cursor: 'pointer' }}
                    onClick={() => { setUploadedFiles([]); setIsBatchMode(false); }}
                  >
                    {t('legacy.batch.clearFiles')}
                  </button>
                </div>
                {uploadedFiles.map((f) => (
                  <div key={f.file_name} className="legacy-mod-batch-file-item">
                    <FileCode2 size={12} />
                    <span style={{ flex: 1, fontFamily: 'monospace', fontSize: '0.75rem' }}>{f.file_name}</span>
                    <span className="legacy-mod-lang-badge" style={{ fontSize: '0.625rem', padding: '1px 6px' }}>
                      {detectLanguage(f.file_name, f.source_code).toUpperCase()}
                    </span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)' }}>
                      {f.source_code.split('\n').length}L
                    </span>
                    <button
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', padding: '0 4px' }}
                      onClick={() => handleRemoveFile(f.file_name)}
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

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

            {vendor === 'openframe' && (
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
              disabled={isAnalyzing || (!sourceCode.trim() && uploadedFiles.length === 0)}
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
                // For active parsing step, show the real agent name from polling (e.g., "JCL Expert")
                const agentLabel =
                  state === 'active' && step.status === 'parsing' && currentAgent
                    ? currentAgent
                    : t(step.agentKey);
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
                    <span className="legacy-mod-step-label">
                      {t(step.labelKey)}
                      <span className="legacy-mod-step-agent">{agentLabel}</span>
                    </span>
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

          {/* Batch Results */}
          {isBatchMode && (batchSummary || fileResults.length > 0) && (
            <div className="legacy-mod-batch-results" style={{ marginBottom: 16 }}>
              {batchSummary && (
                <BatchSummaryCard
                  summary={batchSummary}
                  isLoading={isAnalyzing}
                />
              )}
              {fileResults.length > 0 && (
                <FileAccordion
                  fileResults={fileResults}
                  expandedFiles={expandedFiles}
                  onToggle={(fn) =>
                    setExpandedFiles((prev) => {
                      const next = new Set(prev);
                      if (next.has(fn)) next.delete(fn);
                      else next.add(fn);
                      return next;
                    })
                  }
                  onExpandAll={() =>
                    setExpandedFiles(new Set(fileResults.map((f) => f.file_name)))
                  }
                  onCollapseAll={() => setExpandedFiles(new Set())}
                />
              )}
            </div>
          )}

        </div>
      </div>

      {/* Data Table - Persisted Analysis Results */}
      <div className="legacy-mod-datatable-section">
        <AnalysisDataTable refreshTrigger={dataTableRefresh} />
      </div>

      {/* Modernization AI Assistant */}
      <ModernizationAIAssistant
        analysisContext={sourceCode.trim() ? {
          analysisId: analysisId || undefined,
          fileName,
          assetType: detectLanguage(fileName, sourceCode),
          sourceCodeSnippet: sourceCode.slice(0, 2000),
          sourceCodeFull: sourceCode,
          targetProduct: selectedProduct || undefined,
        } : (selectedProduct ? { targetProduct: selectedProduct } : undefined)}
      />
    </div>
  );
};

export default LegacyModernizationPage;
