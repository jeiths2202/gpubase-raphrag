/**
 * Types for Enhancement Request components
 */

// Enhancement Request Types
export interface EnhanceRequest {
  id: string;
  title: string;
  type?: EnhanceRequestType;
  priority?: EnhancePriority;
  status: EnhanceStatus;
  author_id: string;
  author_name: string;
  created_at: string;
  updated_at: string;
  ai_analyzed: boolean;
}

export type EnhanceRequestType =
  | 'feature'
  | 'bug_fix'
  | 'improvement'
  | 'refactor'
  | 'documentation'
  | 'security'
  | 'performance';

export type EnhancePriority = 'critical' | 'high' | 'medium' | 'low';

export type EnhanceStatus =
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

// Queue Types
export type AgentType = 'analyst' | 'architect' | 'coder' | 'qa';

export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface QueuedTask {
  id: string;
  enhancement_id: string;
  agent_type: AgentType;
  operation: string;
  status: TaskStatus;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  user_id: string;
  user_name: string;
  error_message?: string;
  duration_ms?: number;
  queue_position?: number;
}

export interface AgentStatus {
  agent_type: AgentType;
  is_running: boolean;
  current_task?: QueuedTask;
  total_processed: number;
  total_failed: number;
  last_activity?: string;
}

export interface QueueStatus {
  queue: {
    total_queued: number;
    tasks: QueuedTask[];
  };
  agents: Record<string, AgentStatus>;
  running_tasks: QueuedTask[];
  recent_history: QueuedTask[];
}

// Stats Types
export interface EnhanceStats {
  total: number;
  pending: number;
  analyzed: number;
  implemented: number;
}

// Pagination Types
export interface PaginationState {
  page: number;
  totalPages: number;
  totalItems: number;
}
