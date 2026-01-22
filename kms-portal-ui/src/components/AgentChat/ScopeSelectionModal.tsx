/**
 * Scope Selection Modal Component (Category-based)
 *
 * Modal dialog for selecting document/section scope before RAG search.
 * Uses category-based hierarchy for better organization.
 * Part of the Agent-Driven RAG system for pre-search confirmation.
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';
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
  Tag,
  AlertTriangle,
  Terminal,
  Settings,
  HelpCircle,
  ListChecks,
  FileSearch,
  FolderOpen,
} from 'lucide-react';
import {
  matchCategories,
  type Category,
  type CategoryDocumentInfo,
  type SearchScope,
} from '../../api/agent-navigation.api';
import type { LucideIcon } from 'lucide-react';
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
  /** Language for category names */
  language?: string;
}

interface ExpandedState {
  categories: Set<string>;
  subcategories: Set<string>;
  documents: Set<string>;
}

interface SelectionState {
  categories: Set<string>;
  subcategories: Set<string>;
  documents: Set<string>;
  sections: Set<string>;
}

// Icon mapping for categories
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  'AlertTriangle': AlertTriangle,
  'Terminal': Terminal,
  'Settings': Settings,
  'HelpCircle': HelpCircle,
  'ListChecks': ListChecks,
  'FileSearch': FileSearch,
};

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get category name based on language
 */
const getCategoryName = (category: Category, language?: string): string => {
  switch (language) {
    case 'ko':
      return category.name_ko || category.name;
    case 'ja':
      return category.name_ja || category.name;
    default:
      return category.name;
  }
};

/**
 * Get icon component for category
 */
const getCategoryIcon = (iconName: string): LucideIcon => {
  return CATEGORY_ICONS[iconName] || Folder;
};

// ============================================================================
// Component
// ============================================================================

export const ScopeSelectionModal: React.FC<ScopeSelectionModalProps> = ({
  isOpen,
  onClose,
  onSelectScope,
  t,
  query,
  language = 'en',
}) => {
  // State
  const [categories, setCategories] = useState<Category[]>([]);
  const [extractedKeywords, setExtractedKeywords] = useState<string[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [totalSections, setTotalSections] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ExpandedState>({
    categories: new Set(),
    subcategories: new Set(),
    documents: new Set(),
  });
  const [selection, setSelection] = useState<SelectionState>({
    categories: new Set(),
    subcategories: new Set(),
    documents: new Set(),
    sections: new Set(),
  });

  // Load categories when modal opens
  useEffect(() => {
    if (isOpen && query) {
      loadCategories();
    }
  }, [isOpen, query]);

  // Reset state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setSelection({
        categories: new Set(),
        subcategories: new Set(),
        documents: new Set(),
        sections: new Set(),
      });
      setExpanded({
        categories: new Set(),
        subcategories: new Set(),
        documents: new Set(),
      });
      setError(null);
    }
  }, [isOpen]);

  // Load category matches
  const loadCategories = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await matchCategories({
        query,
        max_categories: 6,
        max_subcategories: 5,
        max_documents: 10,
        min_score: 0.1,
      });

      setCategories(response.data.categories);
      setExtractedKeywords(response.data.extracted_keywords);
      setTotalDocuments(response.data.total_documents);
      setTotalSections(response.data.total_sections);

      // Auto-expand first category with high relevance
      if (response.data.categories.length > 0) {
        const first = response.data.categories[0];
        if (first.relevance_score > 0.5) {
          setExpanded((prev) => ({
            ...prev,
            categories: new Set([first.id]),
          }));
        }
      }
    } catch (err) {
      console.error('Failed to load categories:', err);
      setError(t('agentNav.loadError') || 'Failed to load document candidates');
    } finally {
      setIsLoading(false);
    }
  }, [query, t]);

  // Toggle category expansion
  const toggleCategoryExpand = useCallback((categoryId: string) => {
    setExpanded((prev) => {
      const newCategories = new Set(prev.categories);
      if (newCategories.has(categoryId)) {
        newCategories.delete(categoryId);
      } else {
        newCategories.add(categoryId);
      }
      return { ...prev, categories: newCategories };
    });
  }, []);

  // Toggle subcategory expansion
  const toggleSubcategoryExpand = useCallback((subcategoryId: string) => {
    setExpanded((prev) => {
      const newSubcategories = new Set(prev.subcategories);
      if (newSubcategories.has(subcategoryId)) {
        newSubcategories.delete(subcategoryId);
      } else {
        newSubcategories.add(subcategoryId);
      }
      return { ...prev, subcategories: newSubcategories };
    });
  }, []);

  // Toggle document expansion
  const toggleDocumentExpand = useCallback((docId: string) => {
    setExpanded((prev) => {
      const newDocuments = new Set(prev.documents);
      if (newDocuments.has(docId)) {
        newDocuments.delete(docId);
      } else {
        newDocuments.add(docId);
      }
      return { ...prev, documents: newDocuments };
    });
  }, []);

  // Toggle category selection (selects all documents in category)
  const toggleCategorySelect = useCallback((categoryId: string) => {
    setSelection((prev) => {
      const newCategories = new Set(prev.categories);
      if (newCategories.has(categoryId)) {
        newCategories.delete(categoryId);
      } else {
        newCategories.add(categoryId);
      }
      return { ...prev, categories: newCategories };
    });
  }, []);

  // Toggle subcategory selection
  const toggleSubcategorySelect = useCallback((subcategoryId: string) => {
    setSelection((prev) => {
      const newSubcategories = new Set(prev.subcategories);
      if (newSubcategories.has(subcategoryId)) {
        newSubcategories.delete(subcategoryId);
      } else {
        newSubcategories.add(subcategoryId);
      }
      return { ...prev, subcategories: newSubcategories };
    });
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
  const toggleSectionSelect = useCallback((sectionId: string) => {
    setSelection((prev) => {
      const newSections = new Set(prev.sections);
      if (newSections.has(sectionId)) {
        newSections.delete(sectionId);
      } else {
        newSections.add(sectionId);
      }
      return { ...prev, sections: newSections };
    });
  }, []);

  // Calculate effective selection (expand category/subcategory selection to documents)
  const effectiveSelection = useMemo(() => {
    const documents = new Set<string>();
    const sections = new Set<string>();

    // Add directly selected documents
    selection.documents.forEach((d) => documents.add(d));
    selection.sections.forEach((s) => sections.add(s));

    // Expand category selections to documents
    categories.forEach((cat) => {
      if (selection.categories.has(cat.id)) {
        cat.subcategories.forEach((sub) => {
          sub.documents.forEach((doc) => documents.add(doc.pdf_id));
        });
      } else {
        // Check subcategory selections
        cat.subcategories.forEach((sub) => {
          if (selection.subcategories.has(sub.id)) {
            sub.documents.forEach((doc) => documents.add(doc.pdf_id));
          }
        });
      }
    });

    return { documents, sections };
  }, [selection, categories]);

  // Select all
  const selectAll = useCallback(() => {
    const allCategories = new Set(categories.map((c) => c.id));
    setSelection({
      categories: allCategories,
      subcategories: new Set(),
      documents: new Set(),
      sections: new Set(),
    });
  }, [categories]);

  // Clear selection
  const clearSelection = useCallback(() => {
    setSelection({
      categories: new Set(),
      subcategories: new Set(),
      documents: new Set(),
      sections: new Set(),
    });
  }, []);

  // Handle search with scope
  const handleSearchWithScope = useCallback(() => {
    if (
      effectiveSelection.documents.size === 0 &&
      effectiveSelection.sections.size === 0
    ) {
      // No selection, search all
      onSelectScope(null);
    } else {
      onSelectScope({
        documents: Array.from(effectiveSelection.documents),
        sections: Array.from(effectiveSelection.sections),
        keywords: extractedKeywords,
      });
    }
    onClose();
  }, [effectiveSelection, extractedKeywords, onSelectScope, onClose]);

  // Handle search all (no scope)
  const handleSearchAll = useCallback(() => {
    onSelectScope(null);
    onClose();
  }, [onSelectScope, onClose]);

  // Don't render if not open
  if (!isOpen) return null;

  const selectionCount =
    selection.categories.size +
    selection.subcategories.size +
    selection.documents.size +
    selection.sections.size;

  return (
    <div className="scope-modal-overlay" onClick={onClose}>
      <div className="scope-modal scope-modal-wide" onClick={(e) => e.stopPropagation()}>
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

        {/* Keywords display */}
        {extractedKeywords.length > 0 && (
          <div className="scope-keywords">
            <Tag size={14} className="scope-keywords-icon" />
            <span className="scope-keywords-label">
              {t('agentNav.keywords') || 'Keywords'}:
            </span>
            <div className="scope-keywords-list">
              {extractedKeywords.map((kw) => (
                <span key={kw} className="scope-keyword-tag">
                  {kw}
                </span>
              ))}
            </div>
          </div>
        )}

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
          ) : categories.length === 0 ? (
            <div className="scope-modal-empty">
              <BookOpen size={24} />
              <span>{t('agentNav.noCandidates') || 'No relevant documents found'}</span>
            </div>
          ) : (
            <>
              {/* Summary */}
              <div className="scope-summary">
                <Star size={16} className="scope-summary-icon" />
                <span>
                  {totalDocuments} {t('agentNav.documents') || 'documents'},{' '}
                  {totalSections} {t('agentNav.sections') || 'sections'}{' '}
                  {t('agentNav.matched') || 'matched'}
                </span>
              </div>

              {/* Categories list */}
              <div className="scope-categories">
                {categories.map((category) => {
                  const CategoryIcon = getCategoryIcon(category.icon);
                  const isExpanded = expanded.categories.has(category.id);
                  const isSelected = selection.categories.has(category.id);

                  return (
                    <div key={category.id} className="scope-category">
                      {/* Category header */}
                      <div className="scope-category-header">
                        <button
                          className="scope-expand-btn"
                          onClick={() => toggleCategoryExpand(category.id)}
                        >
                          {isExpanded ? (
                            <ChevronDown size={16} />
                          ) : (
                            <ChevronRight size={16} />
                          )}
                        </button>
                        <button
                          className="scope-checkbox"
                          onClick={() => toggleCategorySelect(category.id)}
                        >
                          {isSelected ? (
                            <CheckSquare size={18} className="checked" />
                          ) : (
                            <Square size={18} />
                          )}
                        </button>
                        <CategoryIcon size={18} className="scope-category-icon" />
                        <div className="scope-category-info">
                          <span className="scope-category-name">
                            {getCategoryName(category, language)}
                          </span>
                          <span className="scope-category-meta">
                            {category.subcategory_count}{' '}
                            {t('agentNav.subcategories') || 'subcategories'},{' '}
                            {category.document_count}{' '}
                            {t('agentNav.documents') || 'docs'}
                          </span>
                        </div>
                        <span className="scope-score">
                          {(category.relevance_score * 100).toFixed(0)}%
                        </span>
                      </div>

                      {/* Subcategories (expandable) */}
                      {isExpanded && category.subcategories.length > 0 && (
                        <div className="scope-subcategories">
                          {category.subcategories.map((subcategory) => {
                            const isSubExpanded = expanded.subcategories.has(
                              subcategory.id
                            );
                            const isSubSelected =
                              isSelected || selection.subcategories.has(subcategory.id);

                            return (
                              <div key={subcategory.id} className="scope-subcategory">
                                {/* Subcategory header */}
                                <div className="scope-subcategory-header">
                                  <button
                                    className="scope-expand-btn"
                                    onClick={() =>
                                      toggleSubcategoryExpand(subcategory.id)
                                    }
                                  >
                                    {isSubExpanded ? (
                                      <ChevronDown size={14} />
                                    ) : (
                                      <ChevronRight size={14} />
                                    )}
                                  </button>
                                  <button
                                    className="scope-checkbox"
                                    onClick={() =>
                                      toggleSubcategorySelect(subcategory.id)
                                    }
                                    disabled={isSelected}
                                  >
                                    {isSubSelected ? (
                                      <CheckSquare size={16} className="checked" />
                                    ) : (
                                      <Square size={16} />
                                    )}
                                  </button>
                                  <FolderOpen size={14} className="scope-subcategory-icon" />
                                  <div className="scope-subcategory-info">
                                    <span className="scope-subcategory-name">
                                      {subcategory.name}
                                    </span>
                                    <span className="scope-subcategory-meta">
                                      {subcategory.document_count}{' '}
                                      {t('agentNav.documents') || 'docs'}
                                    </span>
                                  </div>
                                  <span className="scope-score-small">
                                    {(subcategory.relevance_score * 100).toFixed(0)}%
                                  </span>
                                </div>

                                {/* Documents (expandable) */}
                                {isSubExpanded && subcategory.documents.length > 0 && (
                                  <div className="scope-documents">
                                    {subcategory.documents.map(
                                      (doc: CategoryDocumentInfo) => {
                                        const isDocExpanded = expanded.documents.has(
                                          doc.pdf_id
                                        );
                                        const isDocSelected =
                                          isSubSelected ||
                                          selection.documents.has(doc.pdf_id);

                                        return (
                                          <div key={doc.pdf_id} className="scope-document">
                                            {/* Document header */}
                                            <div className="scope-document-header">
                                              <button
                                                className="scope-expand-btn"
                                                onClick={() =>
                                                  toggleDocumentExpand(doc.pdf_id)
                                                }
                                              >
                                                {isDocExpanded ? (
                                                  <ChevronDown size={12} />
                                                ) : (
                                                  <ChevronRight size={12} />
                                                )}
                                              </button>
                                              <button
                                                className="scope-checkbox"
                                                onClick={() =>
                                                  toggleDocumentSelect(doc.pdf_id)
                                                }
                                                disabled={isSubSelected}
                                              >
                                                {isDocSelected ? (
                                                  <CheckSquare
                                                    size={14}
                                                    className="checked"
                                                  />
                                                ) : (
                                                  <Square size={14} />
                                                )}
                                              </button>
                                              <Folder size={12} className="scope-doc-icon" />
                                              <div className="scope-document-info">
                                                <span className="scope-document-name">
                                                  {doc.document_name}
                                                </span>
                                                <span className="scope-document-meta">
                                                  {doc.total_pages}{' '}
                                                  {t('agentNav.pages') || 'pages'}
                                                </span>
                                              </div>
                                            </div>

                                            {/* Sections (expandable) */}
                                            {isDocExpanded && doc.sections.length > 0 && (
                                              <div className="scope-sections">
                                                {doc.sections.map((section) => {
                                                  const sectionKey = `${doc.pdf_id}:${section.section_id}`;
                                                  const isSectionSelected =
                                                    isDocSelected ||
                                                    selection.sections.has(sectionKey);

                                                  return (
                                                    <div
                                                      key={sectionKey}
                                                      className="scope-section"
                                                      style={{
                                                        paddingLeft: `${
                                                          section.level * 12 + 32
                                                        }px`,
                                                      }}
                                                    >
                                                      <button
                                                        className="scope-checkbox"
                                                        onClick={() =>
                                                          toggleSectionSelect(sectionKey)
                                                        }
                                                        disabled={isDocSelected}
                                                      >
                                                        {isSectionSelected ? (
                                                          <CheckSquare
                                                            size={12}
                                                            className="checked"
                                                          />
                                                        ) : (
                                                          <Square size={12} />
                                                        )}
                                                      </button>
                                                      <FileText
                                                        size={12}
                                                        className="scope-section-icon"
                                                      />
                                                      <span className="scope-section-title">
                                                        {section.title}
                                                      </span>
                                                      <span className="scope-section-pages">
                                                        p.{section.page_start}
                                                        {section.page_end !==
                                                          section.page_start &&
                                                          `-${section.page_end}`}
                                                      </span>
                                                    </div>
                                                  );
                                                })}
                                              </div>
                                            )}
                                          </div>
                                        );
                                      }
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
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
