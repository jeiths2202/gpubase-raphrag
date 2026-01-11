/**
 * API Key API
 *
 * Type-safe wrappers for API key management endpoints.
 * Allows users to create and manage API keys for public RAG access.
 */

import apiClient from './client';
import type { ApiResponse } from './types';

// =============================================================================
// Types
// =============================================================================

/**
 * API key creation request
 */
export interface ApiKeyCreateRequest {
  name: string;
  description?: string;
  allowed_endpoints?: string[];
  allowed_agent_types?: string[];
  rate_limit_per_minute?: number;
  rate_limit_per_hour?: number;
  rate_limit_per_day?: number;
  expires_in_days?: number;
}

/**
 * API key update request
 */
export interface ApiKeyUpdateRequest {
  name?: string;
  description?: string;
  allowed_endpoints?: string[];
  allowed_agent_types?: string[];
  rate_limit_per_minute?: number;
  rate_limit_per_hour?: number;
  rate_limit_per_day?: number;
  is_active?: boolean;
}

/**
 * API key response (without actual key)
 */
export interface ApiKeyResponse {
  id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  owner_id: string | null;
  allowed_endpoints: string[];
  allowed_agent_types: string[];
  rate_limit_per_minute: number;
  rate_limit_per_hour: number;
  rate_limit_per_day: number;
  total_requests: number;
  total_tokens_used: number;
  last_used_at: string | null;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * API key created response (includes full key - shown only once)
 */
export interface ApiKeyCreatedResponse {
  id: string;
  name: string;
  key: string;
  key_prefix: string;
  message: string;
}

/**
 * Paginated API key list response
 */
export interface ApiKeyListResponse {
  items: ApiKeyResponse[];
  total: number;
  page: number;
  page_size: number;
}

// =============================================================================
// API Endpoints
// =============================================================================

/**
 * Create a new API key
 *
 * @param data - API key creation data
 * @returns Created API key with full key (shown only once)
 */
export const createApiKey = async (data: ApiKeyCreateRequest): Promise<ApiKeyCreatedResponse> => {
  const response = await apiClient.post<ApiKeyCreatedResponse>('/api-keys', data);
  return response.data;
};

/**
 * List user's API keys
 *
 * @param page - Page number (1-based)
 * @param pageSize - Items per page
 * @param includeInactive - Include inactive keys
 * @returns Paginated list of API keys
 */
export const listApiKeys = async (
  page: number = 1,
  pageSize: number = 20,
  includeInactive: boolean = false
): Promise<ApiKeyListResponse> => {
  const response = await apiClient.get<ApiKeyListResponse>('/api-keys', {
    params: {
      page,
      page_size: pageSize,
      include_inactive: includeInactive,
    },
  });
  return response.data;
};

/**
 * Get a specific API key
 *
 * @param id - API key ID
 * @returns API key details
 */
export const getApiKey = async (id: string): Promise<ApiKeyResponse> => {
  const response = await apiClient.get<ApiKeyResponse>(`/api-keys/${id}`);
  return response.data;
};

/**
 * Update an API key
 *
 * @param id - API key ID
 * @param data - Fields to update
 * @returns Updated API key
 */
export const updateApiKey = async (
  id: string,
  data: ApiKeyUpdateRequest
): Promise<ApiKeyResponse> => {
  const response = await apiClient.patch<ApiKeyResponse>(`/api-keys/${id}`, data);
  return response.data;
};

/**
 * Delete (deactivate) an API key
 *
 * @param id - API key ID
 */
export const deleteApiKey = async (id: string): Promise<void> => {
  await apiClient.delete(`/api-keys/${id}`);
};

// =============================================================================
// Export as namespace
// =============================================================================

export const apiKeyApi = {
  create: createApiKey,
  list: listApiKeys,
  get: getApiKey,
  update: updateApiKey,
  delete: deleteApiKey,
};

export default apiKeyApi;
