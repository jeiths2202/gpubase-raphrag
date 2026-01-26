/**
 * IMS Credentials Modal Component
 *
 * Modal dialog for entering IMS (Issue Management System) login credentials.
 * Used when the IMS agent requires authentication to search issues.
 */

import React, { useState, useCallback } from 'react';
import { Lock, X, Loader2, AlertCircle } from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

export interface IMSCredentialsModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Callback when modal is closed (cancel or backdrop click) */
  onClose: () => void;
  /** Callback when credentials are successfully saved */
  onSuccess: () => void;
  /** Translation function */
  t: (key: string) => string;
}

// ============================================================================
// Component
// ============================================================================

export const IMSCredentialsModal: React.FC<IMSCredentialsModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  t,
}) => {
  // Form state
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset form state
  const resetForm = useCallback(() => {
    setUsername('');
    setPassword('');
    setError(null);
    setIsSubmitting(false);
  }, []);

  // Handle close
  const handleClose = useCallback(() => {
    resetForm();
    onClose();
  }, [resetForm, onClose]);

  // Handle submit
  const handleSubmit = useCallback(async () => {
    if (!username.trim() || !password.trim()) {
      setError(t('common.agent.credentials.emptyFields') || 'Please fill in all fields');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/ims-credentials/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          ims_url: 'https://ims.tmaxsoft.com',
          username: username,
          password: password,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to save credentials');
      }

      // Success - reset form and call success callback
      resetForm();
      onSuccess();
    } catch (err) {
      console.error('Failed to save IMS credentials:', err);
      setError(
        err instanceof Error
          ? err.message
          : t('common.agent.credentials.saveError') || 'Failed to save credentials'
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [username, password, t, resetForm, onSuccess]);

  // Handle key press in password field
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !isSubmitting) {
        handleSubmit();
      }
    },
    [handleSubmit, isSubmitting]
  );

  // Don't render if not open
  if (!isOpen) return null;

  return (
    <div className="agent-credentials-modal-overlay" onClick={handleClose}>
      <div className="agent-credentials-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="agent-credentials-modal-header">
          <div className="agent-credentials-modal-title">
            <Lock size={20} />
            <h3>{t('common.agent.credentials.title') || 'IMS Login Required'}</h3>
          </div>
          <button className="agent-credentials-modal-close" onClick={handleClose}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="agent-credentials-modal-body">
          <p className="agent-credentials-modal-description">
            {t('common.agent.credentials.description') ||
              'Please enter your IMS credentials to search the Issue Management System.'}
          </p>

          {/* Error message */}
          {error && (
            <div className="agent-credentials-error">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <div className="agent-credentials-form">
            <div className="agent-credentials-field">
              <label htmlFor="ims-username">
                {t('common.agent.credentials.username') || 'Username'}
              </label>
              <input
                id="ims-username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={t('common.agent.credentials.usernamePlaceholder') || 'Enter IMS username'}
                disabled={isSubmitting}
                autoFocus
              />
            </div>

            <div className="agent-credentials-field">
              <label htmlFor="ims-password">
                {t('common.agent.credentials.password') || 'Password'}
              </label>
              <input
                id="ims-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('common.agent.credentials.passwordPlaceholder') || 'Enter IMS password'}
                disabled={isSubmitting}
                onKeyDown={handleKeyDown}
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="agent-credentials-modal-footer">
          <button
            className="agent-credentials-cancel-btn"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            {t('common.cancel') || 'Cancel'}
          </button>
          <button
            className="agent-credentials-submit-btn"
            onClick={handleSubmit}
            disabled={isSubmitting || !username.trim() || !password.trim()}
          >
            {isSubmitting ? (
              <>
                <Loader2 size={16} className="spin" />
                <span>{t('common.agent.credentials.saving') || 'Saving...'}</span>
              </>
            ) : (
              <>
                <Lock size={16} />
                <span>{t('common.agent.credentials.login') || 'Login'}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default IMSCredentialsModal;
