/**
 * Admin Prompts API Client
 *
 * API client for managing system prompts.
 */

import apiClient from './client';

export interface PromptSummary {
  prompt_id: string;
  name: string;
  category: 'agent' | 'middleware' | 'system' | 'persona' | 'domain';
  language: string;
  is_readonly: boolean;
  updated_at: string | null;
  content_preview: string;
}

export interface PromptDetail {
  id: string;
  prompt_id: string;
  name: string;
  description: string | null;
  category: string;
  language: string;
  content: string;
  is_readonly: boolean;
  source_file: string | null;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
  version_count: number;
}

export interface PromptHistory {
  id: string;
  version_number: number;
  content: string;
  change_reason: string | null;
  changed_at: string;
  changed_by: string | null;
}

export interface PromptUpdateRequest {
  content: string;
  reason?: string;
}

export interface PromptTestRequest {
  test_query: string;
  variables?: Record<string, string>;
}

export interface PromptTestResult {
  success: boolean;
  rendered_prompt: string;
  token_count: number;
  warnings: string[];
  error: string | null;
}

export interface SyncResult {
  synced: number;
  skipped: number;
  errors: string[];
}

export const promptsApi = {
  /**
   * List all prompts with optional filtering
   */
  listPrompts: async (
    category?: string,
    language?: string
  ): Promise<PromptSummary[]> => {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    if (language) params.append('language', language);

    const queryString = params.toString();
    const url = `/admin/prompts${queryString ? `?${queryString}` : ''}`;

    const response = await apiClient.get(url);
    return response.data;
  },

  /**
   * Get full prompt detail
   */
  getPrompt: async (
    promptId: string,
    language = 'en'
  ): Promise<PromptDetail> => {
    const response = await apiClient.get(
      `/admin/prompts/${promptId}?language=${language}`
    );
    return response.data;
  },

  /**
   * Update prompt content
   */
  updatePrompt: async (
    promptId: string,
    request: PromptUpdateRequest,
    language = 'en'
  ): Promise<PromptDetail> => {
    const response = await apiClient.put(
      `/admin/prompts/${promptId}?language=${language}`,
      request
    );
    return response.data;
  },

  /**
   * Get version history for a prompt
   */
  getHistory: async (
    promptId: string,
    language = 'en',
    limit = 20
  ): Promise<PromptHistory[]> => {
    const response = await apiClient.get(
      `/admin/prompts/${promptId}/history?language=${language}&limit=${limit}`
    );
    return response.data;
  },

  /**
   * Rollback prompt to a specific version
   */
  rollbackPrompt: async (
    promptId: string,
    versionId: string,
    language = 'en'
  ): Promise<PromptDetail> => {
    const response = await apiClient.post(
      `/admin/prompts/${promptId}/rollback/${versionId}?language=${language}`
    );
    return response.data;
  },

  /**
   * Test prompt with sample input
   */
  testPrompt: async (
    promptId: string,
    request: PromptTestRequest,
    language = 'en'
  ): Promise<PromptTestResult> => {
    const response = await apiClient.post(
      `/admin/prompts/${promptId}/test?language=${language}`,
      request
    );
    return response.data;
  },

  /**
   * Sync prompts from file system to database
   */
  syncFromFiles: async (): Promise<SyncResult> => {
    const response = await apiClient.post('/admin/prompts/sync');
    return response.data;
  },

  /**
   * Force reload prompts into runtime cache
   */
  reloadCache: async (): Promise<void> => {
    await apiClient.post('/admin/prompts/reload');
  },
};
