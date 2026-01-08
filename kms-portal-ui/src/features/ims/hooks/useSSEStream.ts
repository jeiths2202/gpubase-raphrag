/**
 * SSE Stream Hook
 *
 * Manages Server-Sent Events connections with auto-reconnection
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import type { SSEEventData } from '../types';

interface UseSSEStreamOptions {
  autoConnect?: boolean;
  maxReconnectAttempts?: number;
  reconnectDelay?: number;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

interface UseSSEStreamReturn {
  data: SSEEventData | null;
  events: SSEEventData[];
  isConnected: boolean;
  isReconnecting: boolean;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  clearEvents: () => void;
}

// Terminal events that should auto-disconnect
const TERMINAL_EVENTS = ['job_completed', 'job_failed', 'cancelled'];

export function useSSEStream(
  url: string | null,
  options: UseSSEStreamOptions = {}
): UseSSEStreamReturn {
  const {
    autoConnect = true,
    maxReconnectAttempts = 3,
    reconnectDelay = 2000,
    onOpen,
    onClose,
    onError,
  } = options;

  const [data, setData] = useState<SSEEventData | null>(null);
  const [events, setEvents] = useState<SSEEventData[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(true);
  const isTerminatedRef = useRef(false);

  /**
   * Disconnect from SSE stream
   */
  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setIsConnected(false);
    setIsReconnecting(false);
    onClose?.();
  }, [onClose]);

  /**
   * Connect to SSE stream
   */
  const connect = useCallback(() => {
    if (!url) return;

    // Clean up existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    shouldReconnectRef.current = true;
    isTerminatedRef.current = false;
    setError(null);

    try {
      const eventSource = new EventSource(url, { withCredentials: true });
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setIsReconnecting(false);
        setError(null);
        reconnectAttemptsRef.current = 0;
        onOpen?.();
      };

      eventSource.onmessage = (event) => {
        try {
          const eventData: SSEEventData = JSON.parse(event.data);
          setData(eventData);
          setEvents((prev) => [...prev, eventData]);

          // Auto-disconnect on terminal events
          if (eventData.event && TERMINAL_EVENTS.includes(eventData.event)) {
            isTerminatedRef.current = true;
            disconnect();
          }
        } catch (e) {
          console.error('[SSE] Failed to parse event data:', e);
        }
      };

      eventSource.onerror = (event) => {
        setIsConnected(false);
        onError?.(event);

        // Don't reconnect if terminated normally
        if (isTerminatedRef.current) {
          return;
        }

        // Attempt reconnection
        if (
          shouldReconnectRef.current &&
          reconnectAttemptsRef.current < maxReconnectAttempts
        ) {
          setIsReconnecting(true);
          reconnectAttemptsRef.current += 1;

          const delay = reconnectDelay * reconnectAttemptsRef.current;
          console.log(
            `[SSE] Reconnecting in ${delay}ms (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`
          );

          reconnectTimeoutRef.current = setTimeout(() => {
            if (shouldReconnectRef.current) {
              connect();
            }
          }, delay);
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          setError(`Connection failed after ${maxReconnectAttempts} attempts`);
          setIsReconnecting(false);
          disconnect();
        }
      };
    } catch (e) {
      setError(`Failed to create EventSource: ${e}`);
      setIsConnected(false);
    }
  }, [url, maxReconnectAttempts, reconnectDelay, onOpen, onClose, onError, disconnect]);

  /**
   * Clear event history
   */
  const clearEvents = useCallback(() => {
    setEvents([]);
    setData(null);
  }, []);

  // Auto-connect on mount if enabled and URL provided
  useEffect(() => {
    if (autoConnect && url) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [url, autoConnect, connect, disconnect]);

  return {
    data,
    events,
    isConnected,
    isReconnecting,
    error,
    connect,
    disconnect,
    clearEvents,
  };
}

export default useSSEStream;
