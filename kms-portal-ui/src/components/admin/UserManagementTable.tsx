/**
 * User Management Table Component
 * Displays list of users with search, pagination, and action buttons
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Edit,
  BarChart2,
  Key,
  Trash2,
  User,
  MoreVertical,
  Loader2,
} from 'lucide-react';

// Types
export interface UserData {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string | null;
  department?: string;
  last_login_at?: string | null;
}

interface UserListResponse {
  users: UserData[];
  total_count: number;
  page: number;
  limit: number;
  total_pages: number;
}

interface UserManagementTableProps {
  onEditUser: (user: UserData) => void;
  onViewUsage: (user: UserData) => void;
  onResetPassword: (user: UserData) => void;
  onDeleteUser: (user: UserData) => void;
}

// Role badge colors
const ROLE_COLORS: Record<string, string> = {
  admin: '#ef4444',
  leader: '#f59e0b',
  senior: '#8b5cf6',
  user: '#6366f1',
  guest: '#9ca3af',
};

// Status badge colors
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  active: { bg: '#dcfce7', text: '#166534' },
  inactive: { bg: '#fef3c7', text: '#92400e' },
  pending: { bg: '#dbeafe', text: '#1e40af' },
  suspended: { bg: '#fee2e2', text: '#991b1b' },
};

const UserManagementTable: React.FC<UserManagementTableProps> = ({
  onEditUser,
  onViewUsage,
  onResetPassword,
  onDeleteUser,
}) => {
  const [users, setUsers] = useState<UserData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const limit = 10;

  // Fetch users
  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page.toString(),
        limit: limit.toString(),
      });
      if (search) {
        params.append('search', search);
      }

      const response = await fetch(`/api/v1/admin/users?${params}`, {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      const data: UserListResponse = result.data;

      setUsers(data.users);
      setTotalPages(data.total_pages);
      setTotalCount(data.total_count);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch users:', err);
      setError('Failed to load users');
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Search handler with debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      if (page !== 1) {
        setPage(1);
      } else {
        fetchUsers();
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Get status from is_active and is_verified
  const getStatus = (user: UserData): string => {
    if (!user.is_verified) return 'pending';
    if (user.is_active) return 'active';
    return 'inactive';
  };

  // Format date
  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

  // Format relative time
  const formatRelativeTime = (dateStr: string | null): string => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const days = Math.floor(hours / 24);

    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return formatDate(dateStr);
  };

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = () => setOpenMenu(null);
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  return (
    <div className="user-management-table">
      {/* Search Bar */}
      <div className="user-table-header">
        <div className="user-search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search by email or username..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="user-table-info">
          {totalCount} users total
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="user-table-loading">
          <Loader2 className="spinning" size={24} />
          <span>Loading users...</span>
        </div>
      ) : error ? (
        <div className="user-table-error">
          <span>{error}</span>
          <button onClick={fetchUsers}>Retry</button>
        </div>
      ) : (
        <>
          <div className="user-table-container">
            <table className="user-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Department</th>
                  <th>Created</th>
                  <th>Last Login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="user-table-empty">
                      No users found
                    </td>
                  </tr>
                ) : (
                  users.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div className="user-cell">
                          <div className="user-avatar">
                            <User size={16} />
                          </div>
                          <div className="user-info">
                            <span className="user-name">{user.username || user.email.split('@')[0]}</span>
                            <span className="user-email">{user.email}</span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span
                          className="role-badge"
                          style={{ backgroundColor: ROLE_COLORS[user.role] || '#9ca3af' }}
                        >
                          {user.role}
                        </span>
                      </td>
                      <td>
                        <span
                          className="status-badge"
                          style={{
                            backgroundColor: STATUS_COLORS[getStatus(user)]?.bg || '#f3f4f6',
                            color: STATUS_COLORS[getStatus(user)]?.text || '#374151',
                          }}
                        >
                          {getStatus(user)}
                        </span>
                      </td>
                      <td>{user.department || '-'}</td>
                      <td>{formatDate(user.created_at)}</td>
                      <td>{formatRelativeTime(user.last_login_at || null)}</td>
                      <td>
                        <div className="user-actions">
                          <button
                            className="action-btn action-btn--edit"
                            onClick={() => onEditUser(user)}
                            title="Edit user"
                          >
                            <Edit size={16} />
                          </button>
                          <button
                            className="action-btn action-btn--usage"
                            onClick={() => onViewUsage(user)}
                            title="View usage"
                          >
                            <BarChart2 size={16} />
                          </button>
                          <div className="action-menu-container">
                            <button
                              className="action-btn action-btn--more"
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenMenu(openMenu === user.id ? null : user.id);
                              }}
                            >
                              <MoreVertical size={16} />
                            </button>
                            {openMenu === user.id && (
                              <div className="action-menu">
                                <button onClick={() => { onResetPassword(user); setOpenMenu(null); }}>
                                  <Key size={14} />
                                  Reset Password
                                </button>
                                <button
                                  className="action-menu-item--danger"
                                  onClick={() => { onDeleteUser(user); setOpenMenu(null); }}
                                >
                                  <Trash2 size={14} />
                                  Delete User
                                </button>
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="user-pagination">
              <button
                className="pagination-btn"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                <ChevronLeft size={18} />
                Previous
              </button>
              <span className="pagination-info">
                Page {page} of {totalPages}
              </span>
              <button
                className="pagination-btn"
                disabled={page === totalPages}
                onClick={() => setPage(page + 1)}
              >
                Next
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UserManagementTable;
