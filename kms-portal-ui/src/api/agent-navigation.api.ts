/**
 * Agent Navigation API Client
 *
 * API client for Agent-Driven RAG document navigation and session management.
 * Enables pre-search scope selection and session restoration.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Section candidate returned from API
 */
export interface SectionCandidate {
  section_path: string;
  section_title: string;
  page_start: number;
  page_end: number;
  relevance_score: number;
  level: number;
}

/**
 * Document candidate returned from API
 */
export interface DocumentCandidate {
  pdf_id: string;
  document_name: string;
  document_type: string;
  total_pages: number;
  relevance_score: number;
  sections: SectionCandidate[];
  keywords: string[];
}

/**
 * Search scope selection
 */
export interface SearchScope {
  documents: string[];
  sections: string[];
  keywords?: string[];
}

/**
 * Get candidates request
 */
export interface GetCandidatesRequest {
  query: string;
  top_k?: number;
  min_score?: number;
}

/**
 * Get candidates response
 */
export interface GetCandidatesResponse {
  data: {
    candidates: DocumentCandidate[];
    suggested_scope: SearchScope | null;
    total_candidates: number;
  };
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * Scope selection request
 */
export interface ScopeSelectionRequest {
  query: string;
  selected_documents: string[];
  selected_sections: string[];
}

/**
 * Scope selection response
 */
export interface ScopeSelectionResponse {
  data: {
    scope: SearchScope;
    saved_to_history: boolean;
  };
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * Document map entry
 */
export interface DocumentMapEntry {
  pdf_id: string;
  document_name: string;
  document_type: string;
  total_pages: number;
  total_sections?: number;
  sections?: Array<{
    id: string;
    title: string;
    level: number;
    page_start: number;
    page_end: number;
  }>;
  keywords: string[];
  language?: string;
}

/**
 * Document map response
 */
export interface DocumentMapResponse {
  data: {
    documents: DocumentMapEntry[];
    total_documents: number;
  };
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * Session state for restoration
 */
export interface SessionState {
  timestamp: string;
  last_query: string;
  selected_scope: SearchScope | null;
  conversation_id: string | null;
  agent_type: string;
  age_hours: number;
  can_restore: boolean;
}

/**
 * Session check response
 */
export interface SessionCheckResponse {
  data: SessionState;
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * Session restore response
 */
export interface SessionRestoreResponse {
  data: {
    restored: boolean;
    session: SessionState | null;
  };
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * Search history entry
 */
export interface SearchHistoryEntry {
  query: string;
  timestamp: string;
  selected_scope: SearchScope | null;
  result_count: number;
  was_successful: boolean;
}

/**
 * Search history response
 */
export interface SearchHistoryResponse {
  data: {
    history: SearchHistoryEntry[];
    total_items: number;
  };
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

/**
 * User preferences for agent navigation
 */
export interface AgentPreferences {
  default_documents: string[];
  language: string;
  always_confirm_scope: boolean;
  max_history_items: number;
  auto_restore_session: boolean;
}

/**
 * Preferences response
 */
export interface PreferencesResponse {
  data: AgentPreferences;
  meta: {
    timestamp: string;
    request_id: string;
    processing_time_ms: number;
  };
}

// =============================================================================
// API Functions - Navigation
// =============================================================================

/**
 * Get document/section candidates for a query
 */
export const getCandidates = async (
  request: GetCandidatesRequest
): Promise<GetCandidatesResponse> => {
  const response = await apiClient.post<GetCandidatesResponse>(
    '/agent-navigation/candidates',
    request
  );
  return response.data;
};

/**
 * Confirm scope selection
 */
export const selectScope = async (
  request: ScopeSelectionRequest
): Promise<ScopeSelectionResponse> => {
  const response = await apiClient.post<ScopeSelectionResponse>(
    '/agent-navigation/select-scope',
    request
  );
  return response.data;
};

/**
 * Get document map for navigation
 */
export const getDocumentMap = async (
  pdfId?: string
): Promise<DocumentMapResponse> => {
  const params = pdfId ? `?pdf_id=${encodeURIComponent(pdfId)}` : '';
  const response = await apiClient.get<DocumentMapResponse>(
    `/agent-navigation/document-map${params}`
  );
  return response.data;
};

/**
 * Search documents by keyword
 */
export const searchByKeyword = async (
  keyword: string,
  includeSections = true
): Promise<DocumentMapResponse> => {
  const params = new URLSearchParams({
    keyword,
    include_sections: includeSections.toString(),
  });
  const response = await apiClient.get<DocumentMapResponse>(
    `/agent-navigation/search-keyword?${params}`
  );
  return response.data;
};

/**
 * Refresh document map
 */
export const refreshDocumentMap = async (
  pdfId?: string
): Promise<{ data: { success: boolean; pdf_id: string | null } }> => {
  const params = pdfId ? `?pdf_id=${encodeURIComponent(pdfId)}` : '';
  const response = await apiClient.post<{ data: { success: boolean; pdf_id: string | null } }>(
    `/agent-navigation/refresh${params}`
  );
  return response.data;
};

// =============================================================================
// API Functions - Session
// =============================================================================

/**
 * Check if a previous session can be restored
 */
export const checkSessionRestore = async (
  maxAgeHours = 24
): Promise<SessionCheckResponse> => {
  const response = await apiClient.get<SessionCheckResponse>(
    `/agent-session/restore-check?max_age_hours=${maxAgeHours}`
  );
  return response.data;
};

/**
 * Restore or dismiss previous session
 */
export const restoreSession = async (
  restore: boolean
): Promise<SessionRestoreResponse> => {
  const response = await apiClient.post<SessionRestoreResponse>(
    '/agent-session/restore',
    { restore }
  );
  return response.data;
};

/**
 * Get search history
 */
export const getSearchHistory = async (
  limit = 20
): Promise<SearchHistoryResponse> => {
  const response = await apiClient.get<SearchHistoryResponse>(
    `/agent-session/history?limit=${limit}`
  );
  return response.data;
};

/**
 * Clear search history
 */
export const clearSearchHistory = async (): Promise<{ data: { cleared: boolean } }> => {
  const response = await apiClient.delete<{ data: { cleared: boolean } }>(
    '/agent-session/history'
  );
  return response.data;
};

/**
 * Get user preferences
 */
export const getPreferences = async (): Promise<PreferencesResponse> => {
  const response = await apiClient.get<PreferencesResponse>(
    '/agent-session/preferences'
  );
  return response.data;
};

/**
 * Update user preferences
 */
export const updatePreferences = async (
  preferences: Partial<AgentPreferences>
): Promise<PreferencesResponse> => {
  const response = await apiClient.put<PreferencesResponse>(
    '/agent-session/preferences',
    preferences
  );
  return response.data;
};

/**
 * Update session state
 */
export const updateSessionState = async (options: {
  query: string;
  conversation_id?: string;
  agent_type?: string;
  selected_documents?: string[];
  selected_sections?: string[];
}): Promise<{ data: { updated: boolean } }> => {
  const params = new URLSearchParams({ query: options.query });
  if (options.conversation_id) params.append('conversation_id', options.conversation_id);
  if (options.agent_type) params.append('agent_type', options.agent_type);
  if (options.selected_documents) {
    options.selected_documents.forEach(d => params.append('selected_documents', d));
  }
  if (options.selected_sections) {
    options.selected_sections.forEach(s => params.append('selected_sections', s));
  }
  const response = await apiClient.post<{ data: { updated: boolean } }>(
    `/agent-session/update-state?${params}`
  );
  return response.data;
};

// =============================================================================
// Export default API object
// =============================================================================

export const agentNavigationApi = {
  // Navigation
  getCandidates,
  selectScope,
  getDocumentMap,
  searchByKeyword,
  refreshDocumentMap,

  // Session
  checkSessionRestore,
  restoreSession,
  getSearchHistory,
  clearSearchHistory,
  getPreferences,
  updatePreferences,
  updateSessionState,
};

export default agentNavigationApi;
