/**
 * FAQ Registration Modal Component
 *
 * Modal dialog for registering a chat Q&A pair as an FAQ item.
 * Available to admin and leader roles only.
 */

import React, { useState, useCallback, useEffect } from 'react';
import { FileText, X, Loader2, AlertCircle, Tag, FolderOpen } from 'lucide-react';
import type { AgentType } from '../../api/agent.api';
import { createFAQItem, type CreateFAQItemRequest } from '../../api/faq.api';

// ============================================================================
// Types
// ============================================================================

export interface FAQRegistrationModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** Callback when FAQ is successfully registered */
  onSuccess: () => void;
  /** Translation function */
  t: (key: string) => string;
  /** User's original question */
  question: string;
  /** Assistant's answer */
  answer: string;
  /** Agent type for category inference */
  agentType?: AgentType;
}

// Category options for FAQ
const CATEGORY_OPTIONS = [
  { value: 'general', labelKey: 'common.agent.faq.categories.general' },
  { value: 'openframe', labelKey: 'common.agent.faq.categories.openframe' },
  { value: 'ofcobol', labelKey: 'common.agent.faq.categories.ofcobol' },
  { value: 'ofasm', labelKey: 'common.agent.faq.categories.ofasm' },
  { value: 'ims', labelKey: 'common.agent.faq.categories.ims' },
  { value: 'rag', labelKey: 'common.agent.faq.categories.rag' },
];

// Infer category from agent type
const inferCategory = (agentType?: AgentType): string => {
  switch (agentType) {
    case 'ims':
      return 'ims';
    case 'rag':
    case 'auto':
      return 'rag';
    case 'code':
      return 'general';
    default:
      return 'general';
  }
};

// ============================================================================
// Component
// ============================================================================

export const FAQRegistrationModal: React.FC<FAQRegistrationModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  t,
  question,
  answer,
  agentType,
}) => {
  // Form state
  const [editedQuestion, setEditedQuestion] = useState(question);
  const [editedAnswer, setEditedAnswer] = useState(answer);
  const [category, setCategory] = useState(inferCategory(agentType));
  const [tagsInput, setTagsInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form state when props change
  useEffect(() => {
    if (isOpen) {
      setEditedQuestion(question);
      setEditedAnswer(answer);
      setCategory(inferCategory(agentType));
      setTagsInput('');
      setError(null);
    }
  }, [isOpen, question, answer, agentType]);

  // Handle close
  const handleClose = useCallback(() => {
    setError(null);
    setIsSubmitting(false);
    onClose();
  }, [onClose]);

  // Handle submit
  const handleSubmit = useCallback(async () => {
    if (!editedQuestion.trim() || !editedAnswer.trim()) {
      setError(t('common.agent.faq.emptyFields') || 'Please fill in question and answer');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      // Parse tags from comma-separated input
      const tags = tagsInput
        .split(',')
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);

      const request: CreateFAQItemRequest = {
        question_ko: editedQuestion,
        answer_ko: editedAnswer,
        category,
        tags,
        source_type: 'curated',
      };

      await createFAQItem(request);

      // Success
      onSuccess();
      handleClose();
    } catch (err) {
      console.error('Failed to create FAQ item:', err);
      setError(
        err instanceof Error
          ? err.message
          : t('common.agent.faq.createError') || 'Failed to register FAQ'
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [editedQuestion, editedAnswer, category, tagsInput, t, onSuccess, handleClose]);

  // Handle key press
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && e.ctrlKey && !isSubmitting) {
        handleSubmit();
      }
    },
    [handleSubmit, isSubmitting]
  );

  // Don't render if not open
  if (!isOpen) return null;

  return (
    <div className="agent-faq-modal-overlay" onClick={handleClose}>
      <div className="agent-faq-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="agent-faq-modal-header">
          <div className="agent-faq-modal-title">
            <FileText size={20} />
            <h3>{t('common.agent.faq.registerTitle') || 'Register as FAQ'}</h3>
          </div>
          <button className="agent-faq-modal-close" onClick={handleClose}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="agent-faq-modal-body">
          {/* Error message */}
          {error && (
            <div className="agent-faq-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Question field */}
          <div className="agent-faq-field">
            <label htmlFor="faq-question">
              {t('common.agent.faq.question') || 'Question'}
            </label>
            <textarea
              id="faq-question"
              value={editedQuestion}
              onChange={(e) => setEditedQuestion(e.target.value)}
              placeholder={t('common.agent.faq.questionPlaceholder') || 'Enter the question'}
              disabled={isSubmitting}
              rows={3}
              onKeyDown={handleKeyDown}
            />
          </div>

          {/* Answer field */}
          <div className="agent-faq-field">
            <label htmlFor="faq-answer">
              {t('common.agent.faq.answer') || 'Answer'}
            </label>
            <textarea
              id="faq-answer"
              value={editedAnswer}
              onChange={(e) => setEditedAnswer(e.target.value)}
              placeholder={t('common.agent.faq.answerPlaceholder') || 'Enter the answer'}
              disabled={isSubmitting}
              rows={6}
              onKeyDown={handleKeyDown}
            />
          </div>

          {/* Category field */}
          <div className="agent-faq-field">
            <label htmlFor="faq-category">
              <FolderOpen size={14} />
              {t('common.agent.faq.category') || 'Category'}
            </label>
            <select
              id="faq-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              disabled={isSubmitting}
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {t(opt.labelKey) || opt.value}
                </option>
              ))}
            </select>
          </div>

          {/* Tags field */}
          <div className="agent-faq-field">
            <label htmlFor="faq-tags">
              <Tag size={14} />
              {t('common.agent.faq.tags') || 'Tags'}
              <span className="agent-faq-field-hint">
                ({t('common.agent.faq.tagsHint') || 'comma-separated'})
              </span>
            </label>
            <input
              id="faq-tags"
              type="text"
              value={tagsInput}
              onChange={(e) => setTagsInput(e.target.value)}
              placeholder={t('common.agent.faq.tagsPlaceholder') || 'e.g., installation, error, config'}
              disabled={isSubmitting}
            />
          </div>
        </div>

        {/* Footer */}
        <div className="agent-faq-modal-footer">
          <button
            className="agent-faq-cancel-btn"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            {t('common.cancel') || 'Cancel'}
          </button>
          <button
            className="agent-faq-submit-btn"
            onClick={handleSubmit}
            disabled={isSubmitting || !editedQuestion.trim() || !editedAnswer.trim()}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="spin" />
                <span>{t('common.agent.faq.registering') || 'Registering...'}</span>
              </>
            ) : (
              <>
                <FileText size={16} />
                <span>{t('common.agent.faq.register') || 'Register'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default FAQRegistrationModal;
