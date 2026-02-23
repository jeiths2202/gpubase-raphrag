/**
 * Agentic RAG API Client
 *
 * 제품별 Agent 기반 RAG 시스템 API
 */
import client from './client';

const BASE_URL = '/api/v1/agentic-rag';

export type AgentMode = 'rag' | 'code' | 'planner' | 'auto' | 'special';

export interface AgenticRAGRequest {
  message: string;
  product?: string;
  products?: string[];
  selected_product?: string;
  history?: Array<{ role: string; content: string }>;
  file_content?: string;
  language?: string;
  agent_mode?: AgentMode;
}

export interface ClarificationCandidate {
  product: string;
  confidence: number;
  reason: string;
  matched_keywords: string[];
}

export interface VerifiedSentence {
  text: string;
  level: 'verified' | 'inferred' | 'unverified';
  similarity: number;
  source_chunk?: string;
  source_doc?: string;
}

export interface SSEEvent {
  type: string;
  [key: string]: unknown;
}

// Product tree types
export interface ProductVersion {
  product_id: string;
  version: string;
  doc_version: string;
  language: string;
  pdf_count: number;
}

export interface ProductGroup {
  name: string;
  versions: ProductVersion[];
}

export interface ProductsResponse {
  success: boolean;
  products: ProductGroup[];
  special: Array<{ id: string; name: string }>;
}

export const agenticRagApi = {
  health: () => client.get(`${BASE_URL}/health`),

  products: () => client.get(`${BASE_URL}/products`),

  classify: (query: string, language?: string) =>
    client.post(`${BASE_URL}/classify`, { query, language }),

  chat: (request: AgenticRAGRequest) =>
    client.post(`${BASE_URL}/chat`, request),

  /**
   * SSE 스트리밍 채팅 - fetch API 직접 사용
   */
  streamChat: async function* (
    request: AgenticRAGRequest,
    token: string,
  ): AsyncGenerator<SSEEvent> {
    const response = await fetch(`${BASE_URL}/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`Stream failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(trimmed.slice(6));
          yield data as SSEEvent;
        } catch {
          // skip malformed events
        }
      }
    }
  },
};
