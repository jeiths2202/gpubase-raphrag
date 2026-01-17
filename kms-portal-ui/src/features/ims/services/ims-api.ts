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
 * Get multiple issues by their database UUIDs
 * Use this to fetch specific crawled issues by UUID
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

/**
 * Get multiple issues by their IMS IDs (e.g., "304640", "278109")
 * Use this to fetch specific issues by IMS ID strings
 */
export async function getIssuesByImsIds(imsIds: string[]): Promise<IMSIssue[]> {
  const response = await fetch(`${API_BASE}/ims-search/by-ims-ids`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ ims_ids: imsIds }),
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

// ============================================
// Deep Agent Search API
// ============================================

/**
 * Result from agent-based IMS search
 */
export interface AgentSearchResult {
  issues: IMSIssue[];
  rawResponse: string;
  success: boolean;
  error?: string;
}

/**
 * Parse markdown table from agent response to extract IMS issues
 * Table format: | No | Issue ID | Title | Status | Product |
 */
function parseMarkdownTableToIssues(markdown: string): IMSIssue[] {
  const issues: IMSIssue[] = [];
  const lines = markdown.split('\n');

  let inTable = false;
  let headerPassed = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Detect table start
    if (trimmed.startsWith('|') && trimmed.includes('Issue ID')) {
      inTable = true;
      continue;
    }

    // Skip separator line
    if (inTable && trimmed.startsWith('|') && trimmed.includes('---')) {
      headerPassed = true;
      continue;
    }

    // Parse table row
    if (inTable && headerPassed && trimmed.startsWith('|')) {
      const cells = trimmed.split('|').map(c => c.trim()).filter(c => c);

      if (cells.length >= 5) {
        // Extract IMS ID and URL from markdown link [IMS-123](url)
        const idCell = cells[1];
        const linkMatch = idCell.match(/\[([^\]]+)\]\(([^)]+)\)/);

        const imsId = linkMatch ? linkMatch[1] : idCell;
        const url = linkMatch ? linkMatch[2] : '';

        const title = cells[2] || '';
        const status = cells[3] || '';
        const product = cells[4] || '';

        issues.push({
          id: imsId,
          ims_id: imsId,
          title: title,
          description: '',
          status: status as IMSIssue['status'],
          priority: 'medium' as IMSIssue['priority'],
          product: product,
          reporter: '',
          project_key: '',
          labels: [],
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          // Store URL in custom field for click handling
          _url: url,
        } as IMSIssue & { _url?: string });
      }
    }

    // Detect table end
    if (inTable && headerPassed && !trimmed.startsWith('|') && trimmed !== '') {
      break;
    }
  }

  return issues;
}

/**
 * Search IMS using Deep Agent (same as Agent Chat)
 * Streams the response, extracts IMS IDs, then fetches full details from DB
 */
export async function searchWithAgent(
  query: string,
  onProgress?: (status: string) => void,
  signal?: AbortSignal
): Promise<AgentSearchResult> {
  try {
    const response = await fetch(`${API_BASE}/agents/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        task: query,
        agent_type: 'ims',
        language: 'ko',
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`Agent request failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let accumulatedContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data && data !== '[DONE]') {
            try {
              const chunk = JSON.parse(data);

              // Handle different chunk types
              if (chunk.chunk_type === 'text' && chunk.content) {
                accumulatedContent += chunk.content;
              } else if (chunk.chunk_type === 'status' && chunk.content && onProgress) {
                onProgress(chunk.content);
              } else if (chunk.chunk_type === 'thinking' && onProgress) {
                onProgress('analyzing');
              } else if (chunk.chunk_type === 'tool_call' && onProgress) {
                onProgress('searching');
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    }

    // Parse the markdown table to extract IMS IDs
    const parsedIssues = parseMarkdownTableToIssues(accumulatedContent);
    const imsIds = parsedIssues.map(issue => issue.ims_id).filter(id => id);

    console.log('[IMS Agent] Parsed IMS IDs:', imsIds);

    // Fetch full issue details from database using IMS IDs
    let fullIssues: IMSIssue[] = [];
    if (imsIds.length > 0) {
      try {
        if (onProgress) onProgress('loading');
        fullIssues = await getIssuesByImsIds(imsIds);
        console.log('[IMS Agent] Fetched full details:', fullIssues.length, 'issues');
      } catch (fetchError) {
        console.warn('[IMS Agent] Failed to fetch full details, using parsed data:', fetchError);
        // Fallback to parsed data if fetch fails
        fullIssues = parsedIssues;
      }
    }

    return {
      issues: fullIssues.length > 0 ? fullIssues : parsedIssues,
      rawResponse: accumulatedContent,
      success: true,
    };

  } catch (error) {
    console.error('[IMS Agent] Search error:', error);
    return {
      issues: [],
      rawResponse: '',
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}
