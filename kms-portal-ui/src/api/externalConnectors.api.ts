/**
 * External Connectors API Service
 *
 * API client for managing external resource connections.
 * Supports: Notion, Confluence, GitHub, Google Drive, OneNote
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * External resource types supported by the system
 */
export type ExternalResourceType = 'notion' | 'confluence' | 'github' | 'google_drive' | 'onenote';

/**
 * Connection status
 */
export type ConnectionStatus = 'not_connected' | 'connecting' | 'connected' | 'syncing' | 'error' | 'expired';

/**
 * Sync status
 */
export type SyncStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

/**
 * Document status
 */
export type DocumentStatus = 'discovered' | 'chunking' | 'embedding' | 'ready' | 'error';

/**
 * Authentication type
 */
export type AuthType = 'oauth2' | 'api_token' | 'personal_access_token';

/**
 * Available resource configuration
 */
export interface AvailableResource {
  type: ExternalResourceType;
  name: string;
  description: string;
  auth_type: AuthType;
  scopes: string[];
  icon?: string;
}

/**
 * External connection
 */
export interface ExternalConnection {
  id: string;
  user_id: string;
  resource_type: ExternalResourceType;
  status: ConnectionStatus;
  auth_type: AuthType;
  last_sync_at: string | null;
  sync_status: SyncStatus;
  document_count: number;
  chunk_count: number;
  created_at: string;
  error_message: string | null;
}

/**
 * External document
 */
export interface ExternalDocument {
  id: string;
  title: string;
  path: string;
  external_url: string | null;
  status: string;
  chunk_count: number;
  last_synced_at: string | null;
  external_modified_at: string | null;
}

/**
 * Search result
 */
export interface ExternalSearchResult {
  chunk_id: string;
  document_id: string;
  connection_id: string;
  source: string;
  content: string;
  score: number;
  source_name: string;
  source_url: string | null;
  section_title: string | null;
}

/**
 * User stats
 */
export interface UserStats {
  total_connections: number;
  active_connections: number;
  total_documents: number;
  ready_documents: number;
  total_chunks: number;
  by_connection: Record<string, unknown>;
  by_source: Record<string, unknown>;
}

/**
 * Sync statistics
 */
export interface SyncStats {
  connection_id: string;
  status: SyncStatus;
  documents_synced: number;
  documents_added: number;
  documents_updated: number;
  documents_deleted: number;
  message: string;
}

// =============================================================================
// Request Types
// =============================================================================

export interface CreateConnectionRequest {
  resource_type: ExternalResourceType;
  api_token?: string;
  config?: Record<string, unknown>;
}

export interface SearchRequest {
  query: string;
  top_k?: number;
  min_score?: number;
  connection_ids?: string[];
}

export interface SyncRequest {
  full_sync?: boolean;
}

export interface ProcessBatchRequest {
  document_ids: string[];
}

// =============================================================================
// Response Types
// =============================================================================

export interface AvailableResourcesResponse {
  resources: AvailableResource[];
}

export interface ConnectionListResponse {
  connections: ExternalConnection[];
  total: number;
}

export interface OAuthUrlResponse {
  oauth_url: string;
  connection_id: string;
}

export interface DocumentListResponse {
  documents: ExternalDocument[];
  total: number;
  connection_id: string;
  resource_type: ExternalResourceType;
}

export interface SearchResponse {
  results: ExternalSearchResult[];
  total: number;
  query: string;
}

export interface ProcessDocumentResponse {
  id: string;
  title: string;
  status: DocumentStatus;
  chunk_count: number;
  error_message: string | null;
}

export interface ProcessBatchResponse {
  processed: number;
  failed: number;
  skipped: number;
  errors: string[];
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Get available external resource types
 */
export async function getAvailableResources(): Promise<AvailableResourcesResponse> {
  const response = await apiClient.get<AvailableResourcesResponse>('/external-connections/available');
  return response.data;
}

/**
 * List all connections for a user
 */
export async function listConnections(userId: string): Promise<ConnectionListResponse> {
  const response = await apiClient.get<ConnectionListResponse>('/external-connections', {
    params: { user_id: userId },
  });
  return response.data;
}

/**
 * Create a new connection
 */
export async function createConnection(
  userId: string,
  request: CreateConnectionRequest
): Promise<ExternalConnection> {
  const response = await apiClient.post<ExternalConnection>('/external-connections', request, {
    params: { user_id: userId },
  });
  return response.data;
}

/**
 * Get connection details
 */
export async function getConnection(connectionId: string): Promise<ExternalConnection> {
  const response = await apiClient.get<ExternalConnection>(`/external-connections/${connectionId}`);
  return response.data;
}

/**
 * Delete/disconnect a connection
 */
export async function disconnectConnection(connectionId: string): Promise<{ success: boolean; message: string }> {
  const response = await apiClient.delete<{ success: boolean; message: string }>(
    `/external-connections/${connectionId}`
  );
  return response.data;
}

/**
 * Get OAuth URL for authorization
 */
export async function getOAuthUrl(connectionId: string, redirectUri: string): Promise<OAuthUrlResponse> {
  const response = await apiClient.get<OAuthUrlResponse>(`/external-connections/${connectionId}/oauth-url`, {
    params: { redirect_uri: redirectUri },
  });
  return response.data;
}

/**
 * Complete OAuth flow with authorization code
 */
export async function completeOAuth(
  connectionId: string,
  code: string,
  redirectUri: string
): Promise<ExternalConnection> {
  const response = await apiClient.post<ExternalConnection>(
    `/external-connections/${connectionId}/oauth-callback`,
    null,
    {
      params: { code, redirect_uri: redirectUri },
    }
  );
  return response.data;
}

/**
 * Sync documents from external resource
 * Note: Sync can take a long time (5+ minutes for large workspaces), so we use a longer timeout
 */
export async function syncConnection(
  connectionId: string,
  request?: SyncRequest
): Promise<SyncStats> {
  const response = await apiClient.post<SyncStats>(
    `/external-connections/${connectionId}/sync`,
    request || {},
    {
      timeout: 600000, // 10 minutes timeout for sync operation (large workspaces can take 5+ minutes)
    }
  );
  return response.data;
}

/**
 * List documents for a connection
 */
export async function listConnectionDocuments(
  connectionId: string,
  limit = 50,
  offset = 0
): Promise<DocumentListResponse> {
  const response = await apiClient.get<DocumentListResponse>(
    `/external-connections/${connectionId}/documents`,
    {
      params: { limit, offset },
    }
  );
  return response.data;
}

/**
 * Get user stats
 */
export async function getUserStats(userId: string): Promise<UserStats> {
  const response = await apiClient.get<UserStats>(`/external-connections/stats/${userId}`);
  return response.data;
}

/**
 * Search external resources
 */
export async function searchExternalResources(
  userId: string,
  request: SearchRequest
): Promise<SearchResponse> {
  const response = await apiClient.post<SearchResponse>('/external-connections/search', request, {
    params: { user_id: userId },
  });
  return response.data;
}

/**
 * Process a single document (fetch content, chunk, embed)
 * Call this for documents with status 'discovered' to make them searchable
 */
export async function processDocument(
  connectionId: string,
  documentId: string
): Promise<ProcessDocumentResponse> {
  const response = await apiClient.post<ProcessDocumentResponse>(
    `/external-connections/${connectionId}/documents/${documentId}/process`,
    {},
    {
      timeout: 300000, // 5 minutes timeout for document processing
    }
  );
  return response.data;
}

/**
 * Process multiple documents in batch
 * Documents are processed sequentially, already processed ones are skipped
 */
export async function processDocumentsBatch(
  connectionId: string,
  documentIds: string[]
): Promise<ProcessBatchResponse> {
  const response = await apiClient.post<ProcessBatchResponse>(
    `/external-connections/${connectionId}/documents/process-batch`,
    { document_ids: documentIds },
    {
      timeout: 600000, // 10 minutes timeout for batch processing
    }
  );
  return response.data;
}

// =============================================================================
// Export
// =============================================================================

export const externalConnectorsApi = {
  getAvailableResources,
  listConnections,
  createConnection,
  getConnection,
  disconnect: disconnectConnection,
  getOAuthUrl,
  completeOAuth,
  sync: syncConnection,
  listDocuments: listConnectionDocuments,
  getUserStats,
  search: searchExternalResources,
  processDocument,
  processDocumentsBatch,
};

export default externalConnectorsApi;
