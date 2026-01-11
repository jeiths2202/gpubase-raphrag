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
