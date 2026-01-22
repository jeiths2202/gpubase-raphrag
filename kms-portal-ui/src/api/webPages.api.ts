/**
 * Web Pages API Service
 *
 * API client for managing web page sources for RAG.
 * Handles URL-based document fetching, extraction, and embedding.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Web source processing status
 */
export type WebSourceStatus =
  | 'pending'
  | 'fetching'
  | 'extracting'
  | 'chunking'
  | 'embedding'
  | 'ready'
  | 'error';

/**
 * Content extractor type
 */
export type ExtractorType = 'trafilatura' | 'beautifulsoup';

/**
 * Content type
 */
export type ContentType =
  | 'generic'
  | 'article'
  | 'blog'
  | 'documentation'
  | 'news'
  | 'wiki';

/**
 * Web source list item
 */
export interface WebSourceListItem {
  id: string;
  url: string;
  display_name: string;
  domain: string;
  status: WebSourceStatus;
  chunk_count: number;
  word_count: number;
  tags: string[];
  created_at: string;
  fetched_at: string | null;
  error_message: string | null;
}

/**
 * Full web source details
 */
export interface WebSource {
  id: string;
  url: string;
  display_name: string;
  domain: string;
  extractor: ExtractorType;
  include_images: boolean;
  include_links: boolean;
  status: WebSourceStatus;
  http_status_code: number | null;
  error_message: string | null;
  retry_count: number;
  extracted_text: string | null;
  extracted_links: LinkInfo[];
  extracted_images: ImageInfo[];
  content_hash: string | null;
  metadata: WebSourceMetadata;
  stats: WebSourceStats;
  tags: string[];
  created_at: string;
  updated_at: string;
  fetched_at: string | null;
  processed_at: string | null;
}

/**
 * Web source metadata
 */
export interface WebSourceMetadata {
  title: string | null;
  description: string | null;
  author: string | null;
  site_name: string | null;
  og_image: string | null;
  language: string | null;
  keywords: string[];
  canonical_url: string | null;
  content_type: ContentType;
  published_date: string | null;
  modified_date: string | null;
}

/**
 * Web source stats
 */
export interface WebSourceStats {
  word_count: number;
  char_count: number;
  chunk_count: number;
  link_count: number;
  image_count: number;
  fetch_time_ms: number;
  extraction_time_ms: number;
  last_fetched: string | null;
  last_checked: string | null;
}

/**
 * Extracted link info
 */
export interface LinkInfo {
  url: string;
  text: string;
  is_internal: boolean;
}

/**
 * Extracted image info
 */
export interface ImageInfo {
  url: string;
  alt_text: string;
  caption: string;
  width: number | null;
  height: number | null;
}

// =============================================================================
// Request Types
// =============================================================================

/**
 * Create web source request
 */
export interface CreateWebSourceRequest {
  url: string;
  name?: string;
  tags?: string[];
  extractor?: ExtractorType;
  include_images?: boolean;
  include_links?: boolean;
}

/**
 * Bulk create web source request
 */
export interface BulkCreateWebSourceRequest {
  urls: string[];
  tags?: string[];
  extractor?: ExtractorType;
}

/**
 * List params
 */
export interface ListWebSourcesParams {
  status?: WebSourceStatus;
  domain?: string;
  tags?: string;
  page?: number;
  limit?: number;
}

// =============================================================================
// Response Types
// =============================================================================

export interface WebSourceResponse {
  status: string;
  data: {
    web_source: WebSource;
  };
  message?: string;
}

export interface WebSourceListResponse {
  status: string;
  data: {
    web_sources: WebSourceListItem[];
    total: number;
    page: number;
    limit: number;
  };
}

export interface BulkCreateResponse {
  status: string;
  data: {
    web_sources: WebSource[];
    count: number;
  };
  message?: string;
}

export interface ContentResponse {
  status: string;
  data: {
    web_source_id: string;
    url: string;
    title: string | null;
    content: string | null;
    word_count: number;
    char_count: number;
  };
}

export interface LinksResponse {
  status: string;
  data: {
    web_source_id: string;
    links: LinkInfo[];
    count: number;
  };
}

export interface ImagesResponse {
  status: string;
  data: {
    web_source_id: string;
    images: ImageInfo[];
    count: number;
  };
}

export interface SearchResponse {
  status: string;
  data: {
    results: WebSourceListItem[];
    count: number;
    query: string;
  };
}

export interface RefreshResponse {
  status: string;
  data: {
    web_source_id: string;
  };
  message?: string;
}

export interface DeleteResponse {
  status: string;
  message?: string;
}

// =============================================================================
// API Functions
// =============================================================================

const BASE_URL = '/api/v1/web-sources';

/**
 * List web sources with optional filtering
 */
export const listWebSources = async (
  params: ListWebSourcesParams = {}
): Promise<WebSourceListResponse> => {
  const searchParams = new URLSearchParams();

  if (params.status) searchParams.set('status', params.status);
  if (params.domain) searchParams.set('domain', params.domain);
  if (params.tags) searchParams.set('tags', params.tags);
  if (params.page) searchParams.set('page', params.page.toString());
  if (params.limit) searchParams.set('limit', params.limit.toString());

  const queryString = searchParams.toString();
  const url = queryString ? `${BASE_URL}?${queryString}` : BASE_URL;

  const response = await apiClient.get<WebSourceListResponse>(url);
  return response.data;
};

/**
 * Get web source by ID
 */
export const getWebSource = async (id: string): Promise<WebSourceResponse> => {
  const response = await apiClient.get<WebSourceResponse>(`${BASE_URL}/${id}`);
  return response.data;
};

/**
 * Create a new web source
 */
export const createWebSource = async (
  request: CreateWebSourceRequest
): Promise<WebSourceResponse> => {
  const response = await apiClient.post<WebSourceResponse>(BASE_URL, request);
  return response.data;
};

/**
 * Create multiple web sources
 */
export const createBulkWebSources = async (
  request: BulkCreateWebSourceRequest
): Promise<BulkCreateResponse> => {
  const response = await apiClient.post<BulkCreateResponse>(
    `${BASE_URL}/bulk`,
    request
  );
  return response.data;
};

/**
 * Refresh web source content
 */
export const refreshWebSource = async (
  id: string,
  force: boolean = false
): Promise<RefreshResponse> => {
  const response = await apiClient.post<RefreshResponse>(
    `${BASE_URL}/${id}/refresh`,
    { force }
  );
  return response.data;
};

/**
 * Delete a web source
 */
export const deleteWebSource = async (id: string): Promise<DeleteResponse> => {
  const response = await apiClient.delete<DeleteResponse>(`${BASE_URL}/${id}`);
  return response.data;
};

/**
 * Get extracted content from web source
 */
export const getWebSourceContent = async (
  id: string
): Promise<ContentResponse> => {
  const response = await apiClient.get<ContentResponse>(
    `${BASE_URL}/${id}/content`
  );
  return response.data;
};

/**
 * Get extracted links from web source
 */
export const getWebSourceLinks = async (
  id: string,
  internalOnly: boolean = false
): Promise<LinksResponse> => {
  const url = internalOnly
    ? `${BASE_URL}/${id}/links?internal_only=true`
    : `${BASE_URL}/${id}/links`;

  const response = await apiClient.get<LinksResponse>(url);
  return response.data;
};

/**
 * Get extracted images from web source
 */
export const getWebSourceImages = async (id: string): Promise<ImagesResponse> => {
  const response = await apiClient.get<ImagesResponse>(
    `${BASE_URL}/${id}/images`
  );
  return response.data;
};

/**
 * Search web sources by content or metadata
 */
export const searchWebSources = async (
  query: string,
  limit: number = 20
): Promise<SearchResponse> => {
  const response = await apiClient.get<SearchResponse>(
    `${BASE_URL}/search?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  return response.data;
};

// =============================================================================
// Default Export
// =============================================================================

const webPagesApi = {
  list: listWebSources,
  get: getWebSource,
  create: createWebSource,
  createBulk: createBulkWebSources,
  refresh: refreshWebSource,
  delete: deleteWebSource,
  getContent: getWebSourceContent,
  getLinks: getWebSourceLinks,
  getImages: getWebSourceImages,
  search: searchWebSources,
};

export default webPagesApi;
