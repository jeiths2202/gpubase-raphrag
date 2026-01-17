/**
 * Password Reset Modal Component
 * Reset user password and show temporary password
 */

import React, { useState, useEffect } from 'react';
import { X, Key, Copy, Check, Loader2 } from 'lucide-react';
import type { UserData } from './UserManagementTable';

interface PasswordResetModalProps {
  user: UserData;
  onClose: () => void;
}

const PasswordResetModal: React.FC<PasswordResetModalProps> = ({
  user,
  onClose,
}) => {
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Handle reset
  const handleReset = async () => {
    try {
      setResetting(true);
      setError(null);

      const response = await fetch(`/api/v1/admin/users/${user.id}/password-reset`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail?.message || `HTTP ${response.status}`);
      }

      const result = await response.json();
      setTempPassword(result.data.temporary_password);
    } catch (err) {
      console.error('Failed to reset password:', err);
      setError(err instanceof Error ? err.message : 'Failed to reset password');
    } finally {
      setResetting(false);
    }
  };

  // Copy to clipboard
  const handleCopy = async () => {
    if (!tempPassword) return;
    try {
      await navigator.clipboard.writeText(tempPassword);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  // Close on escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-content--small" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Reset Password</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {!tempPassword ? (
            <>
              <div className="reset-info">
                <Key size={48} className="reset-icon" />
                <p>
                  Reset password for <strong>{user.email}</strong>?
                </p>
                <p className="reset-subtext">
                  A temporary password will be generated.
                </p>
              </div>

              {error && (
                <div className="modal-error">
                  {error}
                </div>
              )}
            </>
          ) : (
            <div className="reset-success">
              <div className="reset-success-icon">
                <Check size={32} />
              </div>
              <p className="reset-success-text">Password has been reset!</p>
              <div className="temp-password-box">
                <label>Temporary Password:</label>
                <div className="temp-password-value">
                  <code>{tempPassword}</code>
                  <button
                    className="copy-btn"
                    onClick={handleCopy}
                    title="Copy to clipboard"
                  >
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                </div>
              </div>
              <p className="reset-note">
                Please share this password securely with the user.
                They will be required to change it on first login.
              </p>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {!tempPassword ? (
            <>
              <button className="btn btn--secondary" onClick={onClose} disabled={resetting}>
                Cancel
              </button>
              <button className="btn btn--primary" onClick={handleReset} disabled={resetting}>
                {resetting ? (
                  <>
                    <Loader2 className="spinning" size={16} />
                    Resetting...
                  </>
                ) : (
                  <>
                    <Key size={16} />
                    Reset Password
                  </>
                )}
              </button>
            </>
          ) : (
            <button className="btn btn--primary" onClick={onClose}>
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default PasswordResetModal;
