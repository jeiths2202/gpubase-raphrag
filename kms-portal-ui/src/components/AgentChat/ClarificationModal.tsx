/**
 * Clarification Modal Component
 *
 * Modal dialog for clarifying ambiguous terms in user queries.
 * Presents possible meanings and allows user to select the intended one.
 * Supports "Remember my choice" functionality for future queries.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  HelpCircle,
  X,
  CheckCircle2,
  Info,
  Tag,
  MessageSquare,
  Save,
} from 'lucide-react';
import type { DetectedAmbiguousTerm, TermSelection } from '../../api/clarification.api';
import './ClarificationModal.css';

// ============================================================================
// Types
// ============================================================================

export interface ClarificationModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when clarification is confirmed */
  onConfirm: (selections: TermSelection[]) => void;
  /** Translation function */
  t: (key: string) => string;
  /** The original query */
  query: string;
  /** Detected ambiguous terms requiring clarification */
  detectedTerms: DetectedAmbiguousTerm[];
}

interface SelectionState {
  [term: string]: {
    entityId: string;
    entityName: string;
    remember: boolean;
  };
}

// ============================================================================
// Component
// ============================================================================

export const ClarificationModal: React.FC<ClarificationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  t,
  query,
  detectedTerms,
}) => {
  // Track selections for each term
  const [selections, setSelections] = useState<SelectionState>({});

  // Reset selections when modal opens with new terms
  useEffect(() => {
    if (isOpen && detectedTerms.length > 0) {
      const initialSelections: SelectionState = {};
      detectedTerms.forEach((term) => {
        // Pre-select if user has a preference
        if (term.user_preference) {
          const entity = term.possible_entities.find(
            (e) => e.id === term.user_preference
          );
          if (entity) {
            initialSelections[term.term_normalized] = {
              entityId: entity.id,
              entityName: entity.name,
              remember: false,
            };
          }
        }
      });
      setSelections(initialSelections);
    }
  }, [isOpen, detectedTerms]);

  // Handle entity selection
  const handleSelectEntity = useCallback(
    (termNormalized: string, entityId: string, entityName: string) => {
      setSelections((prev) => ({
        ...prev,
        [termNormalized]: {
          entityId,
          entityName,
          remember: prev[termNormalized]?.remember || false,
        },
      }));
    },
    []
  );

  // Handle remember checkbox toggle
  const handleToggleRemember = useCallback((termNormalized: string) => {
    setSelections((prev) => {
      if (!prev[termNormalized]) return prev;
      return {
        ...prev,
        [termNormalized]: {
          ...prev[termNormalized],
          remember: !prev[termNormalized].remember,
        },
      };
    });
  }, []);

  // Check if all terms have selections
  const allSelected = detectedTerms.every(
    (term) => selections[term.term_normalized]?.entityId
  );

  // Handle confirm
  const handleConfirm = useCallback(() => {
    if (!allSelected) return;

    const termSelections: TermSelection[] = detectedTerms.map((term) => {
      const selection = selections[term.term_normalized];
      return {
        term: term.term,
        selected_entity_id: selection.entityId,
        selected_entity_name: selection.entityName,
        remember: selection.remember,
      };
    });

    onConfirm(termSelections);
    onClose();
  }, [allSelected, detectedTerms, selections, onConfirm, onClose]);

  // Don't render if not open
  if (!isOpen) return null;

  return (
    <div className="clarification-modal-overlay" onClick={onClose}>
      <div
        className="clarification-modal"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="clarification-modal-header">
          <div className="clarification-modal-title">
            <HelpCircle size={20} />
            <h3>{t('common.clarification.title') || 'Clarify Your Search'}</h3>
          </div>
          <button className="clarification-modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Query display */}
        <div className="clarification-modal-query">
          <MessageSquare size={16} className="clarification-query-icon" />
          <span className="clarification-query-label">
            {t('common.clarification.query') || 'Your query'}:
          </span>
          <span className="clarification-query-text">"{query}"</span>
        </div>

        {/* Info message */}
        <div className="clarification-info">
          <Info size={16} />
          <span>
            {t('common.clarification.infoMessage') ||
              'Your query contains terms that could have multiple meanings. Please select the intended meaning for each term to get more accurate results.'}
          </span>
        </div>

        {/* Body - Terms list */}
        <div className="clarification-modal-body">
          {detectedTerms.map((term) => {
            const currentSelection = selections[term.term_normalized];

            return (
              <div key={term.term_normalized} className="clarification-term">
                {/* Term header */}
                <div className="clarification-term-header">
                  <Tag size={16} className="clarification-term-icon" />
                  <span className="clarification-term-name">"{term.term}"</span>
                  {term.category && (
                    <span className="clarification-term-category">
                      {term.category}
                    </span>
                  )}
                </div>

                {/* Entity options */}
                <div className="clarification-entities">
                  {term.possible_entities.map((entity) => {
                    const isSelected = currentSelection?.entityId === entity.id;

                    return (
                      <button
                        key={entity.id}
                        className={`clarification-entity ${
                          isSelected ? 'selected' : ''
                        }`}
                        onClick={() =>
                          handleSelectEntity(
                            term.term_normalized,
                            entity.id,
                            entity.name
                          )
                        }
                      >
                        <div className="clarification-entity-check">
                          {isSelected ? (
                            <CheckCircle2 size={18} className="checked" />
                          ) : (
                            <div className="clarification-entity-circle" />
                          )}
                        </div>
                        <div className="clarification-entity-info">
                          <span className="clarification-entity-name">
                            {entity.name}
                          </span>
                          <span className="clarification-entity-desc">
                            {entity.description}
                          </span>
                          {entity.keywords.length > 0 && (
                            <div className="clarification-entity-keywords">
                              {entity.keywords.slice(0, 4).map((kw) => (
                                <span
                                  key={kw}
                                  className="clarification-keyword"
                                >
                                  {kw}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Remember checkbox - only show if entity is selected */}
                {currentSelection && (
                  <label className="clarification-remember">
                    <input
                      type="checkbox"
                      checked={currentSelection.remember}
                      onChange={() => handleToggleRemember(term.term_normalized)}
                    />
                    <Save size={14} />
                    <span>
                      {t('common.clarification.remember') ||
                        'Remember this choice for future searches'}
                    </span>
                  </label>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="clarification-modal-footer">
          <div className="clarification-selection-count">
            <span>
              {Object.keys(selections).filter((k) => selections[k]?.entityId)
                .length}{' '}
              / {detectedTerms.length}{' '}
              {t('common.clarification.selected') || 'selected'}
            </span>
          </div>
          <div className="clarification-modal-actions">
            <button className="clarification-cancel-btn" onClick={onClose}>
              {t('common.cancel') || 'Cancel'}
            </button>
            <button
              className="clarification-confirm-btn"
              onClick={handleConfirm}
              disabled={!allSelected}
            >
              <CheckCircle2 size={16} />
              {t('common.clarification.confirm') || 'Confirm & Search'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClarificationModal;
