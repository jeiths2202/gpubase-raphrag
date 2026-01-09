/**
 * AuthProvider Component
 *
 * Provides authentication context to the application with:
 * - Session validation on mount
 * - Automatic session refresh
 * - Authentication state management
 */

import React, { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useSessionRefresh } from '../hooks/useSessionRefresh';

interface AuthProviderProps {
  children: React.ReactNode;

  /**
   * Enable automatic session refresh
   * @default true
   */
  enableAutoRefresh?: boolean;

  /**
   * Session refresh interval in milliseconds
   * @default 240000 (4 minutes)
   */
  refreshInterval?: number;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({
  children,
  enableAutoRefresh = true,
  refreshInterval = 4 * 60 * 1000,
}) => {
  const { isAuthenticated, isInitialized, checkAuth, setInitialized } = useAuthStore();

  // Session refresh hook
  useSessionRefresh({
    enabled: enableAutoRefresh && isAuthenticated,
    interval: refreshInterval,
    refreshOnVisibility: true,
    onRefreshError: (error) => {
      console.debug('[AuthProvider] Session refresh failed:', error.message);
    },
  });

  // Validate session on mount
  useEffect(() => {
    const validateSession = async () => {
      if (isInitialized) {
        return;
      }

      // If we have persisted auth state, validate it
      if (isAuthenticated) {
        try {
          await checkAuth();
        } catch (error) {
          console.debug('[AuthProvider] Session validation failed:', error);
          // Error is handled by the store (logout if session expired)
        }
      } else {
        // Not authenticated - just mark as initialized
        setInitialized(true);
      }
    };

    validateSession();
  }, [isAuthenticated, isInitialized, checkAuth, setInitialized]);

  return <>{children}</>;
};

export default AuthProvider;
