/**
 * useAuth Hook
 *
 * Provides a clean interface for authentication functionality.
 * Combines auth store access with session management.
 *
 * Features:
 * - Session validation on mount (optional)
 * - Periodic session refresh (optional)
 * - Loading and initialized states
 * - Role-based access checks
 */

import { useEffect, useCallback, useRef } from 'react';
import { useAuthStore, type User } from '../store/authStore';
import type { UserRole } from '../api';

// =============================================================================
// Types
// =============================================================================

export interface UseAuthOptions {
  /**
   * Validate session on mount
   * @default true
   */
  validateOnMount?: boolean;

  /**
   * Enable periodic session refresh
   * @default false
   */
  enablePeriodicRefresh?: boolean;

  /**
   * Interval for periodic refresh in milliseconds
   * @default 300000 (5 minutes)
   */
  refreshInterval?: number;
}

export interface UseAuthReturn {
  // State
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  error: string | null;

  // Actions
  login: (userId: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<boolean>;
  clearError: () => void;

  // Helpers
  hasRole: (requiredRole: UserRole) => boolean;
  isAdmin: boolean;
}

// =============================================================================
// Role Hierarchy
// =============================================================================

const ROLE_HIERARCHY: Record<UserRole, number> = {
  admin: 5,
  leader: 4,
  senior: 3,
  user: 2,
  guest: 1,
};

// =============================================================================
// Hook Implementation
// =============================================================================

export function useAuth(options: UseAuthOptions = {}): UseAuthReturn {
  const {
    validateOnMount = true,
    enablePeriodicRefresh = false,
    refreshInterval = 5 * 60 * 1000, // 5 minutes
  } = options;

  // Auth store
  const {
    user,
    isAuthenticated,
    isLoading,
    isInitialized,
    error,
    login,
    logout,
    checkAuth,
    clearError,
    setInitialized,
  } = useAuthStore();

  // Track if we've already validated
  const hasValidated = useRef(false);

  // ==========================================================================
  // Session Validation on Mount
  // ==========================================================================
  useEffect(() => {
    if (!validateOnMount || hasValidated.current || isInitialized) {
      return;
    }

    hasValidated.current = true;

    // Only validate if we think we're authenticated (from persisted state)
    // or if we haven't initialized yet
    if (isAuthenticated || !isInitialized) {
      checkAuth().catch(() => {
        // Error handled in store
      });
    } else {
      // Not authenticated and not initialized - just mark as initialized
      setInitialized(true);
    }
  }, [validateOnMount, isAuthenticated, isInitialized, checkAuth, setInitialized]);

  // ==========================================================================
  // Periodic Session Refresh
  // ==========================================================================
  useEffect(() => {
    if (!enablePeriodicRefresh || !isAuthenticated) {
      return;
    }

    const intervalId = setInterval(() => {
      // Silently check auth in background
      checkAuth().catch(() => {
        // Error handled in store - will trigger logout if session expired
      });
    }, refreshInterval);

    return () => clearInterval(intervalId);
  }, [enablePeriodicRefresh, refreshInterval, isAuthenticated, checkAuth]);

  // ==========================================================================
  // Role Check Helper
  // ==========================================================================
  const hasRole = useCallback(
    (requiredRole: UserRole): boolean => {
      if (!user) return false;

      const userLevel = ROLE_HIERARCHY[user.role] ?? 1;
      const requiredLevel = ROLE_HIERARCHY[requiredRole] ?? 1;

      return userLevel >= requiredLevel;
    },
    [user]
  );

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    // State
    user,
    isAuthenticated,
    isLoading,
    isInitialized,
    error,

    // Actions
    login,
    logout,
    checkAuth,
    clearError,

    // Helpers
    hasRole,
    isAdmin: user?.role === 'admin',
  };
}

// =============================================================================
// Convenience Hooks
// =============================================================================

/**
 * Hook to check if user has required role
 */
export function useRequireRole(requiredRole: UserRole): {
  hasAccess: boolean;
  isLoading: boolean;
} {
  const { user, isLoading, isInitialized } = useAuth({ validateOnMount: false });

  if (!isInitialized || isLoading) {
    return { hasAccess: false, isLoading: true };
  }

  if (!user) {
    return { hasAccess: false, isLoading: false };
  }

  const userLevel = ROLE_HIERARCHY[user.role] ?? 1;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] ?? 1;

  return {
    hasAccess: userLevel >= requiredLevel,
    isLoading: false,
  };
}

/**
 * Hook to check if user is admin
 */
export function useIsAdmin(): boolean {
  const { user } = useAuth({ validateOnMount: false });
  return user?.role === 'admin';
}

export default useAuth;
