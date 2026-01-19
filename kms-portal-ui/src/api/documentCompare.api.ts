/**
 * Document Comparison API
 * API client for comparing multiple documents on a specific topic
 */

import client from './client';

// =============================================================================
// Types
// =============================================================================

export interface DocumentCompareRequest {
  document_ids: string[];
  topic: string;
  language?: string;
}

export interface DocumentSection {
  section_path?: string;
  section_title?: string;
  content: string;
  page_number?: number;
  score: number;
  chunk_id?: string;
}

export interface DocumentCompareResult {
  doc_id: string;
  doc_name: string;
  relevant_sections: DocumentSection[];
  has_content: boolean;
}

export interface ComparisonDifference {
  aspect: string;
  documents: Record<string, string>;
}

export interface ComparisonSummary {
  topic: string;
  documents: DocumentCompareResult[];
  summary: string;
  commonalities: string[];
  differences: ComparisonDifference[];
  language: string;
}

export interface CompareStreamChunk {
  type: 'compare_start' | 'document_start' | 'document_result' | 'summary_start' | 'compare_done' | 'error';
  data: Record<string, unknown>;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Compare multiple documents on a specific topic
 */
export async function compareDocuments(
  documentIds: string[],
  topic: string,
  language: string = 'auto'
): Promise<ComparisonSummary> {
  const response = await client.post<{ data: ComparisonSummary }>('/documents/compare', {
    document_ids: documentIds,
    topic,
    language,
  });
  return response.data.data;
}

/**
 * Stream document comparison results
 */
export async function* streamCompareDocuments(
  documentIds: string[],
  topic: string,
  language: string = 'auto',
  signal?: AbortSignal
): AsyncGenerator<CompareStreamChunk> {
  const response = await fetch(`${import.meta.env.VITE_API_URL || ''}/api/v1/documents/compare/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      document_ids: documentIds,
      topic,
      language,
    }),
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
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
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data) {
            try {
              const chunk = JSON.parse(data) as CompareStreamChunk;
              yield chunk;
            } catch (e) {
              console.error('Failed to parse SSE data:', e, data);
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export const documentCompareApi = {
  compareDocuments,
  streamCompareDocuments,
};

export default documentCompareApi;
