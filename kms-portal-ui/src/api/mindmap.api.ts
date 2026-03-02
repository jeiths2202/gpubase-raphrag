/**
 * Mindmap API
 *
 * API functions for mindmap generation, exploration, and querying.
 * Integrates with the backend mindmap service for knowledge graph visualization.
 */

import apiClient from './client';

// =============================================================================
// Enums
// =============================================================================

export type NodeType = 'root' | 'concept' | 'entity' | 'topic' | 'keyword';
export type RelationType =
  | 'relates_to'
  | 'contains'
  | 'causes'
  | 'depends_on'
  | 'similar_to'
  | 'opposes'
  | 'part_of'
  | 'example_of';

// =============================================================================
// Models
// =============================================================================

export interface MindmapNode {
  id: string;
  label: string;
  type: NodeType;
  description?: string;
  importance: number;
  source_chunks?: string[];
  metadata?: Record<string, unknown>;
  x?: number;
  y?: number;
  color?: string;
  size?: number;
}

export interface MindmapEdge {
  id: string;
  source: string;
  target: string;
  relation: RelationType;
  label?: string;
  strength: number;
  bidirectional?: boolean;
}

export interface MindmapData {
  nodes: MindmapNode[];
  edges: MindmapEdge[];
  root_id?: string;
  metadata?: Record<string, unknown>;
}

export interface MindmapInfo {
  id: string;
  title: string;
  description?: string;
  document_ids: string[];
  node_count: number;
  edge_count: number;
  created_at: string;
  updated_at: string;
}

export interface MindmapFull extends MindmapInfo {
  data: MindmapData;
}

// =============================================================================
// Request Types
// =============================================================================

export interface GenerateMindmapRequest {
  document_ids?: string[];
  title?: string;
  max_nodes?: number;
  depth?: number;
  focus_topic?: string;
  language?: string;
  product_id?: string;
}

export interface ExpandNodeRequest {
  node_id: string;
  depth?: number;
  max_children?: number;
  product_id?: string;
}

export interface QueryNodeRequest {
  node_id: string;
  question?: string;
  product_id?: string;
}

// =============================================================================
// Response Types
// =============================================================================

export interface GenerateMindmapResponse {
  mindmap: MindmapFull;
  message: string;
}

export interface ExpandNodeResponse {
  new_nodes: MindmapNode[];
  new_edges: MindmapEdge[];
  expanded_from: string;
}

export interface QueryNodeResponse {
  node_id: string;
  node_label: string;
  answer: string;
  related_concepts: string[];
  sources: Array<{
    title?: string;
    content?: string;
    chunk_id?: string;
    score?: number;
  }>;
}

export interface NodeDetailResponse {
  node: MindmapNode;
  connected_nodes: MindmapNode[];
  edges: MindmapEdge[];
  source_content: Array<{
    title?: string;
    content?: string;
    chunk_id?: string;
  }>;
}

export interface MindmapListResponse {
  mindmaps: MindmapInfo[];
  total: number;
}

// API response wrappers (matching backend SuccessResponse structure)
interface ApiResponse<T> {
  data: T;
  meta?: {
    request_id?: string;
    processing_time_ms?: number;
  };
}

interface PaginatedApiResponse<T> extends ApiResponse<T> {
  pagination?: {
    page: number;
    limit: number;
    total_items: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Generate a new mindmap from documents
 * POST /api/v1/mindmap/generate
 */
export const generateMindmap = async (
  request: GenerateMindmapRequest
): Promise<GenerateMindmapResponse> => {
  const response = await apiClient.post<ApiResponse<GenerateMindmapResponse>>(
    '/mindmap/generate',
    request
  );
  return response.data.data;
};

/**
 * List all mindmaps with pagination
 * GET /api/v1/mindmap
 */
export const listMindmaps = async (
  page: number = 1,
  limit: number = 20
): Promise<{ mindmaps: MindmapInfo[]; total: number; pagination?: PaginatedApiResponse<MindmapListResponse>['pagination'] }> => {
  const response = await apiClient.get<PaginatedApiResponse<MindmapListResponse>>(
    '/mindmap',
    { params: { page, limit } }
  );
  return {
    mindmaps: response.data.data.mindmaps,
    total: response.data.data.total,
    pagination: response.data.pagination,
  };
};

/**
 * Get mindmap by ID with full data (nodes and edges)
 * GET /api/v1/mindmap/{id}
 */
export const getMindmap = async (mindmapId: string): Promise<MindmapFull> => {
  const response = await apiClient.get<ApiResponse<MindmapFull>>(
    `/mindmap/${mindmapId}`
  );
  return response.data.data;
};

/**
 * Delete a mindmap
 * DELETE /api/v1/mindmap/{id}
 */
export const deleteMindmap = async (
  mindmapId: string
): Promise<{ deleted: boolean; mindmap_id: string }> => {
  const response = await apiClient.delete<ApiResponse<{ deleted: boolean; mindmap_id: string }>>(
    `/mindmap/${mindmapId}`
  );
  return response.data.data;
};

/**
 * Expand a node to add sub-concepts
 * POST /api/v1/mindmap/{id}/expand
 */
export const expandNode = async (
  mindmapId: string,
  request: ExpandNodeRequest
): Promise<ExpandNodeResponse> => {
  const response = await apiClient.post<ApiResponse<ExpandNodeResponse>>(
    `/mindmap/${mindmapId}/expand`,
    request
  );
  return response.data.data;
};

/**
 * Query about a specific node using RAG
 * POST /api/v1/mindmap/{id}/query
 */
export const queryNode = async (
  mindmapId: string,
  request: QueryNodeRequest
): Promise<QueryNodeResponse> => {
  const response = await apiClient.post<ApiResponse<QueryNodeResponse>>(
    `/mindmap/${mindmapId}/query`,
    request
  );
  return response.data.data;
};

/**
 * Get detailed information about a specific node
 * GET /api/v1/mindmap/{id}/node/{nodeId}
 */
export const getNodeDetail = async (
  mindmapId: string,
  nodeId: string
): Promise<NodeDetailResponse> => {
  const response = await apiClient.get<ApiResponse<NodeDetailResponse>>(
    `/mindmap/${mindmapId}/node/${nodeId}`
  );
  return response.data.data;
};

/**
 * Generate mindmap from all documents in the system
 * POST /api/v1/mindmap/from-all-documents
 *
 * Note: Pass language in query params to match FastAPI Query() parameter
 */
export const generateFromAllDocuments = async (params?: {
  title?: string;
  max_nodes?: number;
  focus_topic?: string;
  language?: string;
  product_id?: string;
}): Promise<GenerateMindmapResponse> => {
  // Build query string explicitly to ensure params are passed correctly
  const queryParams = new URLSearchParams();
  if (params?.title) queryParams.append('title', params.title);
  if (params?.max_nodes) queryParams.append('max_nodes', params.max_nodes.toString());
  if (params?.focus_topic) queryParams.append('focus_topic', params.focus_topic);
  if (params?.language) queryParams.append('language', params.language);
  if (params?.product_id) queryParams.append('product_id', params.product_id);

  const queryString = queryParams.toString();
  const url = queryString
    ? `/mindmap/from-all-documents?${queryString}`
    : '/mindmap/from-all-documents';

  const response = await apiClient.post<ApiResponse<GenerateMindmapResponse>>(url);
  return response.data.data;
};

// =============================================================================
// Default Export (namespace-style API)
// =============================================================================

const mindmapApi = {
  generate: generateMindmap,
  list: listMindmaps,
  get: getMindmap,
  delete: deleteMindmap,
  expandNode,
  queryNode,
  getNodeDetail,
  generateFromAllDocuments,
};

export default mindmapApi;
