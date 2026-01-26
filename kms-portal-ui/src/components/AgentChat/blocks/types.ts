/**
 * Structured Answer Block Types
 * ChatGPT-style output rendering types
 */

export type BlockType =
  | 'text'
  | 'heading'
  | 'list'
  | 'code'
  | 'table'
  | 'quote'
  | 'image'
  | 'source_citation'
  | 'no_answer';

/**
 * Individual content block in a structured answer
 */
export interface AnswerBlock {
  type: BlockType;
  content?: string;

  // List block fields
  items?: string[];
  ordered?: boolean;

  // Code block fields
  language?: string;

  // Table block fields
  headers?: string[];
  rows?: string[][];

  // Heading block fields
  level?: 1 | 2 | 3 | 4;

  // Image block fields
  url?: string;
  caption?: string;

  // Source citation fields
  doc_name?: string;
  page?: number;
  chunk_id?: string;
  score?: number;
}

/**
 * Structured answer composed of blocks
 */
export interface StructuredAnswer {
  blocks: AnswerBlock[];
  confidence: number;
  language: string;
  metadata?: Record<string, unknown>;
}

/**
 * Props for the main BlockRenderer component
 */
export interface BlockRendererProps {
  blocks: AnswerBlock[];
  isStreaming?: boolean;
  onSourceClick?: (source: SourceCitationInfo) => void;
}

/**
 * Source citation click handler info
 */
export interface SourceCitationInfo {
  doc_name: string;
  page?: number;
  chunk_id?: string;
  score?: number;
}

/**
 * Common props for individual block components
 */
export interface BaseBlockProps {
  className?: string;
}
