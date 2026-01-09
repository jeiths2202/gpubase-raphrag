/**
 * IMS Knowledge Service API Client
 */

import type {
  CredentialsRequest,
  CredentialsResponse,
  ValidationResponse,
  SearchRequest,
  SearchResponse,
  CrawlJobRequest,
  CrawlJobResponse,
  IMSIssue,
  IMSChatRequest,
  IMSChatResponse,
  IMSChatConversation,
} from '../types';

const API_BASE = '/api/v1';

// Note: Authorization is handled via HttpOnly cookies
// All requests use credentials: 'include' to send cookies automatically

/**
 * Helper function to handle API responses
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Unknown error' }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }
  return response.json();
}

// ============================================
// Credentials API
// ============================================

/**
 * Create or update IMS credentials
 */
export async function createCredentials(data: CredentialsRequest): Promise<CredentialsResponse> {
  const response = await fetch(`${API_BASE}/ims-credentials/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<CredentialsResponse>(response);
}

/**
 * Get credentials metadata (no sensitive data)
 */
export async function getCredentials(): Promise<CredentialsResponse> {
  const response = await fetch(`${API_BASE}/ims-credentials/`, {
    method: 'GET',
        credentials: 'include',
  });
  return handleResponse<CredentialsResponse>(response);
}

/**
 * Validate stored credentials against IMS
 */
export async function validateCredentials(): Promise<ValidationResponse> {
  const response = await fetch(`${API_BASE}/ims-credentials/validate`, {
    method: 'POST',
        credentials: 'include',
  });
  return handleResponse<ValidationResponse>(response);
}

/**
 * Delete stored credentials
 */
export async function deleteCredentials(): Promise<void> {
  const response = await fetch(`${API_BASE}/ims-credentials/`, {
    method: 'DELETE',
        credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Unknown error' }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }
}

// ============================================
// Search API
// ============================================

/**
 * Search IMS issues with hybrid search
 */
export async function searchIssues(data: SearchRequest): Promise<SearchResponse> {
  const response = await fetch(`${API_BASE}/ims-search/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<SearchResponse>(response);
}

/**
 * Get recently crawled issues
 */
export async function getRecentIssues(limit: number = 20): Promise<IMSIssue[]> {
  const response = await fetch(`${API_BASE}/ims-search/recent?limit=${limit}`, {
    method: 'GET',
        credentials: 'include',
  });
  return handleResponse<IMSIssue[]>(response);
}

/**
 * Get issue details by ID
 */
export async function getIssueDetails(issueId: string): Promise<IMSIssue> {
  const response = await fetch(`${API_BASE}/ims-search/${issueId}`, {
    method: 'GET',
        credentials: 'include',
  });
  return handleResponse<IMSIssue>(response);
}

/**
 * Get multiple issues by their IDs
 * Use this to fetch specific crawled issues instead of searching the database
 */
export async function getIssuesByIds(issueIds: string[]): Promise<IMSIssue[]> {
  const response = await fetch(`${API_BASE}/ims-search/by-ids`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ issue_ids: issueIds }),
  });
  return handleResponse<IMSIssue[]>(response);
}

// ============================================
// Crawl Jobs API
// ============================================

/**
 * Create a new crawl job
 */
export async function createCrawlJob(data: CrawlJobRequest): Promise<CrawlJobResponse> {
  const response = await fetch(`${API_BASE}/ims-jobs/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  });
  return handleResponse<CrawlJobResponse>(response);
}

/**
 * Get crawl job status (for polling)
 */
export async function getJobStatus(jobId: string): Promise<CrawlJobResponse> {
  const response = await fetch(`${API_BASE}/ims-jobs/${jobId}`, {
    method: 'GET',
        credentials: 'include',
  });
  return handleResponse<CrawlJobResponse>(response);
}

/**
 * Get SSE stream URL for real-time progress
 */
export function getJobStreamUrl(jobId: string): string {
  return `${API_BASE}/ims-jobs/${jobId}/stream`;
}

/**
 * Cancel a running crawl job
 */
export async function cancelCrawlJob(jobId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/ims-jobs/${jobId}`, {
    method: 'DELETE',
        credentials: 'include',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Unknown error' }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }
}

// ============================================
// Dashboard API (Optional)
// ============================================

/**
 * Get dashboard quick stats
 */
export async function getQuickStats(): Promise<{
  total_issues: number;
  open_issues: number;
  critical_issues: number;
  total_crawls: number;
  resolution_rate: number;
}> {
  const response = await fetch(`${API_BASE}/ims-dashboard/quick-stats`, {
    method: 'GET',
        credentials: 'include',
  });
  return handleResponse(response);
}

// ============================================
// Cache API (Optional)
// ============================================

/**
 * Invalidate search cache
 */
export async function invalidateSearchCache(): Promise<void> {
  const response = await fetch(`${API_BASE}/ims-cache/invalidate/search`, {
    method: 'DELETE',
        credentials: 'include',
  });
  if (!response.ok) {
    console.warn('Failed to invalidate search cache');
  }
}

// ============================================
// AI Chat API
// ============================================

/**
 * Send chat message (non-streaming)
 */
export async function sendChatMessage(data: IMSChatRequest): Promise<IMSChatResponse> {
  const response = await fetch(`${API_BASE}/ims-chat/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ ...data, stream: false }),
  });
  return handleResponse<IMSChatResponse>(response);
}

/**
 * Get SSE stream URL for chat (streaming)
 */
export function getChatStreamUrl(): string {
  return `${API_BASE}/ims-chat/stream`;
}

/**
 * Stream chat response using SSE
 */
export async function* streamChatMessage(
  data: IMSChatRequest
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const response = await fetch(`${API_BASE}/ims-chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ ...data, stream: true }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Unknown error' }));
    throw new Error(error.detail || error.message || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        // Event names are parsed but data lines are processed separately
        continue;
      }
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          // Get event name from previous line or default to 'message'
          yield { event: 'message', data };
        } catch (e) {
          // Skip invalid JSON
        }
      }
    }
  }
}

/**
 * Get chat conversation history
 */
export async function getChatConversations(limit: number = 20): Promise<{
  conversations: IMSChatConversation[];
  total: number;
}> {
  const response = await fetch(`${API_BASE}/ims-chat/conversations?limit=${limit}`, {
    method: 'GET',
    credentials: 'include',
  });
  return handleResponse(response);
}

/**
 * Get a specific conversation
 */
export async function getChatConversation(conversationId: string): Promise<IMSChatConversation> {
  const response = await fetch(`${API_BASE}/ims-chat/conversations/${conversationId}`, {
    method: 'GET',
    credentials: 'include',
  });
  return handleResponse<IMSChatConversation>(response);
}
