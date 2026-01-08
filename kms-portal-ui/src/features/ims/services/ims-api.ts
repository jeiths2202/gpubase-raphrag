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
} from '../types';
import { useAuthStore } from '../../../store/authStore';

const API_BASE = '/api/v1';

/**
 * Get authorization headers
 */
function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

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
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
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
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
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
    headers: { ...getAuthHeaders() },
    credentials: 'include',
  });
  if (!response.ok) {
    console.warn('Failed to invalidate search cache');
  }
}
