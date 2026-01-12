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
export type AgentType = 'auto' | 'rag' | 'ims' | 'vision' | 'code' | 'planner';

/**
 * Agent execution request
 */
export interface AgentExecuteRequest {
  task: string;
  agent_type?: AgentType;
  session_id?: string;
  max_steps?: number;
  language?: 'auto' | 'en' | 'ko' | 'ja';
  file_context?: string;  // Attached file content for RAG priority context
  url_context?: string;   // URL to fetch and use as RAG context
  ui_context?: UIContext; // UI context for context-aware AI responses
  use_deep_agent?: boolean; // Use Deep Agents framework for execution
}

/**
 * UI Context for context-aware AI (matches backend UIContext model)
 */
export interface UIContext {
  current_page: string;
  page_title: string;
  page_metadata?: Record<string, unknown>;
  selected_item?: {
    type: string;
    id: string;
    title: string;
    content?: string;
    summary?: string;
    metadata?: Record<string, unknown>;
  };
  visible_components: string[];
  language: 'en' | 'ko' | 'ja';
  theme: 'light' | 'dark';
  user_permission_scope: 'admin' | 'user';
  captured_at?: string;
}

/**
 * URL fetch response
 */
export interface FetchUrlResponse {
  url: string;
  title: string | null;
  content: string;
  char_count: number;
  word_count: number;
  success: boolean;
  error: string | null;
  warning: string | null;  // Set when URL was redirected to a different page
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
 * Artifact types
 */
export type ArtifactType = 'code' | 'text' | 'markdown' | 'html' | 'json' | 'diff' | 'log' | 'image';

/**
 * Artifact language for code highlighting
 */
export type ArtifactLanguage =
  | 'python' | 'javascript' | 'typescript' | 'java' | 'go' | 'rust'
  | 'c' | 'cpp' | 'csharp' | 'ruby' | 'php' | 'swift' | 'kotlin'
  | 'sql' | 'bash' | 'powershell' | 'batch'
  | 'html' | 'css' | 'scss'
  | 'json' | 'yaml' | 'xml' | 'toml'
  | 'markdown' | 'text' | 'plaintext'
  | 'docker' | 'dockerfile'
  | 'diff' | 'patch';

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
  | 'done'
  | 'status'
  | 'artifact'
  // Enterprise multi-agent orchestration chunk types
  | 'orchestration_start'
  | 'dag_created'
  | 'batch_start'
  | 'agent_start'
  | 'agent_chunk'
  | 'agent_done'
  | 'batch_done'
  | 'evaluation'
  | 'retry'
  | 'synthesis'
  | 'next_actions';

/**
 * Trace data for DAG visualization (enterprise multi-agent)
 */
export interface StreamTraceData {
  trace_id?: string;
  dag?: {
    tasks: Array<{
      task_id: string;
      description: string;
      agent_type: string;
      status: string;
      dependencies: string[];
      start_time?: string;
      end_time?: string;
      latency_ms?: number;
      error?: string;
    }>;
    execution_batches: string[][];
    parallelism_type: string;
  };
  current_task?: {
    task_id: string;
    status: string;
    start_time?: string;
    end_time?: string;
    latency_ms?: number;
    error?: string;
  };
  timeline_event?: {
    event: string;
    task_id?: string;
    agent_type?: string;
    timestamp: string;
    success?: boolean;
    latency_ms?: number;
    error?: string;
    data?: Record<string, unknown>;
  };
  evaluations?: Record<string, {
    passed: boolean;
    score?: number;
    issues: string[];
    retry_recommended?: boolean;
    retry_reason?: string;
  }>;
}

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

  // Artifact-specific fields
  artifact_id?: string;
  artifact_type?: ArtifactType;
  artifact_title?: string;
  artifact_language?: ArtifactLanguage;

  // Enterprise multi-agent trace data
  trace_data?: StreamTraceData;
  task_id?: string;  // Task ID for enterprise multi-agent
  agent_type?: AgentType;  // Agent type for enterprise multi-agent
  agent_chunk?: AgentStreamChunk;  // Nested chunk from sub-agent
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
 *
 * Note: For 'planner' agent type, uses the enterprise/stream endpoint
 * which enables multi-agent orchestration with DAG visualization.
 */
export async function* streamAgent(
  request: AgentExecuteRequest,
  signal?: AbortSignal
): AsyncGenerator<AgentStreamChunk, void, unknown> {
  // Use enterprise endpoint for planner agent (enables DAG + multi-agent orchestration)
  const isEnterprise = request.agent_type === 'planner';
  const endpoint = isEnterprise ? '/agents/enterprise/stream' : '/agents/stream';

  // For enterprise endpoint:
  // - If use_deep_agent is true, disable multi-agent to use Deep Agent directly
  // - Otherwise, enable multi-agent orchestration for DAG visualization
  const enableMultiAgent = isEnterprise && !request.use_deep_agent;
  const requestBody = isEnterprise
    ? { ...request, enable_multi_agent: enableMultiAgent }
    : request;

  const response = await fetch(`${apiClient.defaults.baseURL}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include', // Include cookies for authentication
    body: JSON.stringify(requestBody),
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

/**
 * Fetch URL content for RAG context
 * Extracts readable text from a webpage
 */
export async function fetchUrlContent(url: string): Promise<FetchUrlResponse> {
  const response = await apiClient.post<FetchUrlResponse>('/agents/fetch-url', { url });
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
  fetchUrl: fetchUrlContent,
};

export default agentApi;
