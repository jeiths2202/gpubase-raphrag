/**
 * Adaptive Documents API Client
 *
 * API client for structure-preserving PDF chunking and embedding.
 * Supports semantic boundary-based chunking with hierarchical relationships.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Chunk type classification
 */
export type ChunkType = 'TEXT_CHUNK' | 'TABLE_CHUNK' | 'IMAGE_CHUNK' | 'OCR_CHUNK';

/**
 * Document type classification
 */
export type DocumentType = 'manual' | 'report' | 'paper' | 'contract' | 'presentation' | 'form' | 'other';

/**
 * Processing status
 */
export type ProcessingStatus = 'pending' | 'analyzing' | 'chunking' | 'embedding' | 'validating' | 'completed' | 'failed' | 'partial';

/**
 * Quality level
 */
export type QualityLevel = 'excellent' | 'good' | 'fair' | 'poor';

/**
 * Process request options
 */
export interface AdaptiveProcessOptions {
  language?: string;
  maxChunkSize?: number;
  minChunkSize?: number;
  overlapSize?: number;
  preserveTables?: boolean;
  preserveSections?: boolean;
  forceReprocess?: boolean;
}

/**
 * Process response
 */
export interface AdaptiveProcessResponse {
  pdf_id: string;
  task_id: string;
  status: ProcessingStatus;
  message: string;
  estimated_chunks: number;
}

/**
 * Chunk list item
 */
export interface ChunkListItem {
  chunk_id: string;
  chunk_type: ChunkType;
  content_preview: string;
  content_length: number;
  page_start: number;
  page_end: number;
  section_path: string | null;
  section_title: string | null;
  has_embedding: boolean;
}

/**
 * Chunk detail
 */
export interface ChunkDetail {
  chunk_id: string;
  pdf_id: string;
  chunk_type: ChunkType;
  content: string;
  content_length: number;
  page_start: number;
  page_end: number;
  section_path: string | null;
  section_title: string | null;
  relations: {
    previous: string | null;
    next: string | null;
    references: string[];
    parent: string | null;
    children: string[];
  };
  has_embedding: boolean;
  embedding_model_version: string;
  chunk_version: number;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

/**
 * Coverage response
 */
export interface CoverageResponse {
  pdf_id: string;
  text_coverage: number;
  table_coverage: number;
  image_coverage: number;
  ocr_coverage: number;
  overall_coverage: number;
  total_chunks: number;
  embedded_chunks: number;
  quality_level: QualityLevel;
  last_verified_at: string | null;
}

/**
 * Quality response
 */
export interface QualityResponse {
  pdf_id: string;
  top_k_recall: number;
  section_precision: number;
  avg_similarity: number;
  quality_level: QualityLevel;
  hallucination_detected: boolean;
  issues: string[];
  recommendations: string[];
}

/**
 * Structure analysis response
 */
export interface StructureAnalysisResponse {
  pdf_id: string;
  document_type: DocumentType;
  total_pages: number;
  total_sections: number;
  total_images: number;
  total_tables: number;
  language: string;
  hierarchy: Array<{
    id: string;
    title: string;
    level: number;
    page_start: number;
    page_end: number;
    parent_id: string | null;
    children: string[];
  }>;
  layout_info: {
    columns: number;
    has_header: boolean;
    has_footer: boolean;
    has_toc: boolean;
    page_dimensions: { width: number; height: number };
  };
  analyzed_at: string | null;
}

/**
 * Search request
 */
export interface SearchAdaptiveChunksRequest {
  query: string;
  pdf_id?: string;
  chunk_types?: ChunkType[];
  section_path_prefix?: string;
  limit?: number;
  min_similarity?: number;
}

/**
 * Search result item
 */
export interface SearchResultItem {
  chunk_id: string;
  pdf_id: string;
  chunk_type: ChunkType;
  content: string;
  section_path: string | null;
  section_title: string | null;
  page_start: number;
  page_end: number;
  similarity: number;
  related_chunks: string[];
}

/**
 * Search response
 */
export interface SearchAdaptiveChunksResponse {
  query: string;
  total_results: number;
  results: SearchResultItem[];
}

/**
 * Processing status response
 */
export interface ProcessingStatusResponse {
  task_id: string;
  status: ProcessingStatus;
  progress: number;
  message: string;
  pdf_id?: string;
  chunks_processed?: number;
  chunks_total?: number;
  error?: string;
}

/**
 * Delete response
 */
export interface DeleteResponse {
  status: string;
  pdf_id: string;
  details: {
    chunks_deleted: number;
    structure_deleted: boolean;
    coverage_deleted: boolean;
  };
}

// =============================================================================
// API Functions
// =============================================================================

const API_PREFIX = '/documents/adaptive';

/**
 * Adaptive document list item (from list API)
 */
export interface AdaptiveDocumentListItem {
  pdf_id: string;
  document_type: DocumentType;
  total_pages: number;
  total_sections: number;
  language: string;
  chunks_count: number;
  status: ProcessingStatus;
  created_at: string | null;
}

/**
 * List all adaptive documents
 */
export const listAdaptiveDocuments = async (): Promise<AdaptiveDocumentListItem[]> => {
  const response = await apiClient.get<AdaptiveDocumentListItem[]>(`${API_PREFIX}/list`);
  return response.data;
};

/**
 * Process a PDF with adaptive embedding
 */
export const processAdaptivePDF = async (
  file: File,
  options: AdaptiveProcessOptions = {}
): Promise<AdaptiveProcessResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  // Build query params
  const params = new URLSearchParams();
  if (options.language) params.append('language', options.language);
  if (options.maxChunkSize !== undefined) params.append('max_chunk_size', options.maxChunkSize.toString());
  if (options.minChunkSize !== undefined) params.append('min_chunk_size', options.minChunkSize.toString());
  if (options.preserveTables !== undefined) params.append('preserve_tables', options.preserveTables.toString());
  if (options.preserveSections !== undefined) params.append('preserve_sections', options.preserveSections.toString());
  if (options.forceReprocess !== undefined) params.append('force_reprocess', options.forceReprocess.toString());

  const queryString = params.toString();
  const url = `${API_PREFIX}/process${queryString ? `?${queryString}` : ''}`;

  // PDF processing can take a long time (structure analysis, chunking, embedding)
  // Use extended timeout of 5 minutes for large documents
  const response = await apiClient.post<AdaptiveProcessResponse>(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 300000, // 5 minutes timeout for PDF processing
  });
  return response.data;
};

/**
 * Get chunks for a document
 */
export const getAdaptiveChunks = async (
  pdfId: string,
  chunkType?: ChunkType
): Promise<ChunkListItem[]> => {
  const params = chunkType ? `?chunk_type=${chunkType}` : '';
  const response = await apiClient.get<ChunkListItem[]>(`${API_PREFIX}/${pdfId}/chunks${params}`);
  return response.data;
};

/**
 * Get chunk detail
 */
export const getChunkDetail = async (
  pdfId: string,
  chunkId: string
): Promise<ChunkDetail> => {
  const response = await apiClient.get<ChunkDetail>(`${API_PREFIX}/${pdfId}/chunks/${chunkId}`);
  return response.data;
};

/**
 * Get coverage report
 */
export const getCoverage = async (pdfId: string): Promise<CoverageResponse> => {
  const response = await apiClient.get<CoverageResponse>(`${API_PREFIX}/${pdfId}/coverage`);
  return response.data;
};

/**
 * Get quality metrics
 */
export const getQuality = async (pdfId: string): Promise<QualityResponse> => {
  const response = await apiClient.get<QualityResponse>(`${API_PREFIX}/${pdfId}/quality`);
  return response.data;
};

/**
 * Refresh quality metrics (recalculates with actual embeddings)
 */
export const refreshQuality = async (pdfId: string): Promise<QualityResponse> => {
  const response = await apiClient.post<QualityResponse>(`${API_PREFIX}/${pdfId}/refresh-quality`);
  return response.data;
};

/**
 * Get structure analysis
 */
export const getStructure = async (pdfId: string): Promise<StructureAnalysisResponse> => {
  const response = await apiClient.get<StructureAnalysisResponse>(`${API_PREFIX}/${pdfId}/structure`);
  return response.data;
};

/**
 * Search adaptive chunks
 */
export const searchAdaptiveChunks = async (
  request: SearchAdaptiveChunksRequest
): Promise<SearchAdaptiveChunksResponse> => {
  const response = await apiClient.post<SearchAdaptiveChunksResponse>(`${API_PREFIX}/search`, request);
  return response.data;
};

/**
 * Get processing status
 */
export const getProcessingStatus = async (taskId: string): Promise<ProcessingStatusResponse> => {
  const response = await apiClient.get<ProcessingStatusResponse>(`${API_PREFIX}/status/${taskId}`);
  return response.data;
};

/**
 * Delete document and all related data
 */
export const deleteAdaptiveDocument = async (pdfId: string): Promise<DeleteResponse> => {
  const response = await apiClient.delete<DeleteResponse>(`${API_PREFIX}/${pdfId}`);
  return response.data;
};

/**
 * Batch delete response
 */
export interface BatchDeleteResponse {
  status: string;
  total_requested: number;
  deleted: number;
  failed: number;
  results: {
    success: string[];
    failed: Array<{ pdf_id: string; error: string }>;
  };
}

/**
 * Delete multiple documents at once
 */
export const batchDeleteAdaptiveDocuments = async (pdfIds: string[]): Promise<BatchDeleteResponse> => {
  const response = await apiClient.post<BatchDeleteResponse>(`${API_PREFIX}/batch-delete`, pdfIds);
  return response.data;
};

// =============================================================================
// Export default API object
// =============================================================================

export const adaptiveDocumentsApi = {
  list: listAdaptiveDocuments,
  process: processAdaptivePDF,
  getChunks: getAdaptiveChunks,
  getChunkDetail,
  getCoverage,
  getQuality,
  refreshQuality,
  getStructure,
  search: searchAdaptiveChunks,
  getStatus: getProcessingStatus,
  delete: deleteAdaptiveDocument,
  batchDelete: batchDeleteAdaptiveDocuments,
};

export default adaptiveDocumentsApi;
