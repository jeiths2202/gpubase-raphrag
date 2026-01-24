/**
 * Query Clarification API Client
 *
 * API client for the query clarification system that handles
 * ambiguous term detection and user preference management.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * A possible meaning/interpretation of an ambiguous term
 */
export interface PossibleEntity {
  id: string;
  name: string;
  description: string;
  keywords: string[];
}

/**
 * An ambiguous term detected in the user's query
 */
export interface DetectedAmbiguousTerm {
  term: string;
  term_normalized: string;
  position_start: number;
  position_end: number;
  possible_entities: PossibleEntity[];
  category: string | null;
  user_preference: string | null;
}

/**
 * Request to check if query needs clarification
 */
export interface ClarificationCheckRequest {
  query: string;
}

/**
 * Response from clarification check
 */
export interface ClarificationCheckResponse {
  needs_clarification: boolean;
  detected_terms: DetectedAmbiguousTerm[];
  resolved_query: string | null;
  auto_resolved_count: number;
  message: string | null;
}

/**
 * User's selection for a single ambiguous term
 */
export interface TermSelection {
  term: string;
  selected_entity_id: string;
  selected_entity_name: string;
  remember: boolean;
}

/**
 * Request to apply clarification selections
 */
export interface ClarificationApplyRequest {
  query: string;
  selections: TermSelection[];
}

/**
 * Response from applying clarification
 */
export interface ClarificationApplyResponse {
  success: boolean;
  resolved_query: string;
  applied_selections: Array<{
    term: string;
    entity_id: string;
    entity_name: string;
  }>;
  preferences_saved: number;
  message: string | null;
}

/**
 * User's saved term preference
 */
export interface UserTermPreference {
  id: number;
  user_id: string;
  term_normalized: string;
  selected_entity_id: string;
  selected_entity_name: string;
  is_permanent: boolean;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

/**
 * Response for listing user preferences
 */
export interface UserPreferenceListResponse {
  preferences: UserTermPreference[];
  total: number;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Check if a query needs clarification for ambiguous terms
 */
export const checkClarification = async (
  request: ClarificationCheckRequest
): Promise<ClarificationCheckResponse> => {
  const response = await apiClient.post<ClarificationCheckResponse>(
    '/clarification/check',
    request
  );
  return response.data;
};

/**
 * Apply user's clarification selections to resolve the query
 */
export const applyClarification = async (
  request: ClarificationApplyRequest
): Promise<ClarificationApplyResponse> => {
  const response = await apiClient.post<ClarificationApplyResponse>(
    '/clarification/apply',
    request
  );
  return response.data;
};

/**
 * Get user's saved term preferences
 */
export const getUserPreferences = async (
  page: number = 1,
  pageSize: number = 20
): Promise<UserPreferenceListResponse> => {
  const response = await apiClient.get<UserPreferenceListResponse>(
    '/clarification/preferences',
    { params: { page, page_size: pageSize } }
  );
  return response.data;
};

/**
 * Delete a user's term preference
 */
export const deleteUserPreference = async (
  termNormalized: string
): Promise<{ success: boolean; message: string }> => {
  const response = await apiClient.delete<{ success: boolean; message: string }>(
    `/clarification/preferences/${encodeURIComponent(termNormalized)}`
  );
  return response.data;
};

// =============================================================================
// Export default API object
// =============================================================================

export const clarificationApi = {
  checkClarification,
  applyClarification,
  getUserPreferences,
  deleteUserPreference,
};

export default clarificationApi;
