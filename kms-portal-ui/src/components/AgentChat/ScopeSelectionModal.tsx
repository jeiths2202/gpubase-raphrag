/**
 * Scope Selection Modal Component
 *
 * Modal dialog for selecting document/section scope before RAG search.
 * Part of the Agent-Driven RAG system for pre-search confirmation.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Search,
  X,
  Loader2,
  AlertCircle,
  FileText,
  ChevronRight,
  ChevronDown,
  Star,
  CheckSquare,
  Square,
  Folder,
  BookOpen,
  Globe,
} from 'lucide-react';
import {
  getCandidates,
  type DocumentCandidate,
  type SearchScope,
} from '../../api/agent-navigation.api';
import './ScopeSelectionModal.css';

// ============================================================================
// Types
// ============================================================================

export interface ScopeSelectionModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when scope is selected */
  onSelectScope: (scope: SearchScope | null) => void;
  /** Translation function */
  t: (key: string) => string;
  /** The query being searched */
  query: string;
}

interface ExpandedState {
  [docId: string]: boolean;
}

interface SelectionState {
  documents: Set<string>;
  sections: Set<string>;
}

// ============================================================================
// Component
// ============================================================================

export const ScopeSelectionModal: React.FC<ScopeSelectionModalProps> = ({
  isOpen,
  onClose,
  onSelectScope,
  t,
  query,
}) => {
  // State
  const [candidates, setCandidates] = useState<DocumentCandidate[]>([]);
  const [suggestedScope, setSuggestedScope] = useState<SearchScope | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [selection, setSelection] = useState<SelectionState>({
    documents: new Set(),
    sections: new Set(),
  });

  // Load candidates when modal opens
  useEffect(() => {
    if (isOpen && query) {
      loadCandidates();
    }
  }, [isOpen, query]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setSelection({ documents: new Set(), sections: new Set() });
      setExpanded({});
      setError(null);
    }
  }, [isOpen]);

  // Load document candidates
  const loadCandidates = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await getCandidates({
        query,
        top_k: 10,
        min_score: 0.1,
      });

      setCandidates(response.data.candidates);
      setSuggestedScope(response.data.suggested_scope);

      // Auto-expand first candidate if it has high relevance
      if (response.data.candidates.length > 0) {
        const first = response.data.candidates[0];
        if (first.relevance_score > 0.5) {
          setExpanded({ [first.pdf_id]: true });
        }
      }

      // Apply suggested scope if available
      if (response.data.suggested_scope) {
        const scope = response.data.suggested_scope;
        setSelection({
          documents: new Set(scope.documents || []),
          sections: new Set(scope.sections || []),
        });
      }
    } catch (err) {
      console.error('Failed to load candidates:', err);
      setError(t('agentNav.loadError') || 'Failed to load document candidates');
    } finally {
      setIsLoading(false);
    }
  }, [query, t]);

  // Toggle document expansion
  const toggleExpand = useCallback((docId: string) => {
    setExpanded((prev) => ({
      ...prev,
      [docId]: !prev[docId],
    }));
  }, []);

  // Toggle document selection
  const toggleDocumentSelect = useCallback((docId: string) => {
    setSelection((prev) => {
      const newDocs = new Set(prev.documents);
      if (newDocs.has(docId)) {
        newDocs.delete(docId);
      } else {
        newDocs.add(docId);
      }
      return { ...prev, documents: newDocs };
    });
  }, []);

  // Toggle section selection
  const toggleSectionSelect = useCallback((docId: string, sectionPath: string) => {
    const sectionKey = `${docId}:${sectionPath}`;
    setSelection((prev) => {
      const newSections = new Set(prev.sections);
      if (newSections.has(sectionKey)) {
        newSections.delete(sectionKey);
      } else {
        newSections.add(sectionKey);
      }
      return { ...prev, sections: newSections };
    });
  }, []);

  // Apply suggested scope
  const applySuggested = useCallback(() => {
    if (suggestedScope) {
      setSelection({
        documents: new Set(suggestedScope.documents || []),
        sections: new Set(suggestedScope.sections || []),
      });
    }
  }, [suggestedScope]);

  // Select all
  const selectAll = useCallback(() => {
    const allDocs = new Set(candidates.map((c) => c.pdf_id));
    setSelection({ documents: allDocs, sections: new Set() });
  }, [candidates]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelection({ documents: new Set(), sections: new Set() });
  }, []);

  // Handle search with scope
  const handleSearchWithScope = useCallback(() => {
    if (selection.documents.size === 0 && selection.sections.size === 0) {
      // No selection, search all
      onSelectScope(null);
    } else {
      // Extract section paths from section keys
      const sections = Array.from(selection.sections).map((key) => {
        const [, sectionPath] = key.split(':');
        return sectionPath;
      });

      onSelectScope({
        documents: Array.from(selection.documents),
        sections,
      });
    }
    onClose();
  }, [selection, onSelectScope, onClose]);

  // Handle search all (no scope)
  const handleSearchAll = useCallback(() => {
    onSelectScope(null);
    onClose();
  }, [onSelectScope, onClose]);

  // Don't render if not open
  if (!isOpen) return null;

  const selectionCount = selection.documents.size + selection.sections.size;

  return (
    <div className="scope-modal-overlay" onClick={onClose}>
      <div className="scope-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="scope-modal-header">
          <div className="scope-modal-title">
            <Search size={20} />
            <h3>{t('agentNav.selectScope') || 'Select Search Scope'}</h3>
          </div>
          <button className="scope-modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Query display */}
        <div className="scope-modal-query">
          <span className="scope-modal-query-label">
            {t('agentNav.searchQuery') || 'Query'}:
          </span>
          <span className="scope-modal-query-text">"{query}"</span>
        </div>

        {/* Content */}
        <div className="scope-modal-body">
          {isLoading ? (
            <div className="scope-modal-loading">
              <Loader2 size={24} className="spin" />
              <span>{t('agentNav.loading') || 'Loading candidates...'}</span>
            </div>
          ) : error ? (
            <div className="scope-modal-error">
              <AlertCircle size={20} />
              <span>{error}</span>
            </div>
          ) : candidates.length === 0 ? (
            <div className="scope-modal-empty">
              <BookOpen size={24} />
              <span>{t('agentNav.noCandidates') || 'No relevant documents found'}</span>
            </div>
          ) : (
            <>
              {/* Suggested scope */}
              {suggestedScope && (
                <div className="scope-suggested" onClick={applySuggested}>
                  <Star size={16} className="scope-suggested-icon" />
                  <span className="scope-suggested-text">
                    {t('agentNav.suggested') || 'Suggested'}:
                  </span>
                  <span className="scope-suggested-detail">
                    {suggestedScope.documents?.length || 0}{' '}
                    {t('agentNav.documents') || 'documents'},
                    {suggestedScope.sections?.length || 0}{' '}
                    {t('agentNav.sections') || 'sections'}
                  </span>
                </div>
              )}

              {/* Candidates list */}
              <div className="scope-candidates">
                {candidates.map((doc) => (
                  <div key={doc.pdf_id} className="scope-document">
                    {/* Document header */}
                    <div className="scope-document-header">
                      <button
                        className="scope-document-expand"
                        onClick={() => toggleExpand(doc.pdf_id)}
                      >
                        {expanded[doc.pdf_id] ? (
                          <ChevronDown size={16} />
                        ) : (
                          <ChevronRight size={16} />
                        )}
                      </button>
                      <button
                        className="scope-document-checkbox"
                        onClick={() => toggleDocumentSelect(doc.pdf_id)}
                      >
                        {selection.documents.has(doc.pdf_id) ? (
                          <CheckSquare size={18} className="checked" />
                        ) : (
                          <Square size={18} />
                        )}
                      </button>
                      <Folder size={16} className="scope-document-icon" />
                      <div className="scope-document-info">
                        <span className="scope-document-name">{doc.document_name}</span>
                        <span className="scope-document-meta">
                          {doc.document_type} · {doc.total_pages} {t('agentNav.pages') || 'pages'}
                        </span>
                      </div>
                      <span className="scope-document-score">
                        {(doc.relevance_score * 100).toFixed(0)}%
                      </span>
                    </div>

                    {/* Sections (expandable) */}
                    {expanded[doc.pdf_id] && doc.sections.length > 0 && (
                      <div className="scope-sections">
                        {doc.sections.map((section) => (
                          <div
                            key={`${doc.pdf_id}:${section.section_path}`}
                            className="scope-section"
                            style={{ paddingLeft: `${section.level * 16 + 24}px` }}
                          >
                            <button
                              className="scope-section-checkbox"
                              onClick={() =>
                                toggleSectionSelect(doc.pdf_id, section.section_path)
                              }
                            >
                              {selection.sections.has(
                                `${doc.pdf_id}:${section.section_path}`
                              ) ? (
                                <CheckSquare size={16} className="checked" />
                              ) : (
                                <Square size={16} />
                              )}
                            </button>
                            <FileText size={14} className="scope-section-icon" />
                            <span className="scope-section-title">
                              {section.section_path} {section.section_title}
                            </span>
                            <span className="scope-section-pages">
                              p.{section.page_start}
                              {section.page_end !== section.page_start &&
                                `-${section.page_end}`}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="scope-modal-footer">
          <div className="scope-modal-selection">
            {selectionCount > 0 ? (
              <>
                <span>
                  {selectionCount} {t('agentNav.selected') || 'selected'}
                </span>
                <button className="scope-clear-btn" onClick={clearSelection}>
                  {t('agentNav.clear') || 'Clear'}
                </button>
              </>
            ) : (
              <button className="scope-select-all-btn" onClick={selectAll}>
                {t('agentNav.selectAll') || 'Select All'}
              </button>
            )}
          </div>
          <div className="scope-modal-actions">
            <button className="scope-search-all-btn" onClick={handleSearchAll}>
              <Globe size={16} />
              {t('agentNav.searchAll') || 'Search All'}
            </button>
            <button
              className="scope-search-selected-btn"
              onClick={handleSearchWithScope}
              disabled={isLoading}
            >
              <Search size={16} />
              {selectionCount > 0
                ? t('agentNav.searchSelected') || 'Search Selected'
                : t('agentNav.searchAll') || 'Search All'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScopeSelectionModal;
