/**
 * Improvements API Client
 *
 * API client for the AI-Driven Enhancement & Improvement Management System
 */

import apiClient from './client';

// ============================================================================
// Types
// ============================================================================

export type EnhancementStatus =
  | 'submitted'
  | 'analyzing'
  | 'analyzed'
  | 'architecture_review'
  | 'approved'
  | 'rejected'
  | 'implementing'
  | 'code_review'
  | 'testing'
  | 'verified'
  | 'released'
  | 'closed';

export type EnhancementType =
  | 'feature'
  | 'bug_fix'
  | 'improvement'
  | 'refactor'
  | 'documentation'
  | 'security'
  | 'performance';

export type EnhancementPriority = 'critical' | 'high' | 'medium' | 'low';

export type ComplexityLevel = 'low' | 'medium' | 'high' | 'very_high';

export interface AttachmentInfo {
  id: string;
  filename: string;
  original_name: string;
  file_size: number;
  mime_type: string;
  storage_path: string;
  extracted_text?: string;
  uploaded_at: string;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  event_type: string;
  description: string;
  actor_id: string;
  actor_name: string;
  actor_type: 'user' | 'agent';
  details?: Record<string, unknown>;
}

export interface Comment {
  id: string;
  content: string;
  author_id: string;
  author_name: string;
  author_type: 'user' | 'agent';
  created_at: string;
  updated_at?: string;
}

export interface AIAnalysisResult {
  summary: string;
  type_classification: EnhancementType;
  priority_recommendation: EnhancementPriority;
  affected_components: string[];
  potential_risks: string[];
  dependencies: string[];
  estimated_complexity: ComplexityLevel;
  feasibility_score: number;
  recommended_approach: string;
  questions_for_submitter: string[];
  analyzed_at: string;
  agent_id: string;
}

export interface DesignDecision {
  title: string;
  description: string;
  rationale: string;
  alternatives_considered: string[];
  trade_offs: string;
}

export interface FileChange {
  file_path: string;
  change_type: 'modify' | 'delete';
  description: string;
  estimated_lines: number;
}

export interface NewFile {
  file_path: string;
  purpose: string;
  template?: string;
}

export interface APIChange {
  endpoint: string;
  method: string;
  change_type: 'add' | 'modify' | 'deprecate' | 'remove';
  description: string;
}

export interface ArchitectureProposal {
  approach: string;
  design_decisions: DesignDecision[];
  file_changes: FileChange[];
  new_files: NewFile[];
  api_changes: APIChange[];
  database_changes: string[];
  security_considerations: string[];
  backward_compatible: boolean;
  migration_required: boolean;
  reviewed_at: string;
  reviewer_agent_id: string;
}

export interface ImplementationPhase {
  phase_number: number;
  title: string;
  description: string;
  tasks: string[];
  dependencies: number[];
  estimated_effort: string;
}

export interface TestStrategy {
  unit_tests: string[];
  integration_tests: string[];
  e2e_tests: string[];
  manual_tests: string[];
}

export interface ImplementationPlan {
  phases: ImplementationPhase[];
  test_strategy: TestStrategy;
  rollback_plan: string;
  created_at: string;
  created_by_agent: string;
}

export interface EnhancementListItem {
  id: string;
  title: string;
  type?: EnhancementType;
  priority?: EnhancementPriority;
  status: EnhancementStatus;
  author_id: string;
  author_name: string;
  created_at: string;
  updated_at: string;
  ai_analyzed: boolean;
  attachments_count: number;
}

export interface EnhancementDetail extends EnhancementListItem {
  description: string;
  attachments: AttachmentInfo[];
  ai_analysis?: AIAnalysisResult;
  architecture_proposal?: ArchitectureProposal;
  implementation_plan?: ImplementationPlan;
  timeline: TimelineEvent[];
  comments: Comment[];
  assigned_agents: string[];
  estimated_effort?: string;
  actual_effort?: string;
  impact_score?: number;
}

export interface CreateEnhancementRequest {
  title: string;
  description: string;
  type?: EnhancementType;
  priority?: EnhancementPriority;
}

export interface UpdateEnhancementRequest {
  title?: string;
  description?: string;
  type?: EnhancementType;
  priority?: EnhancementPriority;
}

export interface CreateEnhancementResponse {
  id: string;
  title: string;
  status: EnhancementStatus;
  created_at: string;
  message: string;
}

export interface AnalysisResponse {
  enhancement_id: string;
  analysis: AIAnalysisResult;
  status: EnhancementStatus;
  next_steps: string[];
}

export interface ApproveRejectRequest {
  reason?: string;
  comments?: string;
}

export interface EnhancementDashboardStats {
  total_requests: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  by_priority: Record<string, number>;
  avg_analysis_time_seconds: number;
  avg_resolution_time_hours: number;
  ai_analyzed_count: number;
  implemented_count: number;
}

export interface ListEnhancementsParams {
  page?: number;
  limit?: number;
  status?: EnhancementStatus;
  type?: EnhancementType;
  priority?: EnhancementPriority;
  author_id?: string;
  my_requests?: boolean;
  search?: string;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: { items: T[] };
  pagination: {
    page: number;
    limit: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

export interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Create a new enhancement request
 */
export const createEnhancement = async (
  request: CreateEnhancementRequest
): Promise<CreateEnhancementResponse> => {
  const response = await apiClient.post<SuccessResponse<CreateEnhancementResponse>>(
    '/enhancements',
    request
  );
  return response.data.data;
};

/**
 * List enhancement requests with filtering and pagination
 */
export const listEnhancements = async (
  params: ListEnhancementsParams = {}
): Promise<{ items: EnhancementListItem[]; pagination: PaginatedResponse<EnhancementListItem>['pagination'] }> => {
  const response = await apiClient.get<PaginatedResponse<EnhancementListItem>>(
    '/enhancements',
    { params }
  );
  return {
    items: response.data.data.items,
    pagination: response.data.pagination,
  };
};

/**
 * Get enhancement details by ID
 */
export const getEnhancement = async (id: string): Promise<EnhancementDetail> => {
  const response = await apiClient.get<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}`
  );
  return response.data.data;
};

/**
 * Update an enhancement request
 */
export const updateEnhancement = async (
  id: string,
  request: UpdateEnhancementRequest
): Promise<EnhancementDetail> => {
  const response = await apiClient.put<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}`,
    request
  );
  return response.data.data;
};

/**
 * Delete an enhancement request
 */
export const deleteEnhancement = async (id: string): Promise<void> => {
  await apiClient.delete(`/enhancements/${id}`);
};

/**
 * Get dashboard statistics
 */
export const getDashboardStats = async (): Promise<EnhancementDashboardStats> => {
  const response = await apiClient.get<SuccessResponse<EnhancementDashboardStats>>(
    '/enhancements/dashboard'
  );
  return response.data.data;
};

/**
 * Trigger AI analysis of an enhancement
 */
export const analyzeEnhancement = async (id: string): Promise<AnalysisResponse> => {
  const response = await apiClient.post<SuccessResponse<AnalysisResponse>>(
    `/enhancements/${id}/analyze`
  );
  return response.data.data;
};

/**
 * Stream AI analysis (returns EventSource URL)
 */
export const streamAnalyzeEnhancement = (id: string): string => {
  return `/api/v1/enhancements/${id}/analyze/stream`;
};

export interface ArchitectureResponse {
  enhancement_id: string;
  proposal: ArchitectureProposal;
  status: EnhancementStatus;
  next_steps: string[];
}

/**
 * Design architecture proposal for an enhancement
 */
export const designArchitecture = async (id: string): Promise<ArchitectureResponse> => {
  const response = await apiClient.post<SuccessResponse<ArchitectureResponse>>(
    `/enhancements/${id}/architecture`
  );
  return response.data.data;
};

/**
 * Stream architecture design (returns EventSource URL)
 */
export const streamDesignArchitecture = (id: string): string => {
  return `/api/v1/enhancements/${id}/architecture/stream`;
};

export interface ImplementationResponse {
  enhancement_id: string;
  plan: ImplementationPlan;
  status: EnhancementStatus;
  next_steps: string[];
}

/**
 * Create implementation plan for an enhancement
 */
export const createImplementationPlan = async (id: string): Promise<ImplementationResponse> => {
  const response = await apiClient.post<SuccessResponse<ImplementationResponse>>(
    `/enhancements/${id}/implement`
  );
  return response.data.data;
};

/**
 * Stream implementation plan creation (returns EventSource URL)
 */
export const streamImplementationPlan = (id: string): string => {
  return `/api/v1/enhancements/${id}/implement/stream`;
};

/**
 * Submit enhancement for code review
 */
export const submitForCodeReview = async (id: string): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/code-review`
  );
  return response.data.data;
};

/**
 * Complete code review
 */
export const completeCodeReview = async (
  id: string,
  approved: boolean,
  feedback?: string
): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/complete-review`,
    null,
    { params: { approved, feedback } }
  );
  return response.data.data;
};

/**
 * Approve an enhancement for implementation
 */
export const approveEnhancement = async (
  id: string,
  request?: ApproveRejectRequest
): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/approve`,
    request
  );
  return response.data.data;
};

/**
 * Reject an enhancement request
 */
export const rejectEnhancement = async (
  id: string,
  request: ApproveRejectRequest
): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/reject`,
    request
  );
  return response.data.data;
};

/**
 * Add a comment to an enhancement
 */
export const addComment = async (
  id: string,
  content: string
): Promise<Comment> => {
  const formData = new FormData();
  formData.append('content', content);
  const response = await apiClient.post<SuccessResponse<Comment>>(
    `/enhancements/${id}/comments`,
    formData
  );
  return response.data.data;
};

/**
 * Upload an attachment to an enhancement
 */
export const uploadAttachment = async (
  id: string,
  file: File
): Promise<AttachmentInfo> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post<SuccessResponse<AttachmentInfo>>(
    `/enhancements/${id}/attachments`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data.data;
};

/**
 * List attachments for an enhancement
 */
export const listAttachments = async (id: string): Promise<AttachmentInfo[]> => {
  const response = await apiClient.get<SuccessResponse<AttachmentInfo[]>>(
    `/enhancements/${id}/attachments`
  );
  return response.data.data;
};

// ============================================================================
// Testing & Verification Functions
// ============================================================================

export interface TestReport {
  execution_id: string;
  executed_at: string;
  categories: TestCategory[];
  summary: TestSummary;
}

export interface TestCategory {
  category: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  tests: TestItem[];
}

export interface TestItem {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration_ms: number;
}

export interface TestSummary {
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  overall_status: 'passed' | 'failed';
}

export interface VerificationReport {
  summary: string;
  overall_status: 'passed' | 'failed' | 'needs_review';
  test_results: TestResultCategory[];
  coverage_analysis: CoverageAnalysis;
  recommendations: string[];
  issues_found: string[];
  verified_at: string;
  verified_by_agent: string;
}

export interface TestResultCategory {
  category: string;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  notes?: string;
}

export interface CoverageAnalysis {
  estimated_coverage: number;
  critical_paths_covered: boolean;
  gaps: string[];
}

/**
 * Run tests for an enhancement
 */
export const runTests = async (id: string): Promise<TestReport> => {
  const response = await apiClient.post<SuccessResponse<TestReport>>(
    `/enhancements/${id}/run-tests`
  );
  return response.data.data;
};

/**
 * Verify an enhancement implementation
 */
export const verifyImplementation = async (id: string): Promise<VerificationReport> => {
  const response = await apiClient.post<SuccessResponse<VerificationReport>>(
    `/enhancements/${id}/verify`
  );
  return response.data.data;
};

/**
 * Mark an enhancement as verified
 */
export const markVerified = async (id: string): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/mark-verified`
  );
  return response.data.data;
};

/**
 * Release an enhancement
 */
export const releaseEnhancement = async (
  id: string,
  releaseNotes?: string
): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/release`,
    null,
    { params: { release_notes: releaseNotes } }
  );
  return response.data.data;
};

/**
 * Close an enhancement
 */
export const closeEnhancement = async (
  id: string,
  reason?: string
): Promise<EnhancementDetail> => {
  const response = await apiClient.post<SuccessResponse<EnhancementDetail>>(
    `/enhancements/${id}/close`,
    null,
    { params: { reason } }
  );
  return response.data.data;
};
