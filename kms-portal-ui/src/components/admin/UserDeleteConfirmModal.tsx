/**
 * User Delete Confirm Modal Component
 * Confirmation dialog before deleting a user
 */

import React, { useState, useEffect } from 'react';
import { X, Trash2, AlertTriangle, Loader2 } from 'lucide-react';
import type { UserData } from './UserManagementTable';

interface UserDeleteConfirmModalProps {
  user: UserData;
  onClose: () => void;
  onConfirm: () => void;
}

const UserDeleteConfirmModal: React.FC<UserDeleteConfirmModalProps> = ({
  user,
  onClose,
  onConfirm,
}) => {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState('');

  const canDelete = confirmText.toLowerCase() === 'delete';

  // Handle delete
  const handleDelete = async () => {
    if (!canDelete) return;

    try {
      setDeleting(true);
      setError(null);

      const response = await fetch(`/api/v1/admin/users/${user.id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail?.message || `HTTP ${response.status}`);
      }

      onConfirm();
    } catch (err) {
      console.error('Failed to delete user:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete user');
    } finally {
      setDeleting(false);
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
        <div className="modal-header modal-header--danger">
          <h2>Delete User</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          <div className="delete-warning">
            <AlertTriangle size={48} className="delete-warning-icon" />
            <p className="delete-warning-text">
              Are you sure you want to delete this user?
            </p>
            <p className="delete-warning-subtext">
              This action cannot be undone.
            </p>
          </div>

          <div className="delete-user-info">
            <div><strong>Username:</strong> {user.username}</div>
            <div><strong>Email:</strong> {user.email}</div>
            <div><strong>Role:</strong> {user.role}</div>
          </div>

          {error && (
            <div className="modal-error">
              {error}
            </div>
          )}

          <div className="form-group">
            <label>Type "delete" to confirm:</label>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="delete"
              autoFocus
            />
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn--secondary" onClick={onClose} disabled={deleting}>
            Cancel
          </button>
          <button
            className="btn btn--danger"
            onClick={handleDelete}
            disabled={!canDelete || deleting}
          >
            {deleting ? (
              <>
                <Loader2 className="spinning" size={16} />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 size={16} />
                Delete User
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default UserDeleteConfirmModal;
