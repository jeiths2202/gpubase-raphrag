/**
 * useClarification Hook
 *
 * Handles query clarification for ambiguous terms.
 * Integrates with useStreamingChat to intercept queries before sending.
 */

import { useState, useCallback, useRef } from 'react';
import {
  checkClarification,
  applyClarification,
  type DetectedAmbiguousTerm,
  type TermSelection,
} from '../../../api/clarification.api';

// ============================================================================
// Types
// ============================================================================

export interface UseClarificationReturn {
  /** Whether clarification modal is open */
  isModalOpen: boolean;

  /** Detected ambiguous terms requiring clarification */
  detectedTerms: DetectedAmbiguousTerm[];

  /** Original query that triggered clarification */
  pendingQuery: string;

  /** Check if query needs clarification before sending */
  checkQueryClarification: (query: string) => Promise<ClarificationCheckResult>;

  /** Handle user's selections from the clarification modal */
  handleClarificationConfirm: (selections: TermSelection[]) => Promise<void>;

  /** Close the clarification modal */
  closeClarificationModal: () => void;

  /** Auto-resolved message to show user */
  autoResolvedMessage: string | null;

  /** Clear auto-resolved message */
  clearAutoResolvedMessage: () => void;
}

export interface ClarificationCheckResult {
  /** Whether the query can proceed (either no clarification needed or auto-resolved) */
  canProceed: boolean;
  /** The resolved query to use for search (may be modified if auto-resolved) */
  resolvedQuery: string;
  /** Whether the modal was opened for user input */
  modalOpened: boolean;
  /** Number of terms auto-resolved using user preferences */
  autoResolvedCount: number;
}

// ============================================================================
// Hook
// ============================================================================

export function useClarification(
  onSendMessage: (query: string) => void
): UseClarificationReturn {
  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [detectedTerms, setDetectedTerms] = useState<DetectedAmbiguousTerm[]>([]);
  const [pendingQuery, setPendingQuery] = useState('');

  // Auto-resolve message state
  const [autoResolvedMessage, setAutoResolvedMessage] = useState<string | null>(null);

  // Ref to prevent duplicate checks
  const isCheckingRef = useRef(false);

  /**
   * Check if a query needs clarification before sending.
   * Returns immediately if no clarification needed, opens modal otherwise.
   */
  const checkQueryClarification = useCallback(
    async (query: string): Promise<ClarificationCheckResult> => {
      // Prevent duplicate checks
      if (isCheckingRef.current) {
        return { canProceed: true, resolvedQuery: query, modalOpened: false, autoResolvedCount: 0 };
      }

      try {
        isCheckingRef.current = true;

        const response = await checkClarification({ query });

        if (!response.needs_clarification) {
          // Either no ambiguous terms found, or all were auto-resolved
          const resolvedQuery = response.resolved_query || query;

          // Show auto-resolve message if any terms were resolved
          if (response.auto_resolved_count > 0 && response.message) {
            setAutoResolvedMessage(response.message);
            // Auto-clear after 5 seconds
            setTimeout(() => setAutoResolvedMessage(null), 5000);
          }

          return {
            canProceed: true,
            resolvedQuery,
            modalOpened: false,
            autoResolvedCount: response.auto_resolved_count,
          };
        }

        // Clarification needed - open modal
        setDetectedTerms(response.detected_terms);
        setPendingQuery(query);
        setIsModalOpen(true);

        return {
          canProceed: false,
          resolvedQuery: query,
          modalOpened: true,
          autoResolvedCount: 0,
        };
      } catch (error) {
        // On error, allow the query to proceed (graceful degradation)
        console.warn('[useClarification] Check failed, proceeding with original query:', error);
        return { canProceed: true, resolvedQuery: query, modalOpened: false, autoResolvedCount: 0 };
      } finally {
        isCheckingRef.current = false;
      }
    },
    []
  );

  /**
   * Handle user's selections from the clarification modal.
   * Applies selections and sends the resolved query.
   */
  const handleClarificationConfirm = useCallback(
    async (selections: TermSelection[]) => {
      try {
        const response = await applyClarification({
          query: pendingQuery,
          selections,
        });

        // Close modal
        setIsModalOpen(false);
        setDetectedTerms([]);

        // Show message if preferences were saved
        if (response.preferences_saved > 0 && response.message) {
          setAutoResolvedMessage(response.message);
          setTimeout(() => setAutoResolvedMessage(null), 5000);
        }

        // Send the resolved query
        if (response.success && response.resolved_query) {
          onSendMessage(response.resolved_query);
        }
      } catch (error) {
        console.error('[useClarification] Apply failed:', error);
        // On error, send original query
        setIsModalOpen(false);
        onSendMessage(pendingQuery);
      }
    },
    [pendingQuery, onSendMessage]
  );

  /**
   * Close the clarification modal without sending.
   */
  const closeClarificationModal = useCallback(() => {
    setIsModalOpen(false);
    setDetectedTerms([]);
    setPendingQuery('');
  }, []);

  /**
   * Clear auto-resolved message.
   */
  const clearAutoResolvedMessage = useCallback(() => {
    setAutoResolvedMessage(null);
  }, []);

  return {
    isModalOpen,
    detectedTerms,
    pendingQuery,
    checkQueryClarification,
    handleClarificationConfirm,
    closeClarificationModal,
    autoResolvedMessage,
    clearAutoResolvedMessage,
  };
}

export default useClarification;
