/**
 * Session Restore Modal Component
 *
 * Modal dialog shown on login to offer restoration of previous session.
 * Part of the Agent-Driven RAG system for session persistence.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { Clock, X, RefreshCw, PlayCircle, FileText, Folder } from 'lucide-react';
import {
  checkSessionRestore,
  restoreSession,
  type SessionState,
} from '../api/agent-navigation.api';
import './SessionRestoreModal.css';

// ============================================================================
// Types
// ============================================================================

export interface SessionRestoreModalProps {
  /** Whether to check for session on mount */
  autoCheck?: boolean;
  /** Maximum session age in hours */
  maxAgeHours?: number;
  /** Callback when session is restored */
  onRestore?: (session: SessionState) => void;
  /** Callback when user dismisses */
  onDismiss?: () => void;
  /** Translation function */
  t: (key: string) => string;
}

// ============================================================================
// Component
// ============================================================================

export const SessionRestoreModal: React.FC<SessionRestoreModalProps> = ({
  autoCheck = true,
  maxAgeHours = 24,
  onRestore,
  onDismiss,
  t,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [session, setSession] = useState<SessionState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  // Check for restorable session on mount
  useEffect(() => {
    if (autoCheck) {
      checkSession();
    }
  }, [autoCheck]);

  // Check for session
  const checkSession = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await checkSessionRestore(maxAgeHours);
      if (response.data.can_restore) {
        setSession(response.data);
        setIsOpen(true);
      }
    } catch (err) {
      console.error('Failed to check session:', err);
    } finally {
      setIsLoading(false);
    }
  }, [maxAgeHours]);

  // Handle restore
  const handleRestore = useCallback(async () => {
    setIsRestoring(true);
    try {
      const response = await restoreSession(true);
      if (response.data.restored && response.data.session) {
        onRestore?.(response.data.session);
      }
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to restore session:', err);
    } finally {
      setIsRestoring(false);
    }
  }, [onRestore]);

  // Handle dismiss
  const handleDismiss = useCallback(async () => {
    try {
      await restoreSession(false);
    } catch (err) {
      console.error('Failed to dismiss session:', err);
    }
    setIsOpen(false);
    onDismiss?.();
  }, [onDismiss]);

  // Format time ago
  const formatTimeAgo = (hours: number): string => {
    if (hours < 1) {
      const minutes = Math.round(hours * 60);
      return `${minutes} ${t('agentNav.minutesAgo') || 'minutes ago'}`;
    } else if (hours < 24) {
      const h = Math.round(hours);
      return `${h} ${t('agentNav.hoursAgo') || 'hours ago'}`;
    } else {
      const days = Math.round(hours / 24);
      return `${days} ${t('agentNav.daysAgo') || 'days ago'}`;
    }
  };

  // Don't render if not open
  if (!isOpen || !session) return null;

  return (
    <div className="session-restore-overlay" onClick={handleDismiss}>
      <div className="session-restore-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="session-restore-header">
          <div className="session-restore-title">
            <Clock size={20} />
            <h3>{t('agentNav.restoreSession') || 'Restore Previous Session'}</h3>
          </div>
          <button className="session-restore-close" onClick={handleDismiss}>
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="session-restore-body">
          <div className="session-restore-time">
            <RefreshCw size={16} />
            <span>{formatTimeAgo(session.age_hours)}</span>
          </div>

          <div className="session-restore-query">
            <span className="session-restore-query-label">
              {t('agentNav.lastQuery') || 'Last Query'}:
            </span>
            <span className="session-restore-query-text">"{session.last_query}"</span>
          </div>

          {session.selected_scope && (
            <div className="session-restore-scope">
              <span className="session-restore-scope-label">
                {t('agentNav.searchScope') || 'Search Scope'}:
              </span>
              <div className="session-restore-scope-items">
                {session.selected_scope.documents &&
                  session.selected_scope.documents.length > 0 && (
                    <div className="session-restore-scope-item">
                      <Folder size={14} />
                      <span>
                        {session.selected_scope.documents.length}{' '}
                        {t('agentNav.documents') || 'documents'}
                      </span>
                    </div>
                  )}
                {session.selected_scope.sections &&
                  session.selected_scope.sections.length > 0 && (
                    <div className="session-restore-scope-item">
                      <FileText size={14} />
                      <span>
                        {session.selected_scope.sections.length}{' '}
                        {t('agentNav.sections') || 'sections'}
                      </span>
                    </div>
                  )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="session-restore-footer">
          <button className="session-restore-dismiss-btn" onClick={handleDismiss}>
            {t('agentNav.startFresh') || 'Start Fresh'}
          </button>
          <button
            className="session-restore-continue-btn"
            onClick={handleRestore}
            disabled={isRestoring}
          >
            {isRestoring ? (
              <>
                <RefreshCw size={16} className="spin" />
                {t('agentNav.restoring') || 'Restoring...'}
              </>
            ) : (
              <>
                <PlayCircle size={16} />
                {t('agentNav.continue') || 'Continue'}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SessionRestoreModal;
