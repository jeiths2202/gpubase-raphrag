/**
 * JCL Job Failure Diagnosis Page
 *
 * Upload a JOB output zip file, watch 5-agent pipeline progress via SSE,
 * and view/download the final HTML diagnosis report.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  Upload,
  FileArchive,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  FileText,
  ExternalLink,
  Download,
  RotateCcw,
  ChevronRight,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { streamDiagnosis, getReportUrl, type DiagnosisEvent } from '../api/jcl-diagnosis.api';
import './JCLDiagnosisPage.css';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DiagnosisPhase =
  | 'idle'
  | 'extracting'
  | 'classifying'
  | 'parsing'
  | 'diagnosing'
  | 'searching'
  | 'generating'
  | 'complete'
  | 'error';

interface ClassifiedFile {
  filename: string;
  type: string;
}

interface StepInfo {
  step_number: number;
  step_name: string;
  program: string;
  status: string;
  return_code?: number | string;
}

interface ErrorInfo {
  code: string;
  type: string;
  severity: string;
  failed_step: string;
  message: string;
}

interface SearchResult {
  source: string;
  code: string;
  confidence: number;
  description: string;
}

interface DiagnosisState {
  phase: DiagnosisPhase;
  diagnosisId: string | null;
  files: ClassifiedFile[];
  fileStats: Record<string, number>;
  jobName: string | null;
  totalSteps: number;
  steps: StepInfo[];
  error: ErrorInfo | null;
  searchResults: SearchResult[];
  reportText: string;
  reportData: unknown | null;
  severity: string | null;
  errorMessage: string | null;
}

const INITIAL_STATE: DiagnosisState = {
  phase: 'idle',
  diagnosisId: null,
  files: [],
  fileStats: {},
  jobName: null,
  totalSteps: 0,
  steps: [],
  error: null,
  searchResults: [],
  reportText: '',
  reportData: null,
  severity: null,
  errorMessage: null,
};

// ---------------------------------------------------------------------------
// Phase pipeline config
// ---------------------------------------------------------------------------

const PHASES: { key: DiagnosisPhase; labelKey: string; icon: React.ReactNode }[] = [
  { key: 'extracting', labelKey: 'jclDiagnosis.phaseExtract', icon: <FileArchive size={16} /> },
  { key: 'classifying', labelKey: 'jclDiagnosis.phaseClassify', icon: <FileText size={16} /> },
  { key: 'parsing', labelKey: 'jclDiagnosis.phaseParse', icon: <FileText size={16} /> },
  { key: 'diagnosing', labelKey: 'jclDiagnosis.phaseDiagnose', icon: <AlertTriangle size={16} /> },
  { key: 'searching', labelKey: 'jclDiagnosis.phaseSearch', icon: <Search size={16} /> },
  { key: 'generating', labelKey: 'jclDiagnosis.phaseReport', icon: <FileText size={16} /> },
];

const PHASE_ORDER: DiagnosisPhase[] = [
  'extracting', 'classifying', 'parsing', 'diagnosing', 'searching', 'generating',
];

function phaseIndex(p: DiagnosisPhase): number {
  const idx = PHASE_ORDER.indexOf(p);
  return idx >= 0 ? idx : -1;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const JCLDiagnosisPage: React.FC = () => {
  const { t } = useTranslation();

  // Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [language, setLanguage] = useState('ja');
  const [message, setMessage] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const reportAreaRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Diagnosis state
  const [state, setState] = useState<DiagnosisState>(INITIAL_STATE);

  const isRunning = state.phase !== 'idle' && state.phase !== 'complete' && state.phase !== 'error';

  // Auto-scroll report area
  useEffect(() => {
    if (reportAreaRef.current && state.reportText) {
      reportAreaRef.current.scrollTop = reportAreaRef.current.scrollHeight;
    }
  }, [state.reportText]);

  // ---------------------------------------------------------------------------
  // File handling
  // ---------------------------------------------------------------------------

  const handleFileSelect = useCallback((file: File) => {
    if (!file.name.endsWith('.zip')) return;
    setSelectedFile(file);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFileSelect(file);
    },
    [handleFileSelect],
  );

  // ---------------------------------------------------------------------------
  // SSE Event handler
  // ---------------------------------------------------------------------------

  const handleEvent = useCallback((event: DiagnosisEvent) => {
    const { type } = event;

    setState((prev) => {
      switch (type) {
        case 'file_extracted':
          return {
            ...prev,
            phase: 'extracting',
            diagnosisId: (event.diagnosis_id as string) || prev.diagnosisId,
          };

        case 'file_classified':
          return {
            ...prev,
            phase: 'classifying',
            files: (event.files as ClassifiedFile[]) || [],
            fileStats: {
              jcl: (event.jcl as number) || 0,
              proc: (event.proc as number) || 0,
              jesmsg: (event.jesmsg as number) || 0,
              sysmsg: (event.sysmsg as number) || 0,
              sysprint: (event.sysprint as number) || 0,
              unknown: (event.unknown as number) || 0,
            },
          };

        case 'jcl_parsed':
          return {
            ...prev,
            phase: 'parsing',
            jobName: (event.job_name as string) || null,
            totalSteps: (event.total_steps as number) || 0,
            steps: (event.steps as StepInfo[]) || [],
          };

        case 'step_flow':
          return {
            ...prev,
            phase: 'diagnosing',
            steps: (event.steps as StepInfo[]) || prev.steps,
          };

        case 'error_found':
          return {
            ...prev,
            phase: 'diagnosing',
            error: {
              code: (event.code as string) || '',
              type: (event.type as string) || '',
              severity: (event.severity as string) || '',
              failed_step: (event.failed_step as string) || '',
              message: (event.message as string) || '',
            },
            severity: (event.severity as string) || prev.severity,
          };

        case 'searching_knowledge':
          return { ...prev, phase: 'searching' };

        case 'search_result':
          return {
            ...prev,
            phase: 'searching',
            searchResults: [
              ...prev.searchResults,
              {
                source: (event.source as string) || '',
                code: (event.code as string) || '',
                confidence: (event.confidence as number) || 0,
                description: (event.description as string) || '',
              },
            ],
          };

        case 'generating_report':
          return { ...prev, phase: 'generating' };

        case 'llm_token':
          return {
            ...prev,
            phase: 'generating',
            reportText: prev.reportText + ((event.token as string) || ''),
          };

        case 'report_complete':
          return {
            ...prev,
            phase: 'complete',
            diagnosisId: (event.diagnosis_id as string) || prev.diagnosisId,
            reportData: event.report_data || null,
            severity: (event.severity as string) || prev.severity,
            jobName: (event.job_name as string) || prev.jobName,
          };

        case 'error':
          return {
            ...prev,
            phase: 'error',
            errorMessage: (event.message as string) || 'Unknown error',
            diagnosisId: (event.diagnosis_id as string) || prev.diagnosisId,
          };

        default:
          return prev;
      }
    });
  }, []);

  // ---------------------------------------------------------------------------
  // Start diagnosis
  // ---------------------------------------------------------------------------

  const handleAnalyze = useCallback(async () => {
    if (!selectedFile || isRunning) return;

    setState({ ...INITIAL_STATE, phase: 'extracting' });
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamDiagnosis(
        selectedFile,
        language,
        message || undefined,
        handleEvent,
        controller.signal,
      );
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      setState((prev) => ({
        ...prev,
        phase: 'error',
        errorMessage: (err as Error).message || 'Connection failed',
      }));
    }
  }, [selectedFile, language, message, isRunning, handleEvent]);

  // ---------------------------------------------------------------------------
  // Reset
  // ---------------------------------------------------------------------------

  const handleReset = useCallback(() => {
    abortRef.current?.abort();
    setState(INITIAL_STATE);
    setSelectedFile(null);
    setMessage('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  // ---------------------------------------------------------------------------
  // Report actions
  // ---------------------------------------------------------------------------

  const handleOpenReport = useCallback(() => {
    if (state.diagnosisId) {
      window.open(getReportUrl(state.diagnosisId), '_blank');
    }
  }, [state.diagnosisId]);

  const handleDownloadReport = useCallback(() => {
    if (state.diagnosisId) {
      const a = document.createElement('a');
      a.href = getReportUrl(state.diagnosisId);
      a.download = `jcl-diagnosis-${state.diagnosisId}.html`;
      a.click();
    }
  }, [state.diagnosisId]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const currentPhaseIdx = phaseIndex(state.phase);

  const getSeverityClass = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case 'CRITICAL': return 'severity-critical';
      case 'HIGH': return 'severity-high';
      case 'MEDIUM': return 'severity-medium';
      case 'LOW': return 'severity-low';
      default: return '';
    }
  };

  const getStepStatusClass = (status: string) => {
    const s = status?.toUpperCase();
    if (s === 'COMPLETED' || s === 'NORMAL' || s === 'WARNING') return 'step-completed';
    if (s?.startsWith('ABEND') || s === 'FAILED') return 'step-abend';
    if (s === 'SKIPPED' || s === 'NOT_RUN') return 'step-skipped';
    return '';
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="jcl-diagnosis-page">
      {/* Header */}
      <div className="jcl-header">
        <div className="jcl-header-left">
          <AlertTriangle size={24} className="jcl-header-icon" />
          <h1>{t('jclDiagnosis.title')}</h1>
        </div>
        {state.phase !== 'idle' && (
          <button className="jcl-btn jcl-btn-ghost" onClick={handleReset}>
            <RotateCcw size={16} />
            {t('jclDiagnosis.newDiagnosis')}
          </button>
        )}
      </div>

      {/* Zone 1: Upload */}
      {(state.phase === 'idle' || state.phase === 'error') && (
        <div className="jcl-upload-zone">
          <div
            className={`jcl-dropzone ${dragOver ? 'drag-over' : ''} ${selectedFile ? 'has-file' : ''}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              onChange={handleInputChange}
              style={{ display: 'none' }}
            />
            <Upload size={40} className="jcl-dropzone-icon" />
            {selectedFile ? (
              <div className="jcl-dropzone-file">
                <FileArchive size={20} />
                <span>{selectedFile.name}</span>
                <span className="jcl-file-size">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ) : (
              <>
                <p className="jcl-dropzone-title">{t('jclDiagnosis.uploadTitle')}</p>
                <p className="jcl-dropzone-hint">{t('jclDiagnosis.uploadHint')}</p>
              </>
            )}
          </div>

          <div className="jcl-upload-options">
            <div className="jcl-option">
              <label>{t('jclDiagnosis.language')}</label>
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="ja">日本語</option>
                <option value="ko">한국어</option>
                <option value="en">English</option>
              </select>
            </div>
            <div className="jcl-option jcl-option-message">
              <label>{t('jclDiagnosis.message')}</label>
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder={t('jclDiagnosis.messagePlaceholder')}
              />
            </div>
          </div>

          <button
            className="jcl-btn jcl-btn-primary"
            onClick={handleAnalyze}
            disabled={!selectedFile || isRunning}
          >
            {isRunning ? (
              <>
                <Loader2 size={18} className="spin" />
                {t('jclDiagnosis.analyzing')}
              </>
            ) : (
              <>
                <Play size={18} />
                {t('jclDiagnosis.analyze')}
              </>
            )}
          </button>

          {state.phase === 'error' && state.errorMessage && (
            <div className="jcl-error-banner">
              <XCircle size={18} />
              <span>{state.errorMessage}</span>
            </div>
          )}
        </div>
      )}

      {/* Zone 2: Progress Pipeline */}
      {state.phase !== 'idle' && (
        <div className="jcl-progress-zone">
          {/* Phase Steps */}
          <div className="jcl-pipeline">
            {PHASES.map((p, idx) => {
              let status: 'pending' | 'active' | 'done' | 'error' = 'pending';
              if (state.phase === 'error' && idx <= currentPhaseIdx) {
                status = idx < currentPhaseIdx ? 'done' : 'error';
              } else if (state.phase === 'complete') {
                status = 'done';
              } else if (idx < currentPhaseIdx) {
                status = 'done';
              } else if (idx === currentPhaseIdx) {
                status = 'active';
              }

              return (
                <React.Fragment key={p.key}>
                  {idx > 0 && <ChevronRight size={16} className="jcl-pipeline-arrow" />}
                  <div className={`jcl-pipeline-step ${status}`}>
                    <div className="jcl-pipeline-icon">
                      {status === 'done' && <CheckCircle2 size={16} />}
                      {status === 'active' && <Loader2 size={16} className="spin" />}
                      {status === 'error' && <XCircle size={16} />}
                      {status === 'pending' && p.icon}
                    </div>
                    <span className="jcl-pipeline-label">{t(p.labelKey)}</span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>

          {/* Details panels */}
          <div className="jcl-details">
            {/* Job Info */}
            {state.jobName && (
              <div className="jcl-detail-card">
                <h3>{t('jclDiagnosis.jobName')}: {state.jobName}</h3>
                <span className="jcl-badge">{t('jclDiagnosis.totalSteps')}: {state.totalSteps}</span>
              </div>
            )}

            {/* File Classification */}
            {state.files.length > 0 && (
              <div className="jcl-detail-card">
                <h3>{t('jclDiagnosis.phaseClassify')}</h3>
                <div className="jcl-file-badges">
                  {Object.entries(state.fileStats).map(
                    ([type, count]) =>
                      count > 0 && (
                        <span key={type} className="jcl-badge jcl-badge-file">
                          {type.toUpperCase()}: {count}
                        </span>
                      ),
                  )}
                </div>
              </div>
            )}

            {/* Step Flow */}
            {state.steps.length > 0 && (
              <div className="jcl-detail-card">
                <h3>{t('jclDiagnosis.phaseParse')}</h3>
                <div className="jcl-step-flow">
                  {state.steps.map((step, idx) => (
                    <React.Fragment key={idx}>
                      {idx > 0 && <ChevronRight size={14} className="jcl-step-arrow" />}
                      <div className={`jcl-step-node ${getStepStatusClass(step.status)}`}>
                        <div className="jcl-step-name">{step.step_name}</div>
                        <div className="jcl-step-pgm">{step.program}</div>
                        {step.return_code !== undefined && (
                          <div className="jcl-step-rc">RC={step.return_code}</div>
                        )}
                      </div>
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

            {/* Error Card */}
            {state.error && (
              <div className={`jcl-detail-card jcl-error-card ${getSeverityClass(state.error.severity)}`}>
                <div className="jcl-error-header">
                  <span className={`jcl-severity-badge ${getSeverityClass(state.error.severity)}`}>
                    {state.error.severity}
                  </span>
                  <span className="jcl-error-code">{state.error.code}</span>
                </div>
                <div className="jcl-error-body">
                  <p><strong>{t('jclDiagnosis.errorCode')}:</strong> {state.error.code} ({state.error.type})</p>
                  <p><strong>Failed Step:</strong> {state.error.failed_step}</p>
                  <p>{state.error.message}</p>
                </div>
              </div>
            )}

            {/* Search Results */}
            {state.searchResults.length > 0 && (
              <div className="jcl-detail-card">
                <h3>{t('jclDiagnosis.phaseSearch')}</h3>
                <div className="jcl-search-results">
                  {state.searchResults.map((result, idx) => (
                    <div key={idx} className="jcl-search-item">
                      <div className="jcl-search-header">
                        <span className="jcl-search-code">{result.code}</span>
                        <span className="jcl-search-source">{result.source}</span>
                      </div>
                      <div className="jcl-confidence-bar">
                        <div
                          className="jcl-confidence-fill"
                          style={{ width: `${Math.round(result.confidence * 100)}%` }}
                        />
                        <span>{Math.round(result.confidence * 100)}%</span>
                      </div>
                      <p className="jcl-search-desc">{result.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Zone 3: Report */}
      {(state.reportText || state.phase === 'complete') && (
        <div className="jcl-report-zone">
          <div className="jcl-report-header">
            <h2>{t('jclDiagnosis.phaseReport')}</h2>
            {state.phase === 'generating' && <Loader2 size={18} className="spin" />}
          </div>

          <div className="jcl-report-stream" ref={reportAreaRef}>
            <pre>{state.reportText || '...'}</pre>
          </div>

          {state.phase === 'complete' && state.diagnosisId && (
            <div className="jcl-report-actions">
              <button className="jcl-btn jcl-btn-primary" onClick={handleOpenReport}>
                <ExternalLink size={16} />
                {t('jclDiagnosis.openReport')}
              </button>
              <button className="jcl-btn jcl-btn-secondary" onClick={handleDownloadReport}>
                <Download size={16} />
                {t('jclDiagnosis.downloadReport')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default JCLDiagnosisPage;
