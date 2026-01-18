/**
 * AgentChat Type Definitions
 */

import type { AgentType, AgentSource } from '../../api/agent.api';

// Re-export for convenience
export type { AgentSource };

/**
 * Chat message structure
 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'status';
  content: string;
  timestamp: Date;
  agentType?: AgentType;
  toolCalls?: ToolCallInfo[];
  sources?: AgentSource[];
  images?: ImageReference[];  // Multimodal RAG images
  isStreaming?: boolean;
  error?: string;
  statusType?: 'crawling' | 'ready' | 'credentials_required';
}

/**
 * Tool call information for agent execution
 */
export interface ToolCallInfo {
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: 'pending' | 'success' | 'error';
  // Query correction info (when LLM corrupts Japanese/Korean text)
  queryCorrected?: boolean;
  originalLlmQuery?: string;
  correctedQuery?: string;
}

/**
 * Image reference from multimodal RAG
 */
export interface ImageReference {
  imageId: string;
  documentId: string;
  pageNumber?: number;
  description?: string;
  altText?: string;
  similarity?: number;
  imageBase64?: string;
  mimeType?: string;
  // Figure reference fields for document image display
  figureReference?: string;  // e.g., "fig_1_1", "fig_2"
  figureCaption?: string;    // Caption text for the figure
  width?: number;
  height?: number;
}

/**
 * Attached file information
 */
export interface AttachedFile {
  name: string;
  content: string;
  size: number;
}

/**
 * Attached URL information
 */
export interface AttachedUrl {
  url: string;
  title: string | null;
  content: string;
  charCount: number;
  isLoading: boolean;
  error: string | null;
  warning: string | null;  // Set when URL was redirected to a different page
}

/**
 * Per-agent local state structure
 */
export interface AgentLocalState {
  messages: ChatMessage[];
  streamingMessage: ChatMessage | null;
  isLoading: boolean;
  abortController: AbortController | null;
}

/**
 * Individual search result item
 */
export interface SearchResultItem {
  rank?: number;
  title?: string;
  content: string;
  similarity?: number;
  score?: number;
  source?: string;
  page?: number;
  pageNumber?: number;
  docId?: string;
  chunkType?: string;
}

/**
 * Search tool result for progress tracking
 */
export interface SearchToolResult {
  toolName: string;
  status: 'pending' | 'running' | 'success' | 'error';
  startTime?: number;
  endTime?: number;
  input?: Record<string, unknown>;
  output?: string;
  resultCount?: number;
  results?: SearchResultItem[];
  error?: string;
  queryCorrected?: boolean;
  originalQuery?: string;
  correctedQuery?: string;
}

/**
 * Search progress state for tracking RAG search operations
 */
export interface SearchProgressState {
  isOpen: boolean;
  currentQuery: string;
  toolResults: SearchToolResult[];
}

/**
 * RAG Analysis data from query analysis
 */
export interface RagAnalysis {
  original_query: string;
  keywords: string[];
  intent: string;
  search_strategy: string[];
  token_count: number;
}

/**
 * Chunk structure information
 */
export interface ChunkStructure {
  tool_name: string;
  total_chunks: number;
  chunk_types: Record<string, number>;
  page_distribution: Record<number, number>;
  avg_chunk_size: number;
  chunks_preview: Array<{
    index: number;
    type: string;
    page: number;
    size: number;
    preview: string;
    similarity: number;
  }>;
}

/**
 * Embedding information
 */
export interface EmbeddingInfo {
  tool_name: string;
  model: string;
  dimension: number;
  similarity_scores: number[];
  score_distribution: {
    excellent: number;
    good: number;
    fair: number;
    low: number;
  };
  top_matches: Array<{
    rank: number;
    source: string;
    score: number;
    score_pct: string;
  }>;
}

/**
 * Generation progress information
 */
export interface GenerationProgress {
  current_chunk: number;
  total_chunks: number;
  progress_pct: number;
  total_sources?: number;
  tools_used?: string[];
  answer_length?: number;
}

/**
 * Complete RAG progress state for detailed tracking
 */
export interface RagProgressState {
  ragAnalysis: RagAnalysis | null;
  chunkStructures: ChunkStructure[];
  embeddingInfos: EmbeddingInfo[];
  generationProgress: GenerationProgress | null;
  isGenerating: boolean;
}
