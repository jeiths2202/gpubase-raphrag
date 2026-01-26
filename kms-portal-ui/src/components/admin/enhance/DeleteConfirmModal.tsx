/**
 * Delete Confirmation Modal Component
 * Displays a confirmation dialog before deleting an enhancement request
 */
import React from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  isDeleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  isDeleting,
  onClose,
  onConfirm,
}) => {
  if (!isOpen) return null;

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
        <div className="admin-modal-header">
          <AlertTriangle size={24} color="#ef4444" />
          <h3>Delete Enhancement Request</h3>
        </div>
        <div className="admin-modal-body">
          <p>Are you sure you want to delete this enhancement request?</p>
          <p className="admin-modal-warning">This action cannot be undone.</p>
        </div>
        <div className="admin-modal-footer">
          <button className="admin-btn admin-btn--secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="admin-btn admin-btn--danger"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting ? (
              <>
                <Loader2 size={16} className="spinning" />
                Deleting...
              </>
            ) : (
              'Delete'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
