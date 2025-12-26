import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { API_BASE_URL, APP_ENV } from '../config/constants';

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface SystemStatus {
  gpu: {
    name: string;
    memory_used: number;
    memory_total: number;
    utilization: number;
    temperature: number;
    status: 'online' | 'offline' | 'warning';
  };
  model: {
    name: string;
    version: string;
    status: 'loaded' | 'loading' | 'error';
    inference_time_ms: number;
  };
  index: {
    total_documents: number;
    total_chunks: number;
    last_updated: string;
    status: 'ready' | 'indexing' | 'error';
  };
  neo4j: {
    status: 'connected' | 'disconnected';
    node_count: number;
    relationship_count: number;
  };
}

interface KnowledgeSource {
  id: string;
  name: string;
  type: 'pdf' | 'docx' | 'web' | 'api' | 'database';
  document_count: number;
  last_sync: string;
  status: 'active' | 'syncing' | 'error';
}

interface Notification {
  id: string;
  type: 'info' | 'warning' | 'error' | 'success';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
}

interface QuickAction {
  id: string;
  icon: string;
  label: string;
  description: string;
  route: string;
  color: string;
}

// ─────────────────────────────────────────────────────────────
// Environment Configuration
// ─────────────────────────────────────────────────────────────

const ENV_LABELS: Record<string, { label: string; color: string }> = {
  development: { label: 'DEV', color: '#f59e0b' },
  staging: { label: 'STAGING', color: '#8b5cf6' },
  production: { label: 'PROD', color: '#10b981' },
};

// ─────────────────────────────────────────────────────────────
// Quick Actions Configuration
// ─────────────────────────────────────────────────────────────

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'knowledge',
    icon: '📚',
    label: '지식 검색',
    description: 'RAG 기반 문서 검색 및 질의응답',
    route: '/knowledge',
    color: '#3b82f6',
  },
  {
    id: 'mindmap',
    icon: '🧠',
    label: '마인드맵',
    description: '지식 시각화 및 관계 탐색',
    route: '/mindmap',
    color: '#8b5cf6',
  },
  {
    id: 'documents',
    icon: '📄',
    label: '문서 관리',
    description: '문서 업로드 및 인덱싱 관리',
    route: '/documents',
    color: '#10b981',
  },
  {
    id: 'analytics',
    icon: '📊',
    label: '분석 대시보드',
    description: '사용량 통계 및 성능 모니터링',
    route: '/analytics',
    color: '#f59e0b',
  },
];

// ─────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────

const MainDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();

  // State
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [knowledgeSources, setKnowledgeSources] = useState<KnowledgeSource[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showNotifications, setShowNotifications] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // ─────────────────────────────────────────────────────────────
  // Data Fetching
  // ─────────────────────────────────────────────────────────────

  const fetchSystemStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/system/status`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setSystemStatus(data.data);
      }
    } catch {
      // Use mock data if API not available
      setSystemStatus({
        gpu: {
          name: 'NVIDIA A100-SXM4-40GB',
          memory_used: 24.5,
          memory_total: 40,
          utilization: 45,
          temperature: 62,
          status: 'online',
        },
        model: {
          name: 'Nemotron-Mini-4B',
          version: '1.0.0',
          status: 'loaded',
          inference_time_ms: 125,
        },
        index: {
          total_documents: 1247,
          total_chunks: 45892,
          last_updated: new Date().toISOString(),
          status: 'ready',
        },
        neo4j: {
          status: 'connected',
          node_count: 8534,
          relationship_count: 24891,
        },
      });
    }
  }, []);

  const fetchKnowledgeSources = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/system/knowledge/sources`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        // Handle both data.data.sources and data.data array formats
        const sources = data.data?.sources || data.data;
        if (Array.isArray(sources)) {
          setKnowledgeSources(sources);
        }
      }
    } catch {
      // Use mock data
      setKnowledgeSources([
        { id: '1', name: '기술 문서', type: 'pdf', document_count: 342, last_sync: '2시간 전', status: 'active' },
        { id: '2', name: '정책 가이드', type: 'docx', document_count: 128, last_sync: '1일 전', status: 'active' },
        { id: '3', name: 'API 문서', type: 'web', document_count: 89, last_sync: '30분 전', status: 'syncing' },
        { id: '4', name: '내부 위키', type: 'database', document_count: 567, last_sync: '5분 전', status: 'active' },
      ]);
    }
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/notifications`, {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        // Ensure data.data is an array before setting
        if (Array.isArray(data.data)) {
          setNotifications(data.data);
        }
      }
    } catch {
      // Use mock data
      setNotifications([
        {
          id: '1',
          type: 'success',
          title: '인덱싱 완료',
          message: '새로운 문서 15개가 성공적으로 인덱싱되었습니다.',
          timestamp: '5분 전',
          read: false,
        },
        {
          id: '2',
          type: 'info',
          title: '시스템 업데이트',
          message: '모델 버전 1.0.1이 적용되었습니다.',
          timestamp: '1시간 전',
          read: false,
        },
        {
          id: '3',
          type: 'warning',
          title: 'GPU 메모리 경고',
          message: 'GPU 메모리 사용량이 80%를 초과했습니다.',
          timestamp: '3시간 전',
          read: true,
        },
      ]);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      await Promise.all([
        fetchSystemStatus(),
        fetchKnowledgeSources(),
        fetchNotifications(),
      ]);
      setIsLoading(false);
    };
    loadData();

    // Refresh system status every 30 seconds
    const interval = setInterval(fetchSystemStatus, 30000);
    return () => clearInterval(interval);
  }, [fetchSystemStatus, fetchKnowledgeSources, fetchNotifications]);

  // ─────────────────────────────────────────────────────────────
  // Helpers
  // ─────────────────────────────────────────────────────────────

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online':
      case 'loaded':
      case 'ready':
      case 'connected':
      case 'active':
        return '#10b981';
      case 'loading':
      case 'indexing':
      case 'syncing':
        return '#f59e0b';
      case 'offline':
      case 'error':
      case 'disconnected':
        return '#ef4444';
      default:
        return '#64748b';
    }
  };

  const getSourceIcon = (type: string) => {
    switch (type) {
      case 'pdf': return '📕';
      case 'docx': return '📘';
      case 'web': return '🌐';
      case 'api': return '🔌';
      case 'database': return '🗄️';
      default: return '📄';
    }
  };

  const getNotificationIcon = (type: string) => {
    switch (type) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      case 'info': return 'ℹ️';
      default: return '📢';
    }
  };

  const unreadCount = notifications.filter(n => !n.read).length;
  const envConfig = ENV_LABELS[APP_ENV] || ENV_LABELS.development;

  // ─────────────────────────────────────────────────────────────
  // Render
  // ─────────────────────────────────────────────────────────────

  return (
    <div className="dashboard-container">
      {/* Background */}
      <div className="dashboard-bg">
        <div className="gradient-orb orb-1" />
        <div className="gradient-orb orb-2" />
        <div className="gradient-orb orb-3" />
      </div>

      {/* Header */}
      <header className="dashboard-header">
        <div className="header-left">
          <button
            className="mobile-menu-btn"
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            aria-label="메뉴 열기"
          >
            ☰
          </button>
          <div className="logo-section">
            <span className="logo-icon">🧠</span>
            <div className="logo-text">
              <h1>KMS RAG Platform</h1>
              <span className="logo-subtitle">GPU-Accelerated Knowledge Management</span>
            </div>
          </div>
          <span className="env-badge" style={{ background: envConfig.color }}>
            {envConfig.label}
          </span>
        </div>

        <div className="header-right">
          {/* Notification Bell */}
          <div className="notification-wrapper">
            <button
              className="notification-btn"
              onClick={() => setShowNotifications(!showNotifications)}
              aria-label="알림"
            >
              🔔
              {unreadCount > 0 && (
                <span className="notification-badge">{unreadCount}</span>
              )}
            </button>

            <AnimatePresence>
              {showNotifications && (
                <motion.div
                  className="notification-dropdown"
                  initial={{ opacity: 0, y: -10, scale: 0.95 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -10, scale: 0.95 }}
                >
                  <div className="notification-header">
                    <h4>알림</h4>
                    <button onClick={() => setNotifications(notifications.map(n => ({ ...n, read: true })))}>
                      모두 읽음
                    </button>
                  </div>
                  <div className="notification-list">
                    {notifications.length === 0 ? (
                      <div className="notification-empty">알림이 없습니다</div>
                    ) : (
                      notifications.map((notif) => (
                        <div
                          key={notif.id}
                          className={`notification-item ${notif.read ? 'read' : 'unread'}`}
                        >
                          <span className="notification-icon">{getNotificationIcon(notif.type)}</span>
                          <div className="notification-content">
                            <strong>{notif.title}</strong>
                            <p>{notif.message}</p>
                            <span className="notification-time">{notif.timestamp}</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* User Menu */}
          <div className="user-section">
            <div className="user-avatar">
              {user?.name?.charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div className="user-info">
              <span className="user-name">{user?.name || user?.email || 'User'}</span>
              <span className="user-role">{user?.role === 'admin' ? 'Admin' : 'User'}</span>
            </div>
          </div>

          {/* Navigation */}
          <nav className="header-nav">
            {user?.role === 'admin' && (
              <button className="nav-btn" onClick={() => navigate('/admin')}>
                ⚙️ 관리
              </button>
            )}
            <button className="nav-btn logout" onClick={logout}>
              로그아웃
            </button>
          </nav>
        </div>
      </header>

      {/* Mobile Menu */}
      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.nav
            className="mobile-nav"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
          >
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.id}
                className="mobile-nav-item"
                onClick={() => {
                  navigate(action.route);
                  setIsMobileMenuOpen(false);
                }}
              >
                <span>{action.icon}</span>
                <span>{action.label}</span>
              </button>
            ))}
            {user?.role === 'admin' && (
              <button className="mobile-nav-item" onClick={() => navigate('/admin')}>
                <span>⚙️</span>
                <span>관리자 대시보드</span>
              </button>
            )}
          </motion.nav>
        )}
      </AnimatePresence>

      {/* Main Content */}
      <main className="dashboard-main">
        {isLoading ? (
          <div className="loading-state">
            <div className="spinner" />
            <span>데이터를 불러오는 중...</span>
          </div>
        ) : (
          <>
            {/* Welcome Section */}
            <motion.section
              className="welcome-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              <h2>안녕하세요, {user?.name || 'User'}님 👋</h2>
              <p>오늘도 효율적인 지식 관리를 시작하세요.</p>
            </motion.section>

            {/* System Status Cards */}
            {systemStatus && (
              <motion.section
                className="status-section"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 }}
              >
                <h3 className="section-title">🖥️ 시스템 상태</h3>
                <div className="status-grid">
                  {/* GPU Status */}
                  <div className="status-card gpu">
                    <div className="status-header">
                      <span className="status-icon">🎮</span>
                      <span
                        className="status-indicator"
                        style={{ background: getStatusColor(systemStatus.gpu.status) }}
                      />
                    </div>
                    <h4>GPU</h4>
                    <p className="status-name">{systemStatus.gpu.name}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">메모리</span>
                        <div className="metric-bar-container">
                          <div
                            className="metric-bar"
                            style={{
                              width: `${(systemStatus.gpu.memory_used / systemStatus.gpu.memory_total) * 100}%`,
                              background: systemStatus.gpu.memory_used / systemStatus.gpu.memory_total > 0.8 ? '#ef4444' : '#3b82f6',
                            }}
                          />
                        </div>
                        <span className="metric-value">
                          {systemStatus.gpu.memory_used.toFixed(1)} / {systemStatus.gpu.memory_total}GB
                        </span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">사용률</span>
                        <span className="metric-value large">{systemStatus.gpu.utilization}%</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">온도</span>
                        <span className="metric-value">{systemStatus.gpu.temperature}°C</span>
                      </div>
                    </div>
                  </div>

                  {/* Model Status */}
                  <div className="status-card model">
                    <div className="status-header">
                      <span className="status-icon">🤖</span>
                      <span
                        className="status-indicator"
                        style={{ background: getStatusColor(systemStatus.model.status) }}
                      />
                    </div>
                    <h4>AI 모델</h4>
                    <p className="status-name">{systemStatus.model.name}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">버전</span>
                        <span className="metric-value">{systemStatus.model.version}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">상태</span>
                        <span className="metric-value status-text" style={{ color: getStatusColor(systemStatus.model.status) }}>
                          {systemStatus.model.status === 'loaded' ? '정상' : systemStatus.model.status}
                        </span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">추론 시간</span>
                        <span className="metric-value large">{systemStatus.model.inference_time_ms}ms</span>
                      </div>
                    </div>
                  </div>

                  {/* Index Status */}
                  <div className="status-card index">
                    <div className="status-header">
                      <span className="status-icon">📑</span>
                      <span
                        className="status-indicator"
                        style={{ background: getStatusColor(systemStatus.index.status) }}
                      />
                    </div>
                    <h4>벡터 인덱스</h4>
                    <p className="status-name">{systemStatus.index.status === 'ready' ? '준비됨' : systemStatus.index.status}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">문서</span>
                        <span className="metric-value large">{systemStatus.index.total_documents.toLocaleString()}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">청크</span>
                        <span className="metric-value">{systemStatus.index.total_chunks.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>

                  {/* Neo4j Status */}
                  <div className="status-card neo4j">
                    <div className="status-header">
                      <span className="status-icon">🕸️</span>
                      <span
                        className="status-indicator"
                        style={{ background: getStatusColor(systemStatus.neo4j.status) }}
                      />
                    </div>
                    <h4>그래프 DB</h4>
                    <p className="status-name">Neo4j {systemStatus.neo4j.status === 'connected' ? '연결됨' : '연결 끊김'}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">노드</span>
                        <span className="metric-value large">{systemStatus.neo4j.node_count.toLocaleString()}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">관계</span>
                        <span className="metric-value">{systemStatus.neo4j.relationship_count.toLocaleString()}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </motion.section>
            )}

            {/* Quick Actions */}
            <motion.section
              className="actions-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 }}
            >
              <h3 className="section-title">⚡ 빠른 실행</h3>
              <div className="actions-grid">
                {QUICK_ACTIONS.map((action, index) => (
                  <motion.button
                    key={action.id}
                    className="action-card"
                    onClick={() => navigate(action.route)}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: 0.3 + index * 0.1 }}
                    whileHover={{ scale: 1.02, y: -4 }}
                    whileTap={{ scale: 0.98 }}
                    style={{ '--action-color': action.color } as React.CSSProperties}
                  >
                    <span className="action-icon">{action.icon}</span>
                    <div className="action-content">
                      <h4>{action.label}</h4>
                      <p>{action.description}</p>
                    </div>
                    <span className="action-arrow">→</span>
                  </motion.button>
                ))}
              </div>
            </motion.section>

            {/* Knowledge Sources */}
            <motion.section
              className="sources-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.3 }}
            >
              <div className="section-header">
                <h3 className="section-title">📚 지식 소스</h3>
                <button className="btn-secondary" onClick={() => navigate('/documents')}>
                  모두 보기
                </button>
              </div>
              <div className="sources-grid">
                {knowledgeSources.map((source) => (
                  <div key={source.id} className="source-card">
                    <div className="source-icon">{getSourceIcon(source.type)}</div>
                    <div className="source-info">
                      <h4>{source.name}</h4>
                      <p>{source.document_count.toLocaleString()} 문서</p>
                    </div>
                    <div className="source-status">
                      <span
                        className="status-dot"
                        style={{ background: getStatusColor(source.status) }}
                      />
                      <span className="sync-time">{source.last_sync}</span>
                    </div>
                  </div>
                ))}
              </div>
            </motion.section>

            {/* Recent Activity / Stats */}
            <motion.section
              className="activity-section"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.4 }}
            >
              <h3 className="section-title">📈 최근 활동</h3>
              <div className="activity-grid">
                <div className="activity-card">
                  <span className="activity-icon">🔍</span>
                  <div className="activity-content">
                    <span className="activity-value">247</span>
                    <span className="activity-label">오늘 검색</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">📄</span>
                  <div className="activity-content">
                    <span className="activity-value">15</span>
                    <span className="activity-label">신규 문서</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">💬</span>
                  <div className="activity-content">
                    <span className="activity-value">89</span>
                    <span className="activity-label">AI 응답</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">⏱️</span>
                  <div className="activity-content">
                    <span className="activity-value">1.2s</span>
                    <span className="activity-label">평균 응답</span>
                  </div>
                </div>
              </div>
            </motion.section>
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="dashboard-footer">
        <p>KMS RAG Platform v1.0 | Powered by Nemotron & Neo4j | © 2024</p>
      </footer>

      <style>{styles}</style>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────

const styles = `
  /* Container & Background */
  .dashboard-container {
    min-height: 100vh;
    position: relative;
    overflow-x: hidden;
    display: flex;
    flex-direction: column;
  }

  .dashboard-bg {
    position: fixed;
    inset: 0;
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #0f0f23 100%);
    z-index: -1;
  }

  .gradient-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(100px);
    opacity: 0.3;
    animation: float 25s infinite ease-in-out;
  }

  .orb-1 {
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(59, 130, 246, 0.4) 0%, transparent 70%);
    top: -150px;
    right: -100px;
  }

  .orb-2 {
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(139, 92, 246, 0.3) 0%, transparent 70%);
    bottom: -150px;
    left: -100px;
    animation-delay: -10s;
  }

  .orb-3 {
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.25) 0%, transparent 70%);
    top: 50%;
    left: 40%;
    animation-delay: -18s;
  }

  @keyframes float {
    0%, 100% { transform: translate(0, 0) scale(1); }
    25% { transform: translate(30px, -30px) scale(1.05); }
    50% { transform: translate(-20px, 20px) scale(0.95); }
    75% { transform: translate(-30px, -20px) scale(1.02); }
  }

  /* Header */
  .dashboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    position: sticky;
    top: 0;
    z-index: 50;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .mobile-menu-btn {
    display: none;
    background: none;
    border: none;
    color: #fff;
    font-size: 24px;
    cursor: pointer;
    padding: 8px;
  }

  .logo-section {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo-icon {
    font-size: 32px;
  }

  .logo-text h1 {
    color: #fff;
    font-size: 20px;
    font-weight: 700;
    margin: 0;
    line-height: 1.2;
  }

  .logo-subtitle {
    color: rgba(255, 255, 255, 0.5);
    font-size: 12px;
  }

  .env-badge {
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.5px;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  /* Notifications */
  .notification-wrapper {
    position: relative;
  }

  .notification-btn {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 10px;
    font-size: 18px;
    cursor: pointer;
    position: relative;
    transition: all 0.2s;
  }

  .notification-btn:hover {
    background: rgba(255, 255, 255, 0.12);
  }

  .notification-badge {
    position: absolute;
    top: -4px;
    right: -4px;
    background: #ef4444;
    color: #fff;
    font-size: 11px;
    font-weight: 600;
    min-width: 18px;
    height: 18px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .notification-dropdown {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    width: 360px;
    max-height: 400px;
    background: rgba(30, 30, 50, 0.98);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
  }

  .notification-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }

  .notification-header h4 {
    color: #fff;
    font-size: 16px;
    margin: 0;
  }

  .notification-header button {
    background: none;
    border: none;
    color: #3b82f6;
    font-size: 13px;
    cursor: pointer;
  }

  .notification-list {
    max-height: 320px;
    overflow-y: auto;
  }

  .notification-item {
    display: flex;
    gap: 12px;
    padding: 14px 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    transition: background 0.2s;
  }

  .notification-item:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .notification-item.unread {
    background: rgba(59, 130, 246, 0.08);
  }

  .notification-icon {
    font-size: 20px;
    flex-shrink: 0;
  }

  .notification-content {
    flex: 1;
    min-width: 0;
  }

  .notification-content strong {
    display: block;
    color: #fff;
    font-size: 14px;
    margin-bottom: 4px;
  }

  .notification-content p {
    color: rgba(255, 255, 255, 0.6);
    font-size: 13px;
    margin: 0 0 6px;
    line-height: 1.4;
  }

  .notification-time {
    color: rgba(255, 255, 255, 0.4);
    font-size: 12px;
  }

  .notification-empty {
    padding: 40px;
    text-align: center;
    color: rgba(255, 255, 255, 0.4);
  }

  /* User Section */
  .user-section {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 12px;
  }

  .user-avatar {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 600;
    font-size: 16px;
  }

  .user-info {
    display: flex;
    flex-direction: column;
  }

  .user-name {
    color: #fff;
    font-size: 14px;
    font-weight: 500;
  }

  .user-role {
    color: rgba(255, 255, 255, 0.5);
    font-size: 12px;
    text-transform: capitalize;
  }

  /* Header Navigation */
  .header-nav {
    display: flex;
    gap: 8px;
  }

  .nav-btn {
    padding: 10px 16px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    color: #fff;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .nav-btn:hover {
    background: rgba(255, 255, 255, 0.12);
  }

  .nav-btn.logout {
    background: rgba(239, 68, 68, 0.15);
    border-color: rgba(239, 68, 68, 0.2);
    color: #fca5a5;
  }

  .nav-btn.logout:hover {
    background: rgba(239, 68, 68, 0.25);
  }

  /* Mobile Navigation */
  .mobile-nav {
    display: none;
    background: rgba(30, 30, 50, 0.98);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    padding: 12px;
    overflow: hidden;
  }

  .mobile-nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 14px 16px;
    background: rgba(255, 255, 255, 0.03);
    border: none;
    border-radius: 12px;
    color: #fff;
    font-size: 15px;
    cursor: pointer;
    margin-bottom: 8px;
  }

  .mobile-nav-item:last-child {
    margin-bottom: 0;
  }

  /* Main Content */
  .dashboard-main {
    flex: 1;
    padding: 32px 24px;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
  }

  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 80px;
    color: rgba(255, 255, 255, 0.5);
    gap: 20px;
  }

  .spinner {
    width: 48px;
    height: 48px;
    border: 4px solid rgba(255, 255, 255, 0.1);
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Welcome Section */
  .welcome-section {
    margin-bottom: 32px;
  }

  .welcome-section h2 {
    color: #fff;
    font-size: 28px;
    font-weight: 700;
    margin: 0 0 8px;
  }

  .welcome-section p {
    color: rgba(255, 255, 255, 0.6);
    font-size: 16px;
    margin: 0;
  }

  /* Section Titles */
  .section-title {
    color: #fff;
    font-size: 18px;
    font-weight: 600;
    margin: 0 0 20px;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
  }

  .section-header .section-title {
    margin: 0;
  }

  .btn-secondary {
    padding: 8px 16px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    color: #fff;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-secondary:hover {
    background: rgba(255, 255, 255, 0.12);
  }

  /* Status Section */
  .status-section {
    margin-bottom: 40px;
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 20px;
  }

  .status-card {
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 20px;
    padding: 24px;
    transition: all 0.3s;
  }

  .status-card:hover {
    background: rgba(255, 255, 255, 0.05);
    transform: translateY(-2px);
  }

  .status-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .status-icon {
    font-size: 28px;
  }

  .status-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    animation: pulse-status 2s infinite;
  }

  @keyframes pulse-status {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  .status-card h4 {
    color: rgba(255, 255, 255, 0.7);
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 4px;
  }

  .status-name {
    color: #fff;
    font-size: 14px;
    margin: 0 0 20px;
    opacity: 0.9;
  }

  .status-metrics {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .metric {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .metric-label {
    color: rgba(255, 255, 255, 0.5);
    font-size: 12px;
  }

  .metric-value {
    color: #fff;
    font-size: 14px;
    font-weight: 500;
  }

  .metric-value.large {
    font-size: 20px;
    font-weight: 700;
    color: #3b82f6;
  }

  .metric-value.status-text {
    font-weight: 600;
  }

  .metric-bar-container {
    flex: 1;
    min-width: 60px;
    height: 6px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    overflow: hidden;
  }

  .metric-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s;
  }

  /* Quick Actions */
  .actions-section {
    margin-bottom: 40px;
  }

  .actions-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }

  .action-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 24px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    cursor: pointer;
    transition: all 0.3s;
    text-align: left;
    position: relative;
    overflow: hidden;
  }

  .action-card::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: var(--action-color);
    opacity: 0;
    transition: opacity 0.3s;
  }

  .action-card:hover::before {
    opacity: 1;
  }

  .action-card:hover {
    background: rgba(255, 255, 255, 0.06);
    border-color: var(--action-color);
  }

  .action-icon {
    font-size: 36px;
    flex-shrink: 0;
  }

  .action-content {
    flex: 1;
  }

  .action-content h4 {
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 4px;
  }

  .action-content p {
    color: rgba(255, 255, 255, 0.5);
    font-size: 13px;
    margin: 0;
  }

  .action-arrow {
    color: rgba(255, 255, 255, 0.3);
    font-size: 20px;
    transition: all 0.3s;
  }

  .action-card:hover .action-arrow {
    color: var(--action-color);
    transform: translateX(4px);
  }

  /* Knowledge Sources */
  .sources-section {
    margin-bottom: 40px;
  }

  .sources-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }

  .source-card {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 18px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    transition: all 0.2s;
  }

  .source-card:hover {
    background: rgba(255, 255, 255, 0.05);
  }

  .source-icon {
    font-size: 28px;
    flex-shrink: 0;
  }

  .source-info {
    flex: 1;
    min-width: 0;
  }

  .source-info h4 {
    color: #fff;
    font-size: 14px;
    font-weight: 500;
    margin: 0 0 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .source-info p {
    color: rgba(255, 255, 255, 0.5);
    font-size: 12px;
    margin: 0;
  }

  .source-status {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }

  .sync-time {
    color: rgba(255, 255, 255, 0.4);
    font-size: 11px;
    white-space: nowrap;
  }

  /* Activity Section */
  .activity-section {
    margin-bottom: 40px;
  }

  .activity-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
  }

  .activity-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 24px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
  }

  .activity-icon {
    font-size: 32px;
  }

  .activity-content {
    display: flex;
    flex-direction: column;
  }

  .activity-value {
    color: #fff;
    font-size: 28px;
    font-weight: 700;
    line-height: 1;
  }

  .activity-label {
    color: rgba(255, 255, 255, 0.5);
    font-size: 13px;
    margin-top: 4px;
  }

  /* Footer */
  .dashboard-footer {
    padding: 20px;
    text-align: center;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    background: rgba(0, 0, 0, 0.2);
  }

  .dashboard-footer p {
    color: rgba(255, 255, 255, 0.4);
    font-size: 12px;
    margin: 0;
  }

  /* ─────────────────────────────────────────────────────────────
     Responsive Styles
     ───────────────────────────────────────────────────────────── */

  /* Tablet */
  @media (max-width: 1024px) {
    .status-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .sources-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .activity-grid {
      grid-template-columns: repeat(2, 1fr);
    }

    .logo-subtitle {
      display: none;
    }

    .user-info {
      display: none;
    }
  }

  /* Mobile */
  @media (max-width: 768px) {
    .mobile-menu-btn {
      display: block;
    }

    .mobile-nav {
      display: block;
    }

    .logo-text h1 {
      font-size: 16px;
    }

    .env-badge {
      font-size: 10px;
      padding: 3px 8px;
    }

    .header-nav {
      display: none;
    }

    .user-section {
      padding: 6px;
    }

    .user-avatar {
      width: 32px;
      height: 32px;
      font-size: 14px;
    }

    .notification-dropdown {
      position: fixed;
      top: 70px;
      left: 12px;
      right: 12px;
      width: auto;
    }

    .dashboard-main {
      padding: 20px 16px;
    }

    .welcome-section h2 {
      font-size: 22px;
    }

    .status-grid,
    .sources-grid,
    .activity-grid {
      grid-template-columns: 1fr;
    }

    .actions-grid {
      grid-template-columns: 1fr;
    }

    .action-card {
      padding: 18px;
    }

    .action-icon {
      font-size: 28px;
    }

    .status-card {
      padding: 18px;
    }

    .metric-value.large {
      font-size: 18px;
    }
  }

  /* Small Mobile */
  @media (max-width: 480px) {
    .dashboard-header {
      padding: 12px 16px;
    }

    .logo-section {
      gap: 8px;
    }

    .logo-icon {
      font-size: 24px;
    }

    .logo-text h1 {
      font-size: 14px;
    }

    .header-right {
      gap: 8px;
    }

    .notification-btn {
      padding: 8px;
      font-size: 16px;
    }

    .welcome-section h2 {
      font-size: 18px;
    }

    .welcome-section p {
      font-size: 14px;
    }

    .section-title {
      font-size: 16px;
    }
  }
`;

export default MainDashboard;
