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

export interface ProductVersionInfo {
  product: string;
  version: string;
  display_name: string;
  asset_types: string[];
}

export interface ProductFamilyInfo {
  family: string;
  display_name: string;
  versions: ProductVersionInfo[];
}

export interface ProductListResponse {
  families: ProductFamilyInfo[];
  total_products: number;
}

export interface AnalysisRequest {
  file_name: string;
  source_code: string;
  target_product?: string;
  target_version?: string;
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
// Batch Analysis Types
// ============================================================================

export interface FileItem {
  file_name: string;
  source_code: string;
}

export interface BatchAnalysisRequest {
  files: FileItem[];
  target_product?: string;
  target_version?: string;
  vendors?: string[];
  options?: AnalysisOptions;
}

export interface BatchAnalysisResponse {
  batch_id: string;
  total_files: number;
  analysis_ids: string[];
  status: string;
  message: string;
}

export interface FileAnalysisResult {
  file_name: string;
  analysis_id: string;
  status: 'completed' | 'failed' | 'in_progress';
  asset_type: string;
  total_features: number;
  supported_count: number;
  incompatible_count: number;
  support_rate: number;
  risk_summary: Record<string, number>;
  incompatibility_report: IncompatibilityReport | null;
}

export interface IncompatibilityReport {
  file_overview: {
    file_name: string;
    format: string;
    purpose: string;
    program: string;
    total_lines: number;
  };
  parser_verification: Array<{
    statement: string;
    of7_token: string;
    stmt_type: string;
    support: string;
  }>;
  line_analysis: Array<{
    line: number;
    source: string;
    syntax_type: string;
    verdict: 'OK' | 'WARNING' | 'INCOMPATIBLE' | 'SYNTAX_ERROR';
  }>;
  capability_lookup: Array<{
    feature: string;
    capability_key: string;
    status: string;
    notes: string;
  }>;
  incompatible_items: Array<{
    id: number;
    item: string;
    risk: 'HIGH' | 'MEDIUM' | 'LOW';
    description: string;
    mitigation: string;
  }>;
  recommendations: string[];
  summary: {
    total_features: number;
    supported: number;
    incompatible: number;
    support_rate: number;
    risk_high: number;
    risk_medium: number;
    risk_low: number;
  };
}

export interface BatchSummary {
  batch_id: string;
  total_files: number;
  completed_files: number;
  failed_files: number;
  total_features: number;
  total_supported: number;
  total_incompatible: number;
  overall_support_rate: number;
  risk_breakdown: Record<string, number>;
  top_incompatible_items: Array<{
    file_name: string;
    item: string;
    risk: string;
    description: string;
  }>;
}

export interface BatchResultsResponse {
  batch_id: string;
  summary: BatchSummary;
  file_results: FileAnalysisResult[];
}

export interface BatchSSEEvent {
  event: 'file_started' | 'file_progress' | 'file_completed' | 'file_failed' | 'batch_completed';
  data: {
    batch_id: string;
    file_name?: string;
    analysis_id?: string;
    progress_percent?: number;
    current_agent?: string;
    status?: string;
    support_rate?: number;
    incompatible_count?: number;
    error?: string;
    total_files?: number;
    completed?: number;
    failed?: number;
    overall_progress?: number;
  };
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Get available OpenFrame products (grouped by family)
 */
export const getProducts = async (
  assetType?: LegacyAssetType,
  lang: string = 'en'
): Promise<ProductListResponse> => {
  const params: Record<string, string> = { lang };
  if (assetType) params.asset_type = assetType;

  const response = await apiClient.get<ProductListResponse>(
    '/legacy/products',
    { params }
  );
  return response.data;
};

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

// ============================================================================
// Batch Analysis API Functions
// ============================================================================

/**
 * Start a batch analysis for multiple files
 */
export const startBatchAnalysis = async (
  request: BatchAnalysisRequest
): Promise<BatchAnalysisResponse> => {
  const response = await apiClient.post<BatchAnalysisResponse>(
    '/legacy/analyze/batch',
    request
  );
  return response.data;
};

/**
 * Get batch analysis results
 */
export const getBatchResults = async (
  batchId: string
): Promise<BatchResultsResponse> => {
  const response = await apiClient.get<BatchResultsResponse>(
    `/legacy/analyze/batch/${batchId}/results`
  );
  return response.data;
};

/**
 * Stream batch analysis events via SSE
 */
export const streamBatchEvents = (
  batchId: string,
  onEvent: (event: BatchSSEEvent) => void,
  onError?: (error: Event) => void
): EventSource => {
  const baseUrl = apiClient.defaults.baseURL || '/api/v1';
  const url = `${baseUrl}/legacy/analyze/batch/${batchId}/stream`;

  const eventSource = new EventSource(url, { withCredentials: true });

  const eventTypes = ['file_started', 'file_progress', 'file_completed', 'file_failed', 'batch_completed'] as const;
  for (const type of eventTypes) {
    eventSource.addEventListener(type, (e: MessageEvent) => {
      onEvent({ event: type, data: JSON.parse(e.data) });
    });
  }

  eventSource.onerror = (e: Event) => {
    if (onError) onError(e);
    eventSource.close();
  };

  return eventSource;
};

// ============================================================================
// Modernization AI Chat Types
// ============================================================================

export type ModernizationSystemType = 'host' | 'openframe' | 'all';

export interface ModernizationChatRequest {
  message: string;
  system_type: ModernizationSystemType;
  language: string;
  conversation_id?: string;
  analysis_context?: {
    analysis_id?: string;
    file_name?: string;
    asset_type?: string;
    source_code_snippet?: string;
    target_product?: string;
  };
}

/**
 * Get the SSE streaming URL for modernization chat.
 * Used directly by useModernizationChat hook via fetch.
 */
export const getModernizationChatUrl = (): string => {
  const baseUrl = apiClient.defaults.baseURL || '/api/v1';
  return `${baseUrl}/legacy/chat/stream`;
};

// ============================================================================
// Notes API
// ============================================================================

export interface ModernizationNote {
  id: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/**
 * List modernization notes
 */
export const getNotes = async (): Promise<ModernizationNote[]> => {
  const response = await apiClient.get<ModernizationNote[]>('/legacy/notes');
  return response.data;
};

/**
 * Create a modernization note
 */
export const createNote = async (
  content: string,
  tags?: string[]
): Promise<ModernizationNote> => {
  const response = await apiClient.post<ModernizationNote>('/legacy/notes', {
    content,
    tags,
  });
  return response.data;
};

/**
 * Delete a modernization note
 */
export const deleteNote = async (
  noteId: string
): Promise<{ deleted: boolean; note_id: string }> => {
  const response = await apiClient.delete<{ deleted: boolean; note_id: string }>(
    `/legacy/notes/${noteId}`
  );
  return response.data;
};

// ============================================================================
// Persisted Analysis Types (Data Table & Detail Popup)
// ============================================================================

export interface PersistedAnalysisItem {
  id: string;
  batch_id?: string | null;
  file_name: string;
  asset_type: string;
  loc_count: number;
  target_product?: string | null;
  target_version?: string | null;
  status: string;
  total_features: number;
  supported_count: number;
  incompatible_count: number;
  support_rate: number;
  risk_high: number;
  risk_medium: number;
  risk_low: number;
  analysis_duration_seconds?: number | null;
  pipeline_status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PersistedAnalysisListResponse {
  items: PersistedAnalysisItem[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface PersistedAnalysisDetail extends PersistedAnalysisItem {
  user_id?: string | null;
  source_code?: string | null;
  vendors: string[];
  incompatibility_report: IncompatibilityReport | null;
  reports: Record<string, unknown>;
  workspace_snapshot?: Record<string, unknown> | null;
}

export interface AnalysisListParams {
  page?: number;
  limit?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  asset_type?: string;
  status?: string;
  user_id?: string;
}

// ============================================================================
// Persisted Analysis API Functions
// ============================================================================

/**
 * List persisted analysis results (for Data Table)
 */
export const getPersistedAnalyses = async (
  params: AnalysisListParams = {}
): Promise<PersistedAnalysisListResponse> => {
  const response = await apiClient.get<PersistedAnalysisListResponse>(
    '/legacy/analyses',
    { params }
  );
  return response.data;
};

/**
 * Get persisted analysis detail (for popup page)
 */
export const getPersistedAnalysisDetail = async (
  analysisId: string
): Promise<PersistedAnalysisDetail> => {
  const response = await apiClient.get<PersistedAnalysisDetail>(
    `/legacy/analyses/${analysisId}`
  );
  return response.data;
};

/**
 * Delete a persisted analysis
 */
export const deletePersistedAnalysis = async (
  analysisId: string,
  userId: string = 'default'
): Promise<{ success: boolean; deleted_id: string }> => {
  const response = await apiClient.delete<{ success: boolean; deleted_id: string }>(
    `/legacy/analyses/${analysisId}`,
    { params: { user_id: userId } }
  );
  return response.data;
};

// Default export
const legacyApi = {
  getProducts,
  startAnalysis,
  getAnalysisStatus,
  getAnalysisResults,
  getReportList,
  getReport,
  streamAnalysisEvents,
  startBatchAnalysis,
  getBatchResults,
  streamBatchEvents,
  getModernizationChatUrl,
  getNotes,
  createNote,
  deleteNote,
  getPersistedAnalyses,
  getPersistedAnalysisDetail,
  deletePersistedAnalysis,
};

export default legacyApi;
