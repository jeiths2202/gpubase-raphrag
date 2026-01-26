/**
 * User Details Modal Component
 * Edit user information (role, status, display_name, department, email)
 */

import React, { useState, useEffect } from 'react';
import { X, Save, Loader2 } from 'lucide-react';
import type { UserData } from './UserManagementTable';

interface UserDetailsModalProps {
  user: UserData;
  onClose: () => void;
  onSave: (updatedUser: UserData) => void;
}

const ROLES = ['admin', 'leader', 'senior', 'user', 'guest'];
const STATUSES = ['active', 'inactive', 'pending', 'suspended'];

const UserDetailsModal: React.FC<UserDetailsModalProps> = ({
  user,
  onClose,
  onSave,
}) => {
  const [formData, setFormData] = useState({
    display_name: user.username || '',
    email: user.email || '',
    role: user.role || 'user',
    status: user.is_active ? 'active' : (user.is_verified ? 'inactive' : 'pending'),
    department: user.department || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle input change
  const handleChange = (field: string, value: string) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  // Handle save
  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const response = await fetch(`/api/v1/admin/users/${user.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail?.message || `HTTP ${response.status}`);
      }

      const result = await response.json();
      onSave({
        ...user,
        ...result.data,
      });
    } catch (err) {
      console.error('Failed to save user:', err);
      setError(err instanceof Error ? err.message : 'Failed to save user');
    } finally {
      setSaving(false);
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
      <div className="modal-content modal-content--medium" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit User</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {error && (
            <div className="modal-error">
              {error}
            </div>
          )}

          <div className="form-group">
            <label>Display Name</label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) => handleChange('display_name', e.target.value)}
              placeholder="Enter display name"
            />
          </div>

          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={formData.email}
              onChange={(e) => handleChange('email', e.target.value)}
              placeholder="Enter email"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Role</label>
              <select
                value={formData.role}
                onChange={(e) => handleChange('role', e.target.value)}
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role.charAt(0).toUpperCase() + role.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Status</label>
              <select
                value={formData.status}
                onChange={(e) => handleChange('status', e.target.value)}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label>Department</label>
            <input
              type="text"
              value={formData.department}
              onChange={(e) => handleChange('department', e.target.value)}
              placeholder="Enter department"
            />
          </div>

          <div className="form-info">
            <strong>User ID:</strong> {user.id}
            <br />
            <strong>Created:</strong> {user.created_at ? new Date(user.created_at).toLocaleString() : 'N/A'}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn--secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="spinning" size={16} />
                Saving...
              </>
            ) : (
              <>
                <Save size={16} />
                Save Changes
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default UserDetailsModal;
