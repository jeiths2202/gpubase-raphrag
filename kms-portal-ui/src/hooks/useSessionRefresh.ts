/**
 * useSessionRefresh Hook
 *
 * Handles automatic session refresh and token renewal.
 * Works with the API client interceptor for seamless token management.
 *
 * Features:
 * - Periodic background session validation
 * - Manual refresh trigger
 * - Activity-based refresh (refresh on user activity)
 * - Visibility-based refresh (refresh when tab becomes visible)
 */

import { useEffect, useCallback, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import { refreshToken } from '../api';

// =============================================================================
// Types
// =============================================================================

export interface UseSessionRefreshOptions {
  /**
   * Enable periodic refresh
   * @default true
   */
  enabled?: boolean;

  /**
   * Interval for periodic refresh in milliseconds
   * @default 240000 (4 minutes - before typical 5 min token expiry)
   */
  interval?: number;

  /**
   * Refresh when tab becomes visible after being hidden
   * @default true
   */
  refreshOnVisibility?: boolean;

  /**
   * Refresh on user activity (mouse move, keypress, etc.)
   * Only triggers refresh if last refresh was more than `activityThreshold` ago
   * @default false
   */
  refreshOnActivity?: boolean;

  /**
   * Minimum time between activity-based refreshes in milliseconds
   * @default 60000 (1 minute)
   */
  activityThreshold?: number;

  /**
   * Callback when session refresh fails
   */
  onRefreshError?: (error: Error) => void;

  /**
   * Callback when session is successfully refreshed
   */
  onRefreshSuccess?: () => void;
}

export interface UseSessionRefreshReturn {
  /**
   * Manually trigger a session refresh
   */
  refresh: () => Promise<boolean>;

  /**
   * Whether a refresh is currently in progress
   */
  isRefreshing: boolean;

  /**
   * Last successful refresh timestamp
   */
  lastRefreshAt: number | null;

  /**
   * Time until next scheduled refresh (ms)
   */
  nextRefreshIn: number | null;
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useSessionRefresh(
  options: UseSessionRefreshOptions = {}
): UseSessionRefreshReturn {
  const {
    enabled = true,
    interval = 4 * 60 * 1000, // 4 minutes
    refreshOnVisibility = true,
    refreshOnActivity = false,
    activityThreshold = 60 * 1000, // 1 minute
    onRefreshError,
    onRefreshSuccess,
  } = options;

  const { isAuthenticated, logout } = useAuthStore();

  // Refs for tracking state
  const isRefreshingRef = useRef(false);
  const lastRefreshAtRef = useRef<number | null>(null);
  const nextRefreshTimeRef = useRef<number | null>(null);
  const intervalIdRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ==========================================================================
  // Refresh Function
  // ==========================================================================
  const refresh = useCallback(async (): Promise<boolean> => {
    if (isRefreshingRef.current || !isAuthenticated) {
      return false;
    }

    isRefreshingRef.current = true;

    try {
      await refreshToken();
      lastRefreshAtRef.current = Date.now();
      onRefreshSuccess?.();
      return true;
    } catch (error) {
      console.debug('[SessionRefresh] Refresh failed:', error);
      onRefreshError?.(error instanceof Error ? error : new Error('Refresh failed'));

      // If refresh fails, the API client interceptor will handle logout
      // But we can also trigger it here for immediate feedback
      if (error instanceof Error && error.message.includes('401')) {
        await logout();
      }

      return false;
    } finally {
      isRefreshingRef.current = false;
    }
  }, [isAuthenticated, logout, onRefreshError, onRefreshSuccess]);

  // ==========================================================================
  // Periodic Refresh
  // ==========================================================================
  useEffect(() => {
    if (!enabled || !isAuthenticated) {
      if (intervalIdRef.current) {
        clearInterval(intervalIdRef.current);
        intervalIdRef.current = null;
      }
      nextRefreshTimeRef.current = null;
      return;
    }

    // Schedule periodic refresh
    const scheduleRefresh = () => {
      nextRefreshTimeRef.current = Date.now() + interval;
      intervalIdRef.current = setInterval(() => {
        refresh();
        nextRefreshTimeRef.current = Date.now() + interval;
      }, interval);
    };

    scheduleRefresh();

    return () => {
      if (intervalIdRef.current) {
        clearInterval(intervalIdRef.current);
        intervalIdRef.current = null;
      }
    };
  }, [enabled, isAuthenticated, interval, refresh]);

  // ==========================================================================
  // Visibility Change Handler
  // ==========================================================================
  useEffect(() => {
    if (!refreshOnVisibility || !isAuthenticated) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Tab became visible - check if we should refresh
        const timeSinceLastRefresh = lastRefreshAtRef.current
          ? Date.now() - lastRefreshAtRef.current
          : Infinity;

        // Refresh if it's been more than half the interval since last refresh
        if (timeSinceLastRefresh > interval / 2) {
          refresh();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [refreshOnVisibility, isAuthenticated, interval, refresh]);

  // ==========================================================================
  // Activity-based Refresh
  // ==========================================================================
  useEffect(() => {
    if (!refreshOnActivity || !isAuthenticated) {
      return;
    }

    let activityTimeout: ReturnType<typeof setTimeout> | null = null;

    const handleActivity = () => {
      // Debounce activity events
      if (activityTimeout) {
        clearTimeout(activityTimeout);
      }

      activityTimeout = setTimeout(() => {
        const timeSinceLastRefresh = lastRefreshAtRef.current
          ? Date.now() - lastRefreshAtRef.current
          : Infinity;

        if (timeSinceLastRefresh > activityThreshold) {
          refresh();
        }
      }, 1000); // 1 second debounce
    };

    const events = ['mousedown', 'keydown', 'touchstart', 'scroll'];
    events.forEach((event) => {
      window.addEventListener(event, handleActivity, { passive: true });
    });

    return () => {
      if (activityTimeout) {
        clearTimeout(activityTimeout);
      }
      events.forEach((event) => {
        window.removeEventListener(event, handleActivity);
      });
    };
  }, [refreshOnActivity, isAuthenticated, activityThreshold, refresh]);

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    refresh,
    isRefreshing: isRefreshingRef.current,
    lastRefreshAt: lastRefreshAtRef.current,
    nextRefreshIn: nextRefreshTimeRef.current
      ? Math.max(0, nextRefreshTimeRef.current - Date.now())
      : null,
  };
}

export default useSessionRefresh;
