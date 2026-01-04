/**
 * useSSEStream - Server-Sent Events (SSE) React Hook
 *
 * Manages SSE connections with automatic reconnection and error handling.
 */

import { useEffect, useRef, useState, useCallback } from 'react';

export interface SSEEvent {
  event: string;
  [key: string]: any;
}

export interface UseSSEStreamOptions {
  /**
   * Whether to automatically connect on mount
   */
  autoConnect?: boolean;

  /**
   * Maximum number of reconnection attempts
   */
  maxReconnectAttempts?: number;

  /**
   * Delay between reconnection attempts (ms)
   */
  reconnectDelay?: number;

  /**
   * Callback when connection opens
   */
  onOpen?: () => void;

  /**
   * Callback when connection closes
   */
  onClose?: () => void;

  /**
   * Callback when error occurs
   */
  onError?: (error: Event) => void;
}

export interface UseSSEStreamResult {
  /**
   * Latest event received from stream
   */
  data: SSEEvent | null;

  /**
   * All events received (historical)
   */
  events: SSEEvent[];

  /**
   * Current connection state
   */
  isConnected: boolean;

  /**
   * Whether currently attempting to reconnect
   */
  isReconnecting: boolean;

  /**
   * Latest error
   */
  error: string | null;

  /**
   * Manually connect to SSE stream
   */
  connect: () => void;

  /**
   * Manually disconnect from SSE stream
   */
  disconnect: () => void;

  /**
   * Clear event history
   */
  clearEvents: () => void;
}

/**
 * Hook for managing Server-Sent Events (SSE) connections
 *
 * @example
 * ```tsx
 * const { data, events, isConnected, connect, disconnect } = useSSEStream(
 *   '/api/v1/ims-jobs/123/stream',
 *   {
 *     autoConnect: true,
 *     onOpen: () => console.log('Connected'),
 *     onClose: () => console.log('Disconnected')
 *   }
 * );
 *
 * // Latest event
 * console.log(data);
 *
 * // All events history
 * console.log(events);
 * ```
 */
export function useSSEStream(
  url: string | null,
  options: UseSSEStreamOptions = {}
): UseSSEStreamResult {
  const {
    autoConnect = true,
    maxReconnectAttempts = 3,
    reconnectDelay = 2000,
    onOpen,
    onClose,
    onError
  } = options;

  const [data, setData] = useState<SSEEvent | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    clearReconnectTimeout();

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    reconnectAttemptsRef.current = 0;

    if (onClose) {
      onClose();
    }
  }, [clearReconnectTimeout, onClose]);

  const connect = useCallback(() => {
    if (!url) {
      setError('No URL provided');
      return;
    }

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    try {
      const eventSource = new EventSource(url, {
        withCredentials: true
      });

      eventSource.onopen = () => {
        setIsConnected(true);
        setIsReconnecting(false);
        setError(null);
        reconnectAttemptsRef.current = 0;

        if (onOpen) {
          onOpen();
        }
      };

      eventSource.onmessage = (event) => {
        try {
          const parsedData: SSEEvent = JSON.parse(event.data);

          setData(parsedData);
          setEvents(prev => [...prev, parsedData]);

          // Auto-disconnect on terminal events
          if (parsedData.event === 'job_completed' || parsedData.event === 'job_failed') {
            // Delay disconnect to ensure final event is processed
            setTimeout(() => {
              disconnect();
            }, 500);
          }
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
          setError('Failed to parse event data');
        }
      };

      eventSource.onerror = (event) => {
        console.error('SSE error:', event);

        setIsConnected(false);

        if (onError) {
          onError(event);
        }

        // Attempt reconnection if not max attempts
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          setIsReconnecting(true);
          reconnectAttemptsRef.current += 1;

          clearReconnectTimeout();
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(`Reconnecting... (attempt ${reconnectAttemptsRef.current})`);
            connect();
          }, reconnectDelay);
        } else {
          setError('Max reconnection attempts reached');
          disconnect();
        }
      };

      eventSourceRef.current = eventSource;

    } catch (err) {
      console.error('Failed to create EventSource:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsConnected(false);
    }
  }, [url, maxReconnectAttempts, reconnectDelay, disconnect, clearReconnectTimeout, onOpen, onError]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setData(null);
  }, []);

  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect && url) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url, autoConnect]); // Only re-run if URL or autoConnect changes

  return {
    data,
    events,
    isConnected,
    isReconnecting,
    error,
    connect,
    disconnect,
    clearEvents
  };
}
