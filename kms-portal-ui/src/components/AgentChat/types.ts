/**
 * AgentChat Type Definitions
 */

import type { AgentType, AgentSource } from '../../api/agent.api';

// Re-export for convenience
export type { AgentSource };

/**
 * Source reliability level
 */
export type ReliabilityLevel = 'high' | 'medium' | 'low';

/**
 * Source reliability information
 */
export interface SourceReliability {
  score: number;
  level: ReliabilityLevel;
  factors: {
    source_count: number;
    avg_similarity: number;
    source_diversity: number;
    source_quality: number;
  };
  explanation: string;
}

/**
 * Structured Answer Block (ChatGPT-style output)
 */
export interface AnswerBlock {
  type: 'text' | 'heading' | 'list' | 'code' | 'table' | 'quote' | 'image' | 'source_citation' | 'no_answer';
  content?: string;
  items?: string[];
  ordered?: boolean;
  language?: string;
  headers?: string[];
  rows?: string[][];
  level?: 1 | 2 | 3 | 4;
  url?: string;
  caption?: string;
  doc_name?: string;
  page?: number;
  chunk_id?: string;
  score?: number;
}

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
  searchResults?: ExpandableSearchResult[];  // Individual expandable search results
  sourceReliability?: SourceReliability;  // Source reliability information
  structuredBlocks?: AnswerBlock[];  // ChatGPT-style structured answer blocks
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
  rawFile?: File;  // ZIP等のバイナリアーカイブ用 (サーバーへそのまま送信)
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

/**
 * Individual expandable search result for card display
 * Each result contains text, images, tables, and source info
 */
export interface ExpandableSearchResult {
  index: number;           // 결과 순서 (1, 2, 3...)
  total: number;           // 전체 결과 수
  title: string;           // 문서/섹션 제목
  content: string;         // 텍스트 내용
  images: SearchResultImage[];   // 관련 이미지들
  tables: SearchResultTable[];   // 관련 테이블들
  source: SearchResultSource;    // 참조 문서 정보
  score: number;           // 관련도 점수
  chunkId?: string;        // 청크 ID
  chunkType?: string;      // 청크 타입 (TEXT, TABLE, IMAGE 등)
  relations?: Record<string, unknown>;  // 관련 청크 정보
}

/**
 * Image in search result
 */
export interface SearchResultImage {
  imageId: string;
  documentId?: string;
  pageNumber?: number;
  similarity?: number;
  url: string;
}

/**
 * Table in search result
 */
export interface SearchResultTable {
  markdown: string;        // 마크다운 형식의 테이블
}

/**
 * Source information for search result
 */
export interface SearchResultSource {
  documentName: string;
  pageStart?: number;
  pageEnd?: number;
  sectionPath?: string;
  sectionTitle?: string;
  docId?: string;
}

/**
 * Query Clarification Types (Human-in-the-loop)
 */

/**
 * Single option for query clarification
 */
export interface ClarificationOption {
  option_id: string;           // 옵션 식별자
  label: string;               // 짧은 라벨 (2-5 단어)
  description: string;         // 옵션 설명
  refined_query: string;       // 선택 시 사용할 구체화된 쿼리
}

/**
 * Ambiguity type for query clarification
 */
export type AmbiguityType =
  | 'term_ambiguous'           // 용어가 여러 의미를 가짐
  | 'scope_unclear'            // 범위 불명확
  | 'context_missing'          // 맥락 부족
  | 'multiple_intents'         // 다중 의도
  | 'product_unspecified';     // 제품 미지정

/**
 * Clarification request from server
 */
export interface ClarificationRequest {
  clarification_id: string;
  original_query: string;
  ambiguity_type: AmbiguityType;
  clarification_question: string;
  options: ClarificationOption[];
  allow_custom_input: boolean;
  confidence_without_clarification: number;
}

/**
 * Clarification state for UI
 */
export interface ClarificationState {
  isOpen: boolean;
  request: ClarificationRequest | null;
  selectedOptionId: string | null;
  customInput: string;
}

/**
 * Product variant for multi-product search results
 */
export interface ProductVariant {
  platform: string;        // MVS, MSP, XSP, VOS3
  productVersion?: string; // 7.1, 7.3
  description?: string;
  syntax?: string;
  sourcePdf?: string;
  pageNumbers: number[];
  solution?: string;       // For error codes
  documentVersion?: string; // v3.3.1
}

/**
 * Multi-product aggregated search result
 */
export interface MultiProductResult {
  name: string;
  docType: string;
  variants: ProductVariant[];
  hasDifferences: boolean;
  availablePlatforms: string[];
  score: number;
}

/**
 * Product section for UI display
 */
export interface ProductSection {
  platform: string;
  version?: string;
  content: string;
  source?: string;
  pageNumbers?: number[];
  availablePlatforms?: string[];
}
