/**
 * FAQ API Client
 *
 * API client for FAQ system - fetches dynamic FAQ items generated from popular queries.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * FAQ item from API
 */
export interface FAQItemAPI {
  id: string;
  source_type: 'static' | 'dynamic' | 'curated';
  question: string;
  answer: string;
  category: string;
  tags: string[];
  view_count: number;
  helpful_count: number;
  not_helpful_count: number;
  is_pinned: boolean;
  created_at: string | null;
}

/**
 * FAQ category with counts
 */
export interface FAQCategory {
  id: string;
  name: string;
  name_ko: string;
  name_ja: string;
  count: number;
}

/**
 * Popular query item (admin only)
 */
export interface PopularQuery {
  id: string;
  query: string;
  answer: string | null;
  frequency_count: number;
  unique_users: number;
  popularity_score: number;
  is_faq_eligible: boolean;
  agent_type: string | null;
  category: string | null;
  last_asked: string | null;
  first_asked: string | null;
}

/**
 * FAQ list response
 */
export interface FAQListResponse {
  status: string;
  data: {
    items: FAQItemAPI[];
    total: number;
    has_more: boolean;
  };
}

/**
 * FAQ categories response
 */
export interface FAQCategoriesResponse {
  status: string;
  data: {
    categories: FAQCategory[];
  };
}

/**
 * Popular queries response (admin)
 */
export interface PopularQueriesResponse {
  status: string;
  data: {
    queries: PopularQuery[];
    total: number;
    period_days: number;
  };
}

/**
 * Options for fetching FAQ items
 */
export interface GetFAQItemsOptions {
  category?: string;
  language?: 'en' | 'ko' | 'ja';
  limit?: number;
  offset?: number;
  include_dynamic?: boolean;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Get FAQ items
 */
export const getFAQItems = async (options: GetFAQItemsOptions = {}): Promise<FAQListResponse> => {
  const params = new URLSearchParams();

  if (options.category) params.append('category', options.category);
  if (options.language) params.append('language', options.language);
  if (options.limit !== undefined) params.append('limit', options.limit.toString());
  if (options.offset !== undefined) params.append('offset', options.offset.toString());
  if (options.include_dynamic !== undefined) {
    params.append('include_dynamic', options.include_dynamic.toString());
  }

  const queryString = params.toString();
  const url = `/faq${queryString ? `?${queryString}` : ''}`;

  const response = await apiClient.get<FAQListResponse>(url);
  return response.data;
};

/**
 * Get FAQ categories
 */
export const getFAQCategories = async (): Promise<FAQCategoriesResponse> => {
  const response = await apiClient.get<FAQCategoriesResponse>('/faq/categories');
  return response.data;
};

/**
 * Record a view for an FAQ item
 */
export const recordFAQView = async (faqId: string): Promise<void> => {
  await apiClient.post(`/faq/${faqId}/view`);
};

/**
 * Record feedback for an FAQ item
 */
export const recordFAQFeedback = async (faqId: string, isHelpful: boolean): Promise<void> => {
  await apiClient.post(`/faq/${faqId}/feedback`, { is_helpful: isHelpful });
};

/**
 * Get popular queries (admin only)
 */
export const getPopularQueries = async (options: {
  days?: number;
  category?: string;
  agent_type?: string;
  min_frequency?: number;
  limit?: number;
  offset?: number;
} = {}): Promise<PopularQueriesResponse> => {
  const params = new URLSearchParams();

  if (options.days !== undefined) params.append('days', options.days.toString());
  if (options.category) params.append('category', options.category);
  if (options.agent_type) params.append('agent_type', options.agent_type);
  if (options.min_frequency !== undefined) {
    params.append('min_frequency', options.min_frequency.toString());
  }
  if (options.limit !== undefined) params.append('limit', options.limit.toString());
  if (options.offset !== undefined) params.append('offset', options.offset.toString());

  const queryString = params.toString();
  const url = `/faq/popular${queryString ? `?${queryString}` : ''}`;

  const response = await apiClient.get<PopularQueriesResponse>(url);
  return response.data;
};

/**
 * Sync dynamic FAQ items from popular queries (admin only)
 */
export const syncDynamicFAQItems = async (minFrequency?: number): Promise<{ count: number }> => {
  const params = minFrequency !== undefined ? `?min_frequency=${minFrequency}` : '';
  const response = await apiClient.post<{ status: string; message: string; count: number }>(
    `/faq/sync-dynamic${params}`
  );
  return { count: response.data.count };
};

// =============================================================================
// Export default API object
// =============================================================================

export const faqApi = {
  getItems: getFAQItems,
  getCategories: getFAQCategories,
  recordView: recordFAQView,
  recordFeedback: recordFAQFeedback,
  getPopularQueries,
  syncDynamicFAQItems,
};

export default faqApi;
