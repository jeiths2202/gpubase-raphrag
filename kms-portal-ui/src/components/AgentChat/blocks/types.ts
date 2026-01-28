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
  | 'no_answer'
  | 'product_version';

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

  // Product version block fields
  name?: string;  // Command/error/term name
  doc_type?: string;  // commands, error-codes, glossary
  variants?: ProductVariantData[];
  has_differences?: boolean;
  available_platforms?: string[];
}

/**
 * Product variant data for ProductVersionBlock
 */
export interface ProductVariantData {
  platform: string;        // MVS, MSP, XSP, VOS3
  product_version?: string; // 7.1, 7.3
  description?: string;
  syntax?: string;
  source_pdf?: string;
  page_numbers?: number[];
  solution?: string;
  document_version?: string;
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
