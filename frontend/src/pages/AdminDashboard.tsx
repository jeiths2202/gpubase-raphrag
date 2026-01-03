import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { API_BASE_URL } from '../config/constants';
import './AdminDashboard.css';

interface User {
  id: string;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  is_verified: boolean;
  created_at?: string;
}

interface UserStats {
  total_users: number;
  active_users: number;
  inactive_users: number;
  admin_users: number;
  regular_users: number;
  pending_verification: number;
}

interface TokenOverview {
  total_tokens_issued: number;
  daily_average: number;
  avg_processing_time_ms: number;
  slowest_token: {
    token_id: string;
    user_id: string;
    processing_time_ms: number;
    endpoint: string;
    issued_at: string;
  } | null;
  today_count: number;
  today_avg_time_ms: number;
}

interface UserTokenStats {
  user_id: string;
  total_tokens: number;
  avg_processing_time_ms: number;
  max_processing_time_ms: number;
  min_processing_time_ms: number;
  most_used_endpoint: string;
  endpoint_breakdown: Record<string, number>;
}

interface DailyStats {
  date: string;
  count: number;
  avg_processing_time_ms: number;
}

type TabType = 'users' | 'tokens';

const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>('users');

  // User management state
  const [users, setUsers] = useState<User[]>([]);
  const [stats, setStats] = useState<UserStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Token statistics state
  const [tokenOverview, setTokenOverview] = useState<TokenOverview | null>(null);
  const [userTokenStats, setUserTokenStats] = useState<UserTokenStats[]>([]);
  const [dailyStats, setDailyStats] = useState<DailyStats[]>([]);
  const [isLoadingTokens, setIsLoadingTokens] = useState(false);

  const fetchUsers = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        page: currentPage.toString(),
        limit: '10',
      });
      if (searchQuery) {
        params.append('search', searchQuery);
      }

      const response = await fetch(`${API_BASE_URL}/admin/users?${params}`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.status === 403) {
        setError('관리자 권한이 필요합니다.');
        return;
      }

      const data = await response.json();
      if (data.data) {
        setUsers(data.data.users);
        setTotalPages(data.data.total_pages);
      }
    } catch {
      setError('사용자 목록을 불러오는데 실패했습니다.');
    }
  }, [currentPage, searchQuery]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/stats`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await response.json();
      if (data.data) {
        setStats(data.data);
      }
    } catch {
      console.error('Failed to fetch stats');
    }
  }, []);

  const fetchTokenStats = useCallback(async () => {
    setIsLoadingTokens(true);
    try {
      const [overviewRes, userStatsRes, dailyRes] = await Promise.all([
        fetch(`${API_BASE_URL}/admin/tokens/overview`, {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        }),
        fetch(`${API_BASE_URL}/admin/tokens/users`, {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        }),
        fetch(`${API_BASE_URL}/admin/tokens/daily?days=7`, {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        }),
      ]);

      const [overviewData, userStatsData, dailyData] = await Promise.all([
        overviewRes.json(),
        userStatsRes.json(),
        dailyRes.json(),
      ]);

      if (overviewData.data) setTokenOverview(overviewData.data);
      if (userStatsData.data) setUserTokenStats(userStatsData.data);
      if (dailyData.data) setDailyStats(dailyData.data);
    } catch {
      console.error('Failed to fetch token stats');
    } finally {
      setIsLoadingTokens(false);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      await Promise.all([fetchUsers(), fetchStats(), fetchTokenStats()]);
      setIsLoading(false);
    };
    loadData();
  }, [fetchUsers, fetchStats, fetchTokenStats]);

  const handleToggleActive = async (userId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/users/${userId}/toggle-active`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (response.ok) {
        fetchUsers();
        fetchStats();
      }
    } catch {
      setError('상태 변경에 실패했습니다.');
    }
  };

  const handleUpdateUser = async (userId: string, updates: Partial<User>) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/users/${userId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates),
      });

      if (response.ok) {
        setShowEditModal(false);
        setSelectedUser(null);
        fetchUsers();
        fetchStats();
      }
    } catch {
      setError('사용자 정보 수정에 실패했습니다.');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!confirm('정말로 이 사용자를 삭제하시겠습니까?')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/admin/users/${userId}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      const data = await response.json();

      if (response.ok) {
        fetchUsers();
        fetchStats();
      } else {
        setError(data.detail?.message || '삭제에 실패했습니다.');
      }
    } catch {
      setError('삭제 요청에 실패했습니다.');
    }
  };

  // Check if current user is admin
  if (user?.role !== 'admin') {
    return (
      <div className="admin-container">
        <div className="admin-bg">
          <div className="gradient-orb orb-1" />
          <div className="gradient-orb orb-2" />
        </div>
        <div className="access-denied">
          <h1>접근 거부</h1>
          <p>관리자 권한이 필요합니다.</p>
          <button onClick={() => navigate('/')}>돌아가기</button>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-container">
      {/* Background */}
      <div className="admin-bg">
        <div className="gradient-orb orb-1" />
        <div className="gradient-orb orb-2" />
        <div className="gradient-orb orb-3" />
      </div>

      {/* Header */}
      <header className="admin-header">
        <div className="header-left">
          <h1>관리자 대시보드</h1>
          <span className="admin-badge">Admin</span>
        </div>
        <div className="header-right">
          <span className="user-info">{user?.name || user?.email}</span>
          <button className="btn-nav" onClick={() => navigate('/')}>
            메인으로
          </button>
          <button className="btn-logout" onClick={logout}>
            로그아웃
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="admin-main">
        {/* User Stats Cards */}
        {stats && (
          <motion.section
            className="stats-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="stat-card">
              <div className="stat-icon">👥</div>
              <div className="stat-content">
                <span className="stat-value">{stats.total_users}</span>
                <span className="stat-label">전체 사용자</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">✅</div>
              <div className="stat-content">
                <span className="stat-value">{stats.active_users}</span>
                <span className="stat-label">활성 사용자</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">🛡️</div>
              <div className="stat-content">
                <span className="stat-value">{stats.admin_users}</span>
                <span className="stat-label">관리자</span>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">⏳</div>
              <div className="stat-content">
                <span className="stat-value">{stats.pending_verification}</span>
                <span className="stat-label">인증 대기</span>
              </div>
            </div>
          </motion.section>
        )}

        {/* Token Stats Cards */}
        {tokenOverview && (
          <motion.section
            className="stats-section token-stats"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
          >
            <div className="stat-card token">
              <div className="stat-icon">🎫</div>
              <div className="stat-content">
                <span className="stat-value">{tokenOverview.daily_average.toFixed(1)}</span>
                <span className="stat-label">일평균 토큰 발행</span>
              </div>
            </div>
            <div className="stat-card token">
              <div className="stat-icon">⚡</div>
              <div className="stat-content">
                <span className="stat-value">{tokenOverview.avg_processing_time_ms.toFixed(0)}ms</span>
                <span className="stat-label">평균 처리 시간</span>
              </div>
            </div>
            <div className="stat-card token">
              <div className="stat-icon">🐢</div>
              <div className="stat-content">
                <span className="stat-value">{tokenOverview.slowest_token?.processing_time_ms || 0}ms</span>
                <span className="stat-label">최장 처리 시간</span>
              </div>
            </div>
            <div className="stat-card token">
              <div className="stat-icon">📊</div>
              <div className="stat-content">
                <span className="stat-value">{tokenOverview.today_count}</span>
                <span className="stat-label">오늘 발행 수</span>
              </div>
            </div>
          </motion.section>
        )}

        {/* Tab Navigation */}
        <div className="tab-nav">
          <button
            className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
          >
            👥 사용자 관리
          </button>
          <button
            className={`tab-btn ${activeTab === 'tokens' ? 'active' : ''}`}
            onClick={() => setActiveTab('tokens')}
          >
            🎫 토큰 통계
          </button>
        </div>

        {/* Error Message */}
        <AnimatePresence>
          {error && (
            <motion.div
              className="error-banner"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
            >
              {error}
              <button onClick={() => setError(null)}>×</button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Users Tab */}
        {activeTab === 'users' && (
          <motion.section
            className="users-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <div className="section-header">
              <h2>사용자 관리</h2>
              <div className="search-box">
                <input
                  type="text"
                  placeholder="사용자 검색..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                />
              </div>
            </div>

            {isLoading ? (
              <div className="loading-state">
                <div className="spinner" />
                <span>로딩 중...</span>
              </div>
            ) : (
              <>
                <div className="users-table">
                  <div className="table-header">
                    <span>사용자 ID</span>
                    <span>이메일</span>
                    <span>역할</span>
                    <span>상태</span>
                    <span>인증</span>
                    <span>작업</span>
                  </div>
                  {users.map((u) => (
                    <motion.div
                      key={u.id}
                      className="table-row"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      whileHover={{ backgroundColor: 'rgba(255,255,255,0.05)' }}
                    >
                      <span className="user-name">{u.username}</span>
                      <span className="user-email">{u.email}</span>
                      <span className={`role-badge ${u.role}`}>
                        {u.role === 'admin' ? '관리자' : '사용자'}
                      </span>
                      <span className={`status-badge ${u.is_active ? 'active' : 'inactive'}`}>
                        {u.is_active ? '활성' : '비활성'}
                      </span>
                      <span className={`verify-badge ${u.is_verified ? 'verified' : 'unverified'}`}>
                        {u.is_verified ? '완료' : '대기'}
                      </span>
                      <div className="actions">
                        <button
                          className="btn-action edit"
                          onClick={() => {
                            setSelectedUser(u);
                            setShowEditModal(true);
                          }}
                          title="수정"
                        >
                          ✏️
                        </button>
                        <button
                          className="btn-action toggle"
                          onClick={() => handleToggleActive(u.id)}
                          title={u.is_active ? '비활성화' : '활성화'}
                        >
                          {u.is_active ? '🔒' : '🔓'}
                        </button>
                        <button
                          className="btn-action delete"
                          onClick={() => handleDeleteUser(u.id)}
                          title="삭제"
                          disabled={u.username === 'admin'}
                        >
                          🗑️
                        </button>
                      </div>
                    </motion.div>
                  ))}
                  {users.length === 0 && (
                    <div className="empty-state">
                      사용자가 없습니다.
                    </div>
                  )}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="pagination">
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage(p => p - 1)}
                    >
                      이전
                    </button>
                    <span>{currentPage} / {totalPages}</span>
                    <button
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage(p => p + 1)}
                    >
                      다음
                    </button>
                  </div>
                )}
              </>
            )}
          </motion.section>
        )}

        {/* Tokens Tab */}
        {activeTab === 'tokens' && (
          <motion.section
            className="tokens-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            {/* Daily Stats Chart */}
            <div className="token-panel">
              <h3>📈 일별 토큰 발행 현황 (최근 7일)</h3>
              {isLoadingTokens ? (
                <div className="loading-state small">
                  <div className="spinner" />
                </div>
              ) : (
                <div className="daily-chart">
                  {dailyStats.map((day, idx) => {
                    const maxCount = Math.max(...dailyStats.map(d => d.count), 1);
                    const heightPercent = (day.count / maxCount) * 100;
                    return (
                      <div key={idx} className="chart-bar-container">
                        <div className="chart-bar-wrapper">
                          <motion.div
                            className="chart-bar"
                            initial={{ height: 0 }}
                            animate={{ height: `${heightPercent}%` }}
                            transition={{ duration: 0.5, delay: idx * 0.1 }}
                          />
                        </div>
                        <span className="chart-value">{day.count}</span>
                        <span className="chart-label">{day.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Slowest Token Info */}
            {tokenOverview?.slowest_token && (
              <div className="token-panel slowest">
                <h3>🐢 가장 느린 토큰 처리</h3>
                <div className="slowest-info">
                  <div className="info-row">
                    <span className="info-label">토큰 ID:</span>
                    <span className="info-value mono">{tokenOverview.slowest_token.token_id}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">사용자:</span>
                    <span className="info-value">{tokenOverview.slowest_token.user_id}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">처리 시간:</span>
                    <span className="info-value highlight">{tokenOverview.slowest_token.processing_time_ms}ms</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">엔드포인트:</span>
                    <span className="info-value mono">{tokenOverview.slowest_token.endpoint}</span>
                  </div>
                </div>
              </div>
            )}

            {/* User Token Stats Table */}
            <div className="token-panel">
              <h3>👥 유저별 토큰 사용 통계</h3>
              {isLoadingTokens ? (
                <div className="loading-state small">
                  <div className="spinner" />
                </div>
              ) : (
                <div className="token-table">
                  <div className="table-header">
                    <span>사용자 ID</span>
                    <span>총 토큰 수</span>
                    <span>평균 처리 시간</span>
                    <span>최대 처리 시간</span>
                    <span>최소 처리 시간</span>
                    <span>주 사용 API</span>
                  </div>
                  {userTokenStats.map((stat) => (
                    <motion.div
                      key={stat.user_id}
                      className="table-row"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      whileHover={{ backgroundColor: 'rgba(255,255,255,0.05)' }}
                    >
                      <span className="user-id">{stat.user_id}</span>
                      <span className="token-count">{stat.total_tokens}</span>
                      <span className="time-avg">{stat.avg_processing_time_ms.toFixed(1)}ms</span>
                      <span className="time-max">{stat.max_processing_time_ms}ms</span>
                      <span className="time-min">{stat.min_processing_time_ms}ms</span>
                      <span className="endpoint mono">{stat.most_used_endpoint.split('/').pop()}</span>
                    </motion.div>
                  ))}
                  {userTokenStats.length === 0 && (
                    <div className="empty-state">
                      토큰 사용 데이터가 없습니다.
                    </div>
                  )}
                </div>
              )}
            </div>
          </motion.section>
        )}
      </main>

      {/* Edit Modal */}
      <AnimatePresence>
        {showEditModal && selectedUser && (
          <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowEditModal(false)}
          >
            <motion.div
              className="modal-content"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
            >
              <h3>사용자 수정</h3>
              <div className="form-group">
                <label>사용자 ID</label>
                <input type="text" value={selectedUser.username} disabled />
              </div>
              <div className="form-group">
                <label>이메일</label>
                <input
                  type="email"
                  defaultValue={selectedUser.email}
                  id="edit-email"
                />
              </div>
              <div className="form-group">
                <label>역할</label>
                <select defaultValue={selectedUser.role} id="edit-role">
                  <option value="user">사용자</option>
                  <option value="admin">관리자</option>
                </select>
              </div>
              <div className="modal-actions">
                <button
                  className="btn-cancel"
                  onClick={() => setShowEditModal(false)}
                >
                  취소
                </button>
                <button
                  className="btn-save"
                  onClick={() => {
                    const email = (document.getElementById('edit-email') as HTMLInputElement).value;
                    const role = (document.getElementById('edit-role') as HTMLSelectElement).value;
                    handleUpdateUser(selectedUser.id, { email, role });
                  }}
                >
                  저장
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AdminDashboard;
