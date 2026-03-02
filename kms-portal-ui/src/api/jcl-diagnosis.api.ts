/**
 * JCL Diagnosis API Client
 *
 * SSE streaming via fetch + ReadableStream (POST with multipart/form-data)
 * Report HTML via GET endpoint
 */

export interface DiagnosisEvent {
  type: string;
  [key: string]: unknown;
}

/**
 * Stream JCL diagnosis via SSE (multipart/form-data POST)
 */
export async function streamDiagnosis(
  file: File,
  language: string,
  message: string | undefined,
  onEvent: (event: DiagnosisEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('language', language);
  if (message) {
    formData.append('message', message);
  }

  const response = await fetch('/api/v1/jcl-diagnosis/analyze', {
    method: 'POST',
    body: formData,
    credentials: 'include',
    signal,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Diagnosis failed (${response.status}): ${text}`);
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
        onEvent(data as DiagnosisEvent);
      } catch {
        // skip malformed events
      }
    }
  }
}

/**
 * Get report URL for opening in new tab
 */
export function getReportUrl(diagnosisId: string): string {
  return `/api/v1/jcl-diagnosis/${diagnosisId}/report`;
}
