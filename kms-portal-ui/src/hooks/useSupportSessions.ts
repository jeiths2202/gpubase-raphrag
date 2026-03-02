/**
 * useSupportSessions Hook
 *
 * Dashboard-level poller (5s interval) that fetches sessions
 * and triggers browser notifications on new waiting requests.
 */

import { useEffect, useRef, useCallback } from 'react';
import { premiumSupportApi } from '../api/premium-support.api';
import { useSupportStore } from '../store/supportStore';

const POLL_INTERVAL = 5000; // 5 seconds

export function useSupportSessions() {
  const { sessions, waitingCount, activeCount, setSessions, setIsPolling } = useSupportStore();
  const prevWaitingRef = useRef(waitingCount);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      const response = await premiumSupportApi.getSessions();
      const data = Array.isArray(response.data) ? response.data : (response as any).data?.data ?? [];
      setSessions(data);
    } catch (err) {
      console.warn('[SupportSessions] Failed to fetch sessions:', err);
    }
  }, [setSessions]);

  // Trigger browser notification when waiting count increases
  useEffect(() => {
    const prev = prevWaitingRef.current;
    if (waitingCount > prev && prev >= 0) {
      const newCount = waitingCount - prev;
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('New Support Request', {
          body: `${newCount} new support request${newCount > 1 ? 's' : ''} waiting`,
          icon: '/tmax-logo.png',
          tag: 'support-request',
        });
      }
    }
    prevWaitingRef.current = waitingCount;
  }, [waitingCount]);

  // Start polling on mount, stop on unmount
  useEffect(() => {
    setIsPolling(true);
    fetchSessions();

    intervalRef.current = setInterval(fetchSessions, POLL_INTERVAL);

    return () => {
      setIsPolling(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchSessions, setIsPolling]);

  return { sessions, waitingCount, activeCount, refresh: fetchSessions };
}
