/**
 * Legacy Modernization API Client
 *
 * API client for the Legacy Modernization Intelligence Platform.
 * Supports COBOL/JCL/MAP/ASM analysis with 11-agent pipeline.
 */

import apiClient from './client';

// ============================================================================
// Types
// ============================================================================

export type LegacyAssetType = 'cobol' | 'jcl' | 'map' | 'asm';

export type PipelineStatus =
  | 'pending'
  | 'parsing'
  | 'domain_analysis'
  | 'knowledge_enrichment'
  | 'review'
  | 'qa_check'
  | 'e2e_validation'
  | 'risk_assessment'
  | 'competitor_analysis'
  | 'report_generation'
  | 'completed'
  | 'failed';

export type ReportType =
  | 'technical_findings'
  | 'executive_summary'
  | 'migration_roadmap'
  | 'risk_assessment'
  | 'code_quality'
  | 'vendor_comparison'
  | 'test_coverage'
  | 'compliance'
  | 'cost_estimation';

export interface AnalysisRequest {
  file_name: string;
  source_code: string;
  vendors?: string[];
  options?: AnalysisOptions;
}

export interface AnalysisOptions {
  skip_e2e?: boolean;
  skip_competitor?: boolean;
  target_vendors?: string[];
}

export interface AnalysisResponse {
  analysis_id: string;
  status: string;
  message: string;
  estimated_duration_minutes?: number;
}

export interface AnalysisStatus {
  analysis_id: string;
  status: PipelineStatus;
  progress_percent: number;
  current_agent: string | null;
  elapsed_seconds: number;
}

export interface WorkspaceState {
  asset_id: string;
  tenant_id: string;
  version: number;
  created_at: string;
  updated_at: string;
  asset_type: LegacyAssetType;
  dialect: string;
  file_path: string;
  file_name: string;
  loc_count: number;
  pipeline_status: PipelineStatus;
  ast: unknown[];
  features: unknown[];
  trace_evidence: unknown[];
  parse_errors: unknown[];
  annotations: unknown[];
  review_notes: unknown[];
  qa_flags: unknown[];
  qa_passed: boolean | null;
}

export interface AnalysisResults {
  analysis_id: string;
  workspace: WorkspaceState;
  reports: Record<string, unknown>;
}

export interface ReportListResponse {
  analysis_id: string;
  reports: ReportListItem[];
}

export interface ReportListItem {
  report_type: ReportType;
  title: string;
  generated_at: string;
}

export interface ReportDetail {
  report_type: ReportType;
  title: string;
  generated_at: string;
  content: Record<string, unknown>;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Start a legacy code analysis
 */
export const startAnalysis = async (
  request: AnalysisRequest
): Promise<AnalysisResponse> => {
  const response = await apiClient.post<AnalysisResponse>(
    '/legacy/analyze',
    request
  );
  return response.data;
};

/**
 * Get analysis progress status
 */
export const getAnalysisStatus = async (
  analysisId: string
): Promise<AnalysisStatus> => {
  const response = await apiClient.get<AnalysisStatus>(
    `/legacy/analyze/${analysisId}/status`
  );
  return response.data;
};

/**
 * Get full analysis results (workspace + reports)
 */
export const getAnalysisResults = async (
  analysisId: string
): Promise<AnalysisResults> => {
  const response = await apiClient.get<AnalysisResults>(
    `/legacy/analyze/${analysisId}/results`
  );
  return response.data;
};

/**
 * Get list of generated reports
 */
export const getReportList = async (
  analysisId: string
): Promise<ReportListResponse> => {
  const response = await apiClient.get<ReportListResponse>(
    `/legacy/reports/${analysisId}`
  );
  return response.data;
};

/**
 * Get a specific report by type
 */
export const getReport = async (
  analysisId: string,
  reportType: ReportType
): Promise<ReportDetail> => {
  const response = await apiClient.get<ReportDetail>(
    `/legacy/reports/${analysisId}/${reportType}`
  );
  return response.data;
};

/**
 * Stream analysis events via SSE
 */
export const streamAnalysisEvents = (
  analysisId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Event) => void
): EventSource => {
  const baseUrl = apiClient.defaults.baseURL || '/api/v1';
  const url = `${baseUrl}/legacy/analyze/${analysisId}/stream`;

  const eventSource = new EventSource(url, { withCredentials: true });

  eventSource.addEventListener('status_change', (e: MessageEvent) => {
    onEvent({ event: 'status_change', data: JSON.parse(e.data) });
  });

  eventSource.addEventListener('completed', (e: MessageEvent) => {
    onEvent({ event: 'completed', data: JSON.parse(e.data) });
    eventSource.close();
  });

  eventSource.addEventListener('failed', (e: MessageEvent) => {
    onEvent({ event: 'failed', data: JSON.parse(e.data) });
    eventSource.close();
  });

  eventSource.addEventListener('blocked', (e: MessageEvent) => {
    onEvent({ event: 'blocked', data: JSON.parse(e.data) });
  });

  eventSource.onmessage = (e: MessageEvent) => {
    onEvent({ event: 'message', data: JSON.parse(e.data) });
  };

  eventSource.onerror = (e: Event) => {
    if (onError) onError(e);
    eventSource.close();
  };

  return eventSource;
};

// Default export
const legacyApi = {
  startAnalysis,
  getAnalysisStatus,
  getAnalysisResults,
  getReportList,
  getReport,
  streamAnalysisEvents,
};

export default legacyApi;
