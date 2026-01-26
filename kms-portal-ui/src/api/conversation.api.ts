/**
 * Conversation API Service
 *
 * API client for managing conversation history.
 * Supports per-user, per-agent-type workspace persistence.
 */

import apiClient from './client';
import type { AgentType } from './agent.api';

// =============================================================================
// Types
// =============================================================================

/**
 * Conversation list item (summary view)
 */
export interface ConversationListItem {
  id: string;
  title: string | null;
  message_count: number;
  total_tokens: number;
  is_archived: boolean;
  is_starred: boolean;
  strategy: string | null;
  language: string | null;
  agent_type: string | null;
  created_at: string;
  updated_at: string;
  first_message_preview?: string | null;
  last_message_preview?: string | null;
}

/**
 * Message in a conversation
 */
export interface ConversationMessage {
  id: string;
  conversation_id: string;
  parent_message_id: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  model: string | null;
  sources: Array<{
    content: string;
    source: string;
    score: number;
  }>;
  feedback_score: number | null;
  feedback_text: string | null;
  is_regenerated: boolean;
  regeneration_count: number;
  is_active_branch: boolean;
  branch_depth: number;
  created_at: string;
  updated_at: string;
}

/**
 * Full conversation detail
 */
export interface ConversationDetail extends ConversationListItem {
  user_id: string;
  project_id: string | null;
  session_id: string | null;
  metadata: Record<string, unknown>;
  messages: ConversationMessage[];
  active_summary: string | null;
}

/**
 * Request to create a new conversation
 */
export interface CreateConversationRequest {
  title?: string;
  project_id?: string;
  session_id?: string;
  strategy?: 'auto' | 'vector' | 'graph' | 'hybrid' | 'code';
  language?: 'auto' | 'ko' | 'ja' | 'en';
  agent_type?: AgentType;
  metadata?: Record<string, unknown>;
}

/**
 * Request to update a conversation
 */
export interface UpdateConversationRequest {
  title?: string;
  is_archived?: boolean;
  is_starred?: boolean;
  strategy?: 'auto' | 'vector' | 'graph' | 'hybrid' | 'code';
  language?: 'auto' | 'ko' | 'ja' | 'en';
  agent_type?: AgentType;
  metadata?: Record<string, unknown>;
}

/**
 * Request to add a message
 */
export interface AddMessageRequest {
  role: 'user' | 'assistant';
  content: string;
  parent_message_id?: string;
  model?: string;
}

/**
 * Paginated response wrapper
 */
interface PaginatedResponse<T> {
  data: T;
  meta: {
    request_id: string;
  };
  pagination: {
    page: number;
    limit: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

/**
 * Success response wrapper
 */
interface SuccessResponse<T> {
  data: T;
  meta: {
    request_id: string;
  };
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * List conversations for the current user
 */
export async function listConversations(params: {
  skip?: number;
  limit?: number;
  include_archived?: boolean;
  agent_type?: AgentType;
}): Promise<{
  conversations: ConversationListItem[];
  pagination: PaginatedResponse<unknown>['pagination'];
}> {
  const response = await apiClient.get<PaginatedResponse<{ conversations: ConversationListItem[] }>>(
    '/conversations',
    { params }
  );
  return {
    conversations: response.data.data.conversations,
    pagination: response.data.pagination,
  };
}

/**
 * Create a new conversation
 */
export async function createConversation(
  request: CreateConversationRequest
): Promise<ConversationDetail> {
  const response = await apiClient.post<SuccessResponse<ConversationDetail>>(
    '/conversations',
    request
  );
  return response.data.data;
}

/**
 * Get conversation detail with messages
 */
export async function getConversation(
  conversationId: string,
  includeMessages: boolean = true
): Promise<ConversationDetail> {
  const response = await apiClient.get<SuccessResponse<ConversationDetail>>(
    `/conversations/${conversationId}`,
    { params: { include_messages: includeMessages } }
  );
  return response.data.data;
}

/**
 * Update a conversation
 */
export async function updateConversation(
  conversationId: string,
  request: UpdateConversationRequest
): Promise<ConversationDetail> {
  const response = await apiClient.patch<SuccessResponse<ConversationDetail>>(
    `/conversations/${conversationId}`,
    request
  );
  return response.data.data;
}

/**
 * Delete a conversation
 */
export async function deleteConversation(
  conversationId: string,
  hardDelete: boolean = false
): Promise<{ deleted: boolean; conversation_id: string }> {
  const response = await apiClient.delete<SuccessResponse<{ deleted: boolean; conversation_id: string }>>(
    `/conversations/${conversationId}`,
    { params: { hard_delete: hardDelete } }
  );
  return response.data.data;
}

/**
 * Add a message to a conversation
 */
export async function addMessage(
  conversationId: string,
  request: AddMessageRequest
): Promise<ConversationMessage> {
  const response = await apiClient.post<SuccessResponse<ConversationMessage>>(
    `/conversations/${conversationId}/messages`,
    request
  );
  return response.data.data;
}

/**
 * Get messages in a conversation
 */
export async function getMessages(
  conversationId: string,
  params?: {
    include_inactive_branches?: boolean;
    skip?: number;
    limit?: number;
  }
): Promise<ConversationMessage[]> {
  const response = await apiClient.get<SuccessResponse<ConversationMessage[]>>(
    `/conversations/${conversationId}/messages`,
    { params }
  );
  return response.data.data;
}

/**
 * Add feedback to a message
 */
export async function addFeedback(
  conversationId: string,
  messageId: string,
  feedback: { score: number; text?: string }
): Promise<{ success: boolean; message_id: string }> {
  const response = await apiClient.post<SuccessResponse<{ success: boolean; message_id: string }>>(
    `/conversations/${conversationId}/messages/${messageId}/feedback`,
    feedback
  );
  return response.data.data;
}

/**
 * Get user conversation statistics
 */
export async function getStats(): Promise<{
  total_conversations: number;
  active_conversations: number;
  archived_conversations: number;
  total_messages: number;
  total_tokens: number;
}> {
  const response = await apiClient.get<SuccessResponse<{
    total_conversations: number;
    active_conversations: number;
    archived_conversations: number;
    total_messages: number;
    total_tokens: number;
  }>>('/conversations/stats');
  return response.data.data;
}

// =============================================================================
// Exports
// =============================================================================

export const conversationApi = {
  list: listConversations,
  create: createConversation,
  get: getConversation,
  update: updateConversation,
  delete: deleteConversation,
  addMessage,
  getMessages,
  addFeedback,
  getStats,
};

export default conversationApi;
