/**
 * useSessionRestore Hook
 *
 * Handles session restoration flow for Agent-Driven RAG system.
 * Checks for previous session on login and offers to restore it.
 *
 * Features:
 * - Auto-check for restorable session on mount
 * - Session state management (query, scope, conversation)
 * - Restore/dismiss handlers
 * - Integration with agent navigation API
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../store/authStore';
import {
  checkSessionRestore,
  restoreSession,
  type SessionState,
} from '../api/agent-navigation.api';

// =============================================================================
// Types
// =============================================================================

export interface UseSessionRestoreOptions {
  /**
   * Whether to auto-check for restorable session on mount
   * @default true
   */
  autoCheck?: boolean;

  /**
   * Maximum session age in hours for restoration
   * @default 24
   */
  maxAgeHours?: number;

  /**
   * Callback when session is successfully restored
   */
  onRestore?: (session: SessionState) => void;

  /**
   * Callback when user dismisses the restore modal
   */
  onDismiss?: () => void;

  /**
   * Callback when restore check or restore operation fails
   */
  onError?: (error: Error) => void;
}

export interface UseSessionRestoreReturn {
  /**
   * Whether the restore modal should be shown
   */
  isOpen: boolean;

  /**
   * The session state available for restoration
   */
  session: SessionState | null;

  /**
   * Whether initial session check is in progress
   */
  isLoading: boolean;

  /**
   * Whether session restore is in progress
   */
  isRestoring: boolean;

  /**
   * Manually trigger session check
   */
  checkSession: () => Promise<void>;

  /**
   * Handle restore action
   */
  handleRestore: () => Promise<void>;

  /**
   * Handle dismiss action (start fresh)
   */
  handleDismiss: () => Promise<void>;

  /**
   * Close the modal without any action
   */
  close: () => void;
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useSessionRestore(
  options: UseSessionRestoreOptions = {}
): UseSessionRestoreReturn {
  const {
    autoCheck = true,
    maxAgeHours = 24,
    onRestore,
    onDismiss,
    onError,
  } = options;

  const { isAuthenticated } = useAuthStore();

  // State
  const [isOpen, setIsOpen] = useState(false);
  const [session, setSession] = useState<SessionState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  // Refs to prevent double-checking
  const hasCheckedRef = useRef(false);
  const isMountedRef = useRef(true);

  // ==========================================================================
  // Check Session
  // ==========================================================================
  const checkSession = useCallback(async () => {
    if (!isAuthenticated) {
      return;
    }

    setIsLoading(true);

    try {
      const response = await checkSessionRestore(maxAgeHours);

      if (!isMountedRef.current) return;

      if (response.data.can_restore) {
        setSession(response.data);
        setIsOpen(true);
      }
    } catch (err) {
      console.error('[SessionRestore] Failed to check session:', err);
      onError?.(err instanceof Error ? err : new Error('Failed to check session'));
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false);
      }
    }
  }, [isAuthenticated, maxAgeHours, onError]);

  // ==========================================================================
  // Handle Restore
  // ==========================================================================
  const handleRestore = useCallback(async () => {
    setIsRestoring(true);

    try {
      const response = await restoreSession(true);

      if (!isMountedRef.current) return;

      if (response.data.restored && response.data.session) {
        onRestore?.(response.data.session);
      }

      setIsOpen(false);
      setSession(null);
    } catch (err) {
      console.error('[SessionRestore] Failed to restore session:', err);
      onError?.(err instanceof Error ? err : new Error('Failed to restore session'));
    } finally {
      if (isMountedRef.current) {
        setIsRestoring(false);
      }
    }
  }, [onRestore, onError]);

  // ==========================================================================
  // Handle Dismiss
  // ==========================================================================
  const handleDismiss = useCallback(async () => {
    try {
      // Notify backend that user declined restore
      await restoreSession(false);
    } catch (err) {
      console.error('[SessionRestore] Failed to dismiss session:', err);
      // Don't block dismiss on error
    }

    if (isMountedRef.current) {
      setIsOpen(false);
      setSession(null);
      onDismiss?.();
    }
  }, [onDismiss]);

  // ==========================================================================
  // Close without action
  // ==========================================================================
  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  // ==========================================================================
  // Auto-check on mount (when authenticated)
  // ==========================================================================
  useEffect(() => {
    isMountedRef.current = true;

    if (autoCheck && isAuthenticated && !hasCheckedRef.current) {
      hasCheckedRef.current = true;
      checkSession();
    }

    return () => {
      isMountedRef.current = false;
    };
  }, [autoCheck, isAuthenticated, checkSession]);

  // Reset check flag when user logs out
  useEffect(() => {
    if (!isAuthenticated) {
      hasCheckedRef.current = false;
      setIsOpen(false);
      setSession(null);
    }
  }, [isAuthenticated]);

  // ==========================================================================
  // Return
  // ==========================================================================
  return {
    isOpen,
    session,
    isLoading,
    isRestoring,
    checkSession,
    handleRestore,
    handleDismiss,
    close,
  };
}

export default useSessionRestore;
