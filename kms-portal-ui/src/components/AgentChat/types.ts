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
