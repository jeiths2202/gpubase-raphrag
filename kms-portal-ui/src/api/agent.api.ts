/**
 * Agent API Service
 *
 * API client for the AI Agent system.
 * Supports both regular and streaming agent execution.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Agent types available in the system
 */
export type AgentType = 'rag' | 'ims' | 'vision' | 'code' | 'planner';

/**
 * Agent execution request
 */
export interface AgentExecuteRequest {
  task: string;
  agent_type?: AgentType;
  session_id?: string;
  max_steps?: number;
}

/**
 * Agent execution response
 */
export interface AgentExecuteResponse {
  answer: string;
  agent_type: AgentType;
  session_id: string;
  steps: number;
  sources: AgentSource[];
  execution_time: number;
  success: boolean;
  error: string | null;
}

/**
 * Agent source document
 */
export interface AgentSource {
  content: string;
  source: string;
  score: number;
}

/**
 * Agent stream chunk types
 */
export type AgentStreamChunkType =
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'text'
  | 'sources'
  | 'error'
  | 'done';

/**
 * Agent stream chunk
 */
export interface AgentStreamChunk {
  chunk_type: AgentStreamChunkType;
  content: string | null;
  tool_name: string | null;
  tool_input: Record<string, unknown> | null;
  tool_output: string | null;
  sources: AgentSource[] | null;
  metadata: Record<string, unknown> | null;
}

/**
 * Tool definition
 */
export interface ToolDefinition {
  name: string;
  description: string;
}

/**
 * Agent health response
 */
export interface AgentHealthResponse {
  status: string;
  agents_registered: number;
  tools_registered: number;
}

/**
 * Classify task response
 */
export interface ClassifyTaskResponse {
  task: string;
  agent_type: AgentType;
  confidence: number;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Execute an agent task (non-streaming)
 */
export async function executeAgent(request: AgentExecuteRequest): Promise<AgentExecuteResponse> {
  const response = await apiClient.post<AgentExecuteResponse>('/agents/execute', request);
  return response.data;
}

/**
 * Stream agent execution using Server-Sent Events
 * Returns an async generator that yields stream chunks
 */
export async function* streamAgent(
  request: AgentExecuteRequest,
  signal?: AbortSignal
): AsyncGenerator<AgentStreamChunk, void, unknown> {
  const response = await fetch(`${apiClient.defaults.baseURL}/agents/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include', // Include cookies for authentication
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Agent stream failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');

      // Keep the last incomplete line in buffer
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data && data !== '[DONE]') {
            try {
              const chunk: AgentStreamChunk = JSON.parse(data);
              yield chunk;
            } catch (e) {
              console.warn('Failed to parse stream chunk:', data);
            }
          }
        }
      }
    }

    // Process any remaining data in buffer
    if (buffer.startsWith('data: ')) {
      const data = buffer.slice(6).trim();
      if (data && data !== '[DONE]') {
        try {
          const chunk: AgentStreamChunk = JSON.parse(data);
          yield chunk;
        } catch (e) {
          console.warn('Failed to parse final stream chunk:', data);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Get available agent types
 */
export async function getAgentTypes(): Promise<{ agent_types: AgentType[] }> {
  const response = await apiClient.get<{ agent_types: AgentType[] }>('/agents/types');
  return response.data;
}

/**
 * Get available tools
 */
export async function getAgentTools(): Promise<{ tools: ToolDefinition[] }> {
  const response = await apiClient.get<{ tools: ToolDefinition[] }>('/agents/tools');
  return response.data;
}

/**
 * Classify a task to determine the best agent type
 */
export async function classifyTask(task: string): Promise<ClassifyTaskResponse> {
  const response = await apiClient.post<ClassifyTaskResponse>('/agents/classify', { task });
  return response.data;
}

/**
 * Check agent system health
 */
export async function checkAgentHealth(): Promise<AgentHealthResponse> {
  const response = await apiClient.get<AgentHealthResponse>('/agents/health');
  return response.data;
}

// =============================================================================
// Exports
// =============================================================================

export const agentApi = {
  execute: executeAgent,
  stream: streamAgent,
  getTypes: getAgentTypes,
  getTools: getAgentTools,
  classify: classifyTask,
  health: checkAgentHealth,
};

export default agentApi;
