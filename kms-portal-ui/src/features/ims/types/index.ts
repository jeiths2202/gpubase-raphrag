/**
 * IMS Knowledge Service Types
 */

// View mode for displaying results
export type ViewMode = 'table' | 'cards' | 'graph';

// Issue status enum
export type IssueStatus = 'open' | 'in_progress' | 'resolved' | 'closed' | 'pending' | 'rejected';

// Issue priority enum
export type IssuePriority = 'critical' | 'high' | 'medium' | 'low' | 'trivial';

// Job status enum
export type JobStatus =
  | 'pending'
  | 'authenticating'
  | 'parsing_query'
  | 'crawling'
  | 'processing_attachments'
  | 'embedding'
  | 'completed'
  | 'failed'
  | 'cancelled';

/**
 * IMS Issue entity
 */
export interface IMSIssue {
  id: string;
  ims_id: string;
  title: string;
  description: string;
  status: IssueStatus;
  priority: IssuePriority;
  // IMS-specific fields
  category?: string;
  product?: string;
  version?: string;
  module?: string;
  customer?: string;
  issued_date?: string;
  // Metadata
  reporter: string;
  assignee?: string;
  project_key: string;
  labels: string[];
  created_at: string;
  updated_at: string;
  similarity_score?: number;
  hybrid_score?: number;
  // Related issues from IMS Related Issue tab
  related_issue_ids?: string[];
}

/**
 * Issue relation for graph visualization
 */
export interface IssueRelation {
  source_ims_id: string;
  target_ims_id: string;
  relation_type: string;
}

/**
 * Relations response from API
 */
export interface RelationsResponse {
  total_relations: number;
  relations: IssueRelation[];
}

/**
 * Crawl Job entity
 */
export interface IMSJob {
  id: string;
  user_id: string;
  raw_query: string;
  parsed_query?: string;
  status: JobStatus;
  current_step: string;
  progress_percentage: number;
  issues_found: number;
  issues_crawled: number;
  attachments_processed: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  is_cached?: boolean;  // True if results are from cache (within 24h)
  result_issue_ids?: string[];  // Issue IDs for cached results
}

/**
 * Progress snapshot captured at job completion
 */
export interface ProgressSnapshot {
  status: string;
  progress: number;
  currentStep: string;
  timestamp: string;
  issuesFound: number;
  issuesCrawled: number;
  relatedCount?: number;
}

/**
 * Completion statistics for a finished job
 */
export interface CompletionStats {
  totalIssues: number;
  successfulIssues: number;
  duration: number; // in seconds
  outcome: 'success' | 'partial' | 'failed';
  relatedIssues?: number;
  attachments?: number;
  failedIssues?: number;
  progressSnapshot?: ProgressSnapshot;
  resultIssueIds?: string[]; // UUIDs of crawled issues for direct fetching
}

/**
 * Search result tab
 */
export interface IMSSearchTab {
  id: string;
  query: string;
  timestamp: string;
  results: IMSIssue[];
  viewMode: ViewMode;
  completionStats?: CompletionStats;
}

/**
 * SSE Event data structure
 */
export interface SSEEventData {
  event: string;
  status?: JobStatus;
  progress?: number;
  step?: string;
  message?: string;
  // Backend sends both formats - handle either
  total_issues?: number;
  issues_found?: number;
  crawled_issues?: number;
  issues_crawled?: number;
  related_issues?: number;
  related_count?: number;
  attachments?: number;
  attachments_processed?: number;
  issue_number?: number;
  issue_id?: string;
  error?: string;
  // Job completion data
  result_issue_ids?: string[];
}

/**
 * Activity log entry for progress tracker
 */
export interface ActivityLogEntry {
  id: string;
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'error' | 'warning';
}

// ============================================
// API Request/Response Types
// ============================================

/**
 * Credentials create/update request
 */
export interface CredentialsRequest {
  ims_url: string;
  username: string;
  password: string;
}

/**
 * Credentials response (no sensitive data)
 */
export interface CredentialsResponse {
  id: string;
  user_id: string;
  ims_url: string;
  is_validated: boolean;
  last_validated_at?: string;
  validation_error?: string;
  created_at: string;
  updated_at: string;
}

/**
 * Credentials validation response
 */
export interface ValidationResponse {
  is_valid: boolean;
  message: string;
  validated_at?: string;
}

/**
 * Search request
 */
export interface SearchRequest {
  query: string;
  max_results?: number;
  include_attachments?: boolean;
  include_related?: boolean;
  search_strategy?: 'hybrid' | 'semantic' | 'recent';
}

/**
 * Search response
 */
export interface SearchResponse {
  total_results: number;
  query_used: string;
  search_intent?: string;
  results: IMSIssue[];
  execution_time_ms: number;
}

/**
 * Product option for IMS search
 */
export interface ProductOption {
  code: string;
  name: string;
  category: 'openframe' | 'other';
}

/**
 * Available products for IMS search
 */
export const IMS_PRODUCTS: ProductOption[] = [
  // OpenFrame products
  { code: '128', name: 'OpenFrame AIM', category: 'openframe' },
  { code: '520', name: 'OpenFrame ASM', category: 'openframe' },
  { code: '129', name: 'OpenFrame Base', category: 'openframe' },
  { code: '123', name: 'OpenFrame Batch', category: 'openframe' },
  { code: '500', name: 'OpenFrame COBOL', category: 'openframe' },
  { code: '137', name: 'OpenFrame Common', category: 'openframe' },
  { code: '141', name: 'OpenFrame GW', category: 'openframe' },
  { code: '126', name: 'OpenFrame HiDB', category: 'openframe' },
  { code: '147', name: 'OpenFrame ISPF', category: 'openframe' },
  { code: '145', name: 'OpenFrame Manager', category: 'openframe' },
  { code: '135', name: 'OpenFrame Map GUI Editor', category: 'openframe' },
  { code: '143', name: 'OpenFrame Miner', category: 'openframe' },
  { code: '138', name: 'OpenFrame OSC', category: 'openframe' },
  { code: '134', name: 'OpenFrame OSI', category: 'openframe' },
  { code: '142', name: 'OpenFrame OpenStudio Web', category: 'openframe' },
  { code: '510', name: 'OpenFrame PLI', category: 'openframe' },
  { code: '127', name: 'OpenFrame Studio', category: 'openframe' },
  { code: '124', name: 'OpenFrame TACF', category: 'openframe' },
  // Other products
  { code: '640', name: 'ProSort', category: 'other' },
  { code: '425', name: 'ProTrieve', category: 'other' },
];

/**
 * Crawl job create request
 */
export interface CrawlJobRequest {
  query: string;
  include_attachments?: boolean;
  include_related_issues?: boolean;
  max_issues?: number;
  product_codes?: string[];
}

/**
 * Crawl job response
 */
export interface CrawlJobResponse extends IMSJob {}

// ============================================
// UI Component Props Types
// ============================================

/**
 * Progress tracker stats
 */
export interface ProgressStats {
  found: number;
  crawled: number;
  related: number;
}

/**
 * Table sort configuration
 */
export interface SortConfig {
  field: keyof IMSIssue | 'similarity_score';
  direction: 'asc' | 'desc';
}

/**
 * Table filter configuration
 */
export interface FilterConfig {
  status?: IssueStatus;
  priority?: IssuePriority;
}

/**
 * Graph node for visualization
 */
export interface GraphNode {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  issue: IMSIssue;
  color: string;
}

/**
 * Graph link for visualization
 */
export interface GraphLink {
  source: string;
  target: string;
  type: 'similarity' | 'project' | 'label';
  strength: number;
}

// ============================================
// AI Chat Types
// ============================================

/**
 * Chat message role
 */
export type ChatRole = 'user' | 'assistant' | 'system';

/**
 * Chat message
 */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  created_at: string;
  referenced_issues?: string[];
}

/**
 * AI Chat request
 */
export interface IMSChatRequest {
  question: string;
  issue_ids: string[];
  conversation_id?: string;
  language?: 'auto' | 'ko' | 'ja' | 'en';
  stream?: boolean;
  max_context_issues?: number;
}

/**
 * AI Chat response (non-streaming)
 */
export interface IMSChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  role: ChatRole;
  referenced_issues: IMSIssueContext[];
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  created_at: string;
}

/**
 * Issue context for AI chat
 */
export interface IMSIssueContext {
  issue_id: string;
  ims_id: string;
  title: string;
  status_raw?: string;
  priority_raw?: string;
  product?: string;
  version?: string;
  module?: string;
  customer?: string;
  description?: string;
  relevance_score: number;
}

/**
 * SSE event for streaming chat
 */
export interface IMSChatStreamEvent {
  event: 'start' | 'token' | 'sources' | 'done' | 'error';
  data: {
    conversation_id?: string;
    message_id?: string;
    content?: string;
    is_final?: boolean;
    sources?: IMSIssueContext[];
    issues_count?: number;
    total_issues?: number;
    message?: string;
  };
}

/**
 * Chat conversation
 */
export interface IMSChatConversation {
  id: string;
  title?: string;
  issue_ids: string[];
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}
