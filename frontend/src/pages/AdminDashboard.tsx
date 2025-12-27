import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { API_BASE_URL } from '../config/constants';

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
        <style>{styles}</style>
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

      <style>{styles}</style>
    </div>
  );
};

const styles = `
  .admin-container {
    min-height: 100vh;
    position: relative;
    overflow-x: hidden;
  }

  .admin-bg {
    position: fixed;
    inset: 0;
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #0f0f23 100%);
    z-index: -1;
  }

  .gradient-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.4;
    animation: float 20s infinite ease-in-out;
  }

  .orb-1 {
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.4) 0%, transparent 70%);
    top: -100px;
    right: -50px;
  }

  .orb-2 {
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.3) 0%, transparent 70%);
    bottom: -100px;
    left: -50px;
    animation-delay: -7s;
  }

  .orb-3 {
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.3) 0%, transparent 70%);
    top: 40%;
    left: 30%;
    animation-delay: -14s;
  }

  @keyframes float {
    0%, 100% { transform: translate(0, 0) scale(1); }
    25% { transform: translate(20px, -20px) scale(1.02); }
    50% { transform: translate(-15px, 15px) scale(0.98); }
    75% { transform: translate(-20px, -15px) scale(1.01); }
  }

  .admin-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 40px;
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .header-left h1 {
    color: #fff;
    font-size: 24px;
    font-weight: 600;
    margin: 0;
  }

  .admin-badge {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .user-info {
    color: rgba(255, 255, 255, 0.7);
    font-size: 14px;
  }

  .btn-nav, .btn-logout {
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-nav {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: white;
  }

  .btn-nav:hover {
    background: rgba(255, 255, 255, 0.15);
  }

  .btn-logout {
    background: rgba(239, 68, 68, 0.2);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #fca5a5;
  }

  .btn-logout:hover {
    background: rgba(239, 68, 68, 0.3);
  }

  .admin-main {
    padding: 40px;
    max-width: 1400px;
    margin: 0 auto;
  }

  .stats-section {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
  }

  .stats-section.token-stats {
    margin-bottom: 32px;
  }

  .stat-card {
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 24px;
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .stat-card.token {
    border-color: rgba(99, 102, 241, 0.2);
    background: rgba(99, 102, 241, 0.05);
  }

  .stat-icon {
    font-size: 32px;
    width: 60px;
    height: 60px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(99, 102, 241, 0.1);
    border-radius: 12px;
  }

  .stat-content {
    display: flex;
    flex-direction: column;
  }

  .stat-value {
    font-size: 28px;
    font-weight: 700;
    color: #fff;
  }

  .stat-label {
    font-size: 14px;
    color: rgba(255, 255, 255, 0.5);
  }

  .tab-nav {
    display: flex;
    gap: 8px;
    margin-bottom: 24px;
    background: rgba(255, 255, 255, 0.03);
    padding: 6px;
    border-radius: 12px;
    width: fit-content;
  }

  .tab-btn {
    padding: 10px 20px;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.6);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .tab-btn.active {
    background: rgba(99, 102, 241, 0.2);
    color: #a5b4fc;
  }

  .tab-btn:hover:not(.active) {
    color: rgba(255, 255, 255, 0.8);
    background: rgba(255, 255, 255, 0.05);
  }

  .error-banner {
    background: rgba(239, 68, 68, 0.15);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #fca5a5;
    padding: 16px 20px;
    border-radius: 12px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .error-banner button {
    background: none;
    border: none;
    color: #fca5a5;
    font-size: 20px;
    cursor: pointer;
  }

  .users-section, .tokens-section {
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    padding: 24px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }

  .section-header h2 {
    color: #fff;
    font-size: 20px;
    font-weight: 600;
    margin: 0;
  }

  .search-box input {
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: #fff;
    font-size: 14px;
    width: 250px;
    transition: all 0.2s;
  }

  .search-box input::placeholder {
    color: rgba(255, 255, 255, 0.3);
  }

  .search-box input:focus {
    outline: none;
    border-color: rgba(99, 102, 241, 0.5);
    background: rgba(99, 102, 241, 0.05);
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px;
    color: rgba(255, 255, 255, 0.5);
    gap: 16px;
  }

  .loading-state.small {
    padding: 30px;
  }

  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid rgba(255, 255, 255, 0.1);
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .users-table, .token-table {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .table-header, .table-row {
    display: grid;
    grid-template-columns: 1fr 1.5fr 100px 80px 80px 120px;
    gap: 16px;
    padding: 12px 16px;
    align-items: center;
  }

  .token-table .table-header,
  .token-table .table-row {
    grid-template-columns: 1fr 100px 120px 120px 120px 120px;
  }

  .table-header {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 10px;
    color: rgba(255, 255, 255, 0.6);
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .table-row {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.05);
    color: #fff;
    font-size: 14px;
    transition: all 0.2s;
  }

  .user-name, .user-id {
    font-weight: 500;
  }

  .user-email {
    color: rgba(255, 255, 255, 0.7);
  }

  .mono {
    font-family: monospace;
    font-size: 12px;
  }

  .token-count {
    font-weight: 600;
    color: #a5b4fc;
  }

  .time-avg {
    color: #86efac;
  }

  .time-max {
    color: #fca5a5;
  }

  .time-min {
    color: #93c5fd;
  }

  .endpoint {
    color: rgba(255, 255, 255, 0.6);
  }

  .role-badge, .status-badge, .verify-badge {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 500;
    text-align: center;
  }

  .role-badge.admin {
    background: rgba(139, 92, 246, 0.2);
    color: #c4b5fd;
  }

  .role-badge.user {
    background: rgba(59, 130, 246, 0.2);
    color: #93c5fd;
  }

  .status-badge.active {
    background: rgba(34, 197, 94, 0.2);
    color: #86efac;
  }

  .status-badge.inactive {
    background: rgba(239, 68, 68, 0.2);
    color: #fca5a5;
  }

  .verify-badge.verified {
    background: rgba(34, 197, 94, 0.2);
    color: #86efac;
  }

  .verify-badge.unverified {
    background: rgba(251, 191, 36, 0.2);
    color: #fcd34d;
  }

  .actions {
    display: flex;
    gap: 8px;
  }

  .btn-action {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .btn-action.edit {
    background: rgba(59, 130, 246, 0.2);
  }

  .btn-action.toggle {
    background: rgba(251, 191, 36, 0.2);
  }

  .btn-action.delete {
    background: rgba(239, 68, 68, 0.2);
  }

  .btn-action:hover {
    transform: scale(1.1);
  }

  .btn-action:disabled {
    opacity: 0.3;
    cursor: not-allowed;
    transform: none;
  }

  .empty-state {
    text-align: center;
    padding: 40px;
    color: rgba(255, 255, 255, 0.4);
  }

  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 16px;
    margin-top: 20px;
    color: rgba(255, 255, 255, 0.7);
  }

  .pagination button {
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    color: white;
    cursor: pointer;
    transition: all 0.2s;
  }

  .pagination button:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.15);
  }

  .pagination button:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  /* Token Stats Styles */
  .token-panel {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;
  }

  .token-panel h3 {
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 20px;
  }

  .token-panel.slowest {
    border-color: rgba(239, 68, 68, 0.2);
    background: rgba(239, 68, 68, 0.05);
  }

  .daily-chart {
    display: flex;
    justify-content: space-around;
    align-items: flex-end;
    height: 200px;
    padding-top: 20px;
  }

  .chart-bar-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    flex: 1;
  }

  .chart-bar-wrapper {
    height: 150px;
    width: 40px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    display: flex;
    align-items: flex-end;
    overflow: hidden;
  }

  .chart-bar {
    width: 100%;
    background: linear-gradient(180deg, #6366f1, #8b5cf6);
    border-radius: 8px 8px 0 0;
    min-height: 4px;
  }

  .chart-value {
    font-size: 14px;
    font-weight: 600;
    color: #fff;
  }

  .chart-label {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.5);
  }

  .slowest-info {
    display: grid;
    gap: 12px;
  }

  .info-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.03);
    border-radius: 8px;
  }

  .info-label {
    color: rgba(255, 255, 255, 0.6);
    font-size: 14px;
  }

  .info-value {
    color: #fff;
    font-size: 14px;
  }

  .info-value.mono {
    font-family: monospace;
    font-size: 12px;
  }

  .info-value.highlight {
    color: #fca5a5;
    font-weight: 600;
  }

  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }

  .modal-content {
    background: rgba(30, 30, 50, 0.95);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 20px;
    padding: 32px;
    width: 100%;
    max-width: 400px;
  }

  .modal-content h3 {
    color: #fff;
    font-size: 20px;
    margin: 0 0 24px;
  }

  .form-group {
    margin-bottom: 16px;
  }

  .form-group label {
    display: block;
    color: rgba(255, 255, 255, 0.7);
    font-size: 13px;
    margin-bottom: 6px;
  }

  .form-group input,
  .form-group select {
    width: 100%;
    padding: 12px 16px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: #fff;
    font-size: 14px;
  }

  .form-group input:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .form-group select {
    cursor: pointer;
  }

  .form-group select option {
    background: #1a1a2e;
    color: #fff;
  }

  .modal-actions {
    display: flex;
    gap: 12px;
    margin-top: 24px;
  }

  .btn-cancel, .btn-save {
    flex: 1;
    padding: 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-cancel {
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: white;
  }

  .btn-save {
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border: none;
    color: white;
  }

  .btn-save:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(99, 102, 241, 0.4);
  }

  .access-denied {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    color: #fff;
  }

  .access-denied h1 {
    font-size: 32px;
    margin-bottom: 16px;
  }

  .access-denied p {
    color: rgba(255, 255, 255, 0.6);
    margin-bottom: 24px;
  }

  .access-denied button {
    padding: 12px 24px;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    border: none;
    border-radius: 10px;
    color: white;
    font-size: 14px;
    cursor: pointer;
  }
`;

export default AdminDashboard;
