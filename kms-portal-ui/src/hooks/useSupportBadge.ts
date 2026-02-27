/**
 * useSupportBadge Hook
 *
 * Lightweight header badge poller (15s interval) for senior+ roles.
 * Skips if dashboard's 5s poller is already running.
 */

import { useEffect, useRef, useCallback } from 'react';
import { premiumSupportApi } from '../api/premium-support.api';
import { useSupportStore } from '../store/supportStore';
import { useAuthStore } from '../store/authStore';

const BADGE_POLL_INTERVAL = 15000; // 15 seconds

const ROLE_HIERARCHY: Record<string, number> = {
  admin: 5,
  leader: 4,
  senior: 3,
  user: 2,
  guest: 1,
};

export function useSupportBadge() {
  const { isPolling, setSessions } = useSupportStore();
  const user = useAuthStore((s) => s.user);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isSeniorPlus = user ? (ROLE_HIERARCHY[user.role] ?? 1) >= 3 : false;

  const fetchCount = useCallback(async () => {
    try {
      const response = await premiumSupportApi.getSessions();
      const data = Array.isArray(response.data) ? response.data : (response as any).data?.data ?? [];
      setSessions(data);
    } catch {
      // Silent fail for badge polling
    }
  }, [setSessions]);

  useEffect(() => {
    // Skip if not senior+ or if dashboard poller is already active
    if (!isSeniorPlus || isPolling) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    fetchCount();
    intervalRef.current = setInterval(fetchCount, BADGE_POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isSeniorPlus, isPolling, fetchCount]);
}
