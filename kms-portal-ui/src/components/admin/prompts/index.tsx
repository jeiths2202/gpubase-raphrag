/**
 * Prompt Configuration Tab
 *
 * Admin UI for managing system prompts.
 * Allows viewing, editing, and version management of AI agent prompts.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from '../../../hooks/useTranslation';
import {
  promptsApi,
  PromptSummary,
  PromptDetail,
  PromptHistory as PromptHistoryType,
} from '../../../api/prompts.api';
import './PromptTab.css';

// Category display order
const CATEGORY_ORDER = ['agent', 'middleware', 'system', 'persona', 'domain'];

// Category icons
const CATEGORY_ICONS: Record<string, string> = {
  agent: '🤖',
  middleware: '⚙️',
  system: '🔒',
  persona: '👤',
  domain: '📚',
};

export const PromptTab: React.FC = () => {
  const { t } = useTranslation();

  // State
  const [prompts, setPrompts] = useState<PromptSummary[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptDetail | null>(null);
  const [editedContent, setEditedContent] = useState('');
  const [hasChanges, setHasChanges] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // History panel
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<PromptHistoryType[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Category collapse state
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());

  // Load prompts on mount
  useEffect(() => {
    loadPrompts();
  }, []);

  const loadPrompts = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await promptsApi.listPrompts();
      setPrompts(data);
    } catch (err) {
      console.error('Failed to load prompts:', err);
      setError(t('common.prompts.errors.loadFailed') || 'Failed to load prompts');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPrompt = async (promptId: string) => {
    // Warn about unsaved changes
    if (hasChanges) {
      if (!confirm(t('common.prompts.unsavedChanges') || 'You have unsaved changes. Continue?')) {
        return;
      }
    }

    try {
      setError(null);
      const detail = await promptsApi.getPrompt(promptId);
      setSelectedPrompt(detail);
      setEditedContent(detail.content);
      setHasChanges(false);
      setShowHistory(false);
    } catch (err) {
      console.error('Failed to load prompt:', err);
      setError(t('common.prompts.errors.loadDetailFailed') || 'Failed to load prompt details');
    }
  };

  const handleContentChange = useCallback((content: string) => {
    setEditedContent(content);
    setHasChanges(content !== selectedPrompt?.content);
  }, [selectedPrompt?.content]);

  const handleSave = async () => {
    if (!selectedPrompt || !hasChanges) return;

    try {
      setSaving(true);
      setError(null);
      const updated = await promptsApi.updatePrompt(selectedPrompt.prompt_id, {
        content: editedContent,
        reason: 'Updated via Admin UI',
      });
      setSelectedPrompt(updated);
      setHasChanges(false);

      // Reload prompts list to update preview
      loadPrompts();
    } catch (err) {
      console.error('Failed to save prompt:', err);
      setError(t('common.prompts.errors.saveFailed') || 'Failed to save prompt');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (selectedPrompt) {
      setEditedContent(selectedPrompt.content);
      setHasChanges(false);
    }
  };

  const handleToggleHistory = async () => {
    if (!selectedPrompt) return;

    if (showHistory) {
      setShowHistory(false);
      return;
    }

    try {
      setLoadingHistory(true);
      const data = await promptsApi.getHistory(selectedPrompt.prompt_id);
      setHistory(data);
      setShowHistory(true);
    } catch (err) {
      console.error('Failed to load history:', err);
      setError(t('common.prompts.errors.loadHistoryFailed') || 'Failed to load history');
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleRollback = async (versionId: string) => {
    if (!selectedPrompt) return;

    if (!confirm(t('common.prompts.confirmRollback') || 'Are you sure you want to rollback to this version?')) {
      return;
    }

    try {
      setSaving(true);
      setError(null);
      const updated = await promptsApi.rollbackPrompt(selectedPrompt.prompt_id, versionId);
      setSelectedPrompt(updated);
      setEditedContent(updated.content);
      setHasChanges(false);
      setShowHistory(false);

      // Reload history
      const newHistory = await promptsApi.getHistory(selectedPrompt.prompt_id);
      setHistory(newHistory);
    } catch (err) {
      console.error('Failed to rollback:', err);
      setError(t('common.prompts.errors.rollbackFailed') || 'Failed to rollback prompt');
    } finally {
      setSaving(false);
    }
  };

  const toggleCategory = (category: string) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) {
        next.delete(category);
      } else {
        next.add(category);
      }
      return next;
    });
  };

  // Group prompts by category
  const promptsByCategory = prompts.reduce<Record<string, PromptSummary[]>>((acc, prompt) => {
    if (!acc[prompt.category]) {
      acc[prompt.category] = [];
    }
    acc[prompt.category].push(prompt);
    return acc;
  }, {});

  // Sort categories
  const sortedCategories = Object.keys(promptsByCategory).sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b)
  );

  if (loading) {
    return <div className="prompt-tab-loading">{t('common.loading') || 'Loading...'}</div>;
  }

  return (
    <div className="prompt-tab">
      {/* Error banner */}
      {error && (
        <div className="prompt-tab-error">
          <span>{error}</span>
          <button onClick={() => setError(null)} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className="prompt-tab-content">
        {/* Left: Prompt List */}
        <div className="prompt-list">
          {sortedCategories.map((category) => (
            <div key={category} className="prompt-list-category">
              <div
                className="prompt-list-category-header"
                onClick={() => toggleCategory(category)}
              >
                <span
                  className={`prompt-list-category-icon ${
                    collapsedCategories.has(category) ? 'collapsed' : ''
                  }`}
                >
                  ▼
                </span>
                <span>{CATEGORY_ICONS[category] || '📄'}</span>
                <span>
                  {t(`common.prompts.categories.${category}`) ||
                    category.charAt(0).toUpperCase() + category.slice(1)}
                </span>
              </div>
              {!collapsedCategories.has(category) && (
                <div className="prompt-list-items">
                  {promptsByCategory[category].map((prompt) => (
                    <div
                      key={prompt.prompt_id}
                      className={`prompt-list-item ${
                        selectedPrompt?.prompt_id === prompt.prompt_id ? 'selected' : ''
                      }`}
                      onClick={() => handleSelectPrompt(prompt.prompt_id)}
                    >
                      <span className="prompt-list-item-name">{prompt.name}</span>
                      {prompt.is_readonly && (
                        <span className="prompt-list-item-readonly">🔒</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Right: Editor Panel */}
        <div className="prompt-editor-panel">
          {selectedPrompt ? (
            <>
              {/* Metadata Header */}
              <div className="prompt-metadata">
                <h2>{selectedPrompt.name}</h2>
                <div className="prompt-metadata-badges">
                  <span className="prompt-badge category">{selectedPrompt.category}</span>
                  <span className="prompt-badge language">{selectedPrompt.language}</span>
                  {selectedPrompt.is_readonly && (
                    <span className="prompt-badge readonly">
                      {t('common.prompts.readonly') || 'Read-only'}
                    </span>
                  )}
                </div>
                {selectedPrompt.description && (
                  <p className="prompt-description">{selectedPrompt.description}</p>
                )}
              </div>

              {/* Editor */}
              <div className="prompt-editor-container">
                <textarea
                  className="prompt-editor-textarea"
                  value={editedContent}
                  onChange={(e) => handleContentChange(e.target.value)}
                  disabled={selectedPrompt.is_readonly}
                  spellCheck={false}
                />
              </div>

              {/* Actions */}
              <div className="prompt-actions">
                <button
                  onClick={handleSave}
                  disabled={!hasChanges || selectedPrompt.is_readonly || saving}
                  className="btn-primary"
                >
                  {saving ? (t('common.saving') || 'Saving...') : (t('common.save') || 'Save')}
                </button>
                <button
                  onClick={handleReset}
                  disabled={!hasChanges}
                  className="btn-secondary"
                >
                  {t('common.reset') || 'Reset'}
                </button>
                <button
                  onClick={handleToggleHistory}
                  className="btn-tertiary"
                  disabled={loadingHistory}
                >
                  {loadingHistory
                    ? (t('common.loading') || 'Loading...')
                    : `${t('common.prompts.history') || 'History'} (${selectedPrompt.version_count})`}
                </button>

                <div className="prompt-actions-spacer" />

                {/* Unsaved indicator */}
                {hasChanges && (
                  <div className="prompt-unsaved-indicator">
                    <span className="prompt-unsaved-dot" />
                    <span>{t('common.prompts.unsavedChanges') || 'Unsaved changes'}</span>
                  </div>
                )}
              </div>

              {/* History Panel */}
              {showHistory && (
                <div className="prompt-history">
                  <div className="prompt-history-header">
                    <h3>{t('common.prompts.versionHistory') || 'Version History'}</h3>
                    <button
                      className="prompt-history-close"
                      onClick={() => setShowHistory(false)}
                    >
                      ×
                    </button>
                  </div>
                  {history.length > 0 ? (
                    <div className="prompt-history-list">
                      {history.map((item) => (
                        <div key={item.id} className="prompt-history-item">
                          <div className="prompt-history-info">
                            <span className="prompt-history-version">
                              v{item.version_number}
                            </span>
                            <span className="prompt-history-date">
                              {new Date(item.changed_at).toLocaleString()}
                            </span>
                            {item.change_reason && (
                              <span className="prompt-history-reason">
                                {item.change_reason}
                              </span>
                            )}
                          </div>
                          <button
                            className="prompt-history-rollback"
                            onClick={() => handleRollback(item.id)}
                            disabled={saving || selectedPrompt.is_readonly}
                          >
                            {t('common.prompts.rollback') || 'Rollback'}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="prompt-history-empty">
                      {t('common.prompts.noHistory') || 'No version history available'}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="prompt-placeholder">
              {t('common.prompts.selectPrompt') || 'Select a prompt to edit'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PromptTab;
