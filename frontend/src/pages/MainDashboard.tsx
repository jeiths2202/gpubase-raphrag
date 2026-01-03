import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { API_BASE_URL, APP_ENV } from '../config/constants';
import ThemeToggle from '../components/ThemeToggle';
import LanguageSelector from '../components/LanguageSelector';
import { useTranslation } from '../hooks/useTranslation';
import './MainDashboard.css';

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

// ─────────────────────────────────────────────────────────────
// Environment Configuration
// ─────────────────────────────────────────────────────────────

const ENV_LABELS: Record<string, { label: string; color: string }> = {
  development: { label: 'DEV', color: '#f59e0b' },
  staging: { label: 'STAGING', color: '#8b5cf6' },
  production: { label: 'PROD', color: '#10b981' },
};

// ─────────────────────────────────────────────────────────────
// Quick Actions Configuration (using translation keys)
// ─────────────────────────────────────────────────────────────

const QUICK_ACTIONS_CONFIG = [
  { id: 'knowledge', icon: '📚', route: '/knowledge', color: '#818cf8' },
  { id: 'mindmap', icon: '🧠', route: '/mindmap', color: '#8b5cf6' },
  { id: 'documents', icon: '📄', route: '/documents', color: '#10b981' },
  { id: 'analytics', icon: '📊', route: '/analytics', color: '#f59e0b' },
];

// ─────────────────────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────────────────────

const MainDashboard: React.FC = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { t } = useTranslation();

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
      // Use mock data - names will be translated in render
      setKnowledgeSources([
        { id: '1', name: 'technicalDocs', type: 'pdf', document_count: 342, last_sync: '2h', status: 'active' },
        { id: '2', name: 'policyGuide', type: 'docx', document_count: 128, last_sync: '1d', status: 'active' },
        { id: '3', name: 'apiDocs', type: 'web', document_count: 89, last_sync: '30m', status: 'syncing' },
        { id: '4', name: 'internalWiki', type: 'database', document_count: 567, last_sync: '5m', status: 'active' },
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

  // Helper to translate source names
  const getSourceName = (nameKey: string) => {
    const key = `dashboard.sources.${nameKey}` as keyof import('../i18n/types').TranslationKeys;
    const translated = t(key);
    return translated !== key ? translated : nameKey;
  };

  // Helper to translate time ago
  const getTimeAgo = (timeCode: string) => {
    const match = timeCode.match(/^(\d+)(m|h|d)$/);
    if (!match) return timeCode;
    const [, count, unit] = match;
    switch (unit) {
      case 'm': return t('dashboard.timeAgo.minutesAgo', { count });
      case 'h': return t('dashboard.timeAgo.hoursAgo', { count });
      case 'd': return t('dashboard.timeAgo.daysAgo', { count });
      default: return timeCode;
    }
  };

  // Generate translated quick actions
  const quickActions = QUICK_ACTIONS_CONFIG.map(action => ({
    ...action,
    label: t(`dashboard.actions.${action.id}.label` as keyof import('../i18n/types').TranslationKeys),
    description: t(`dashboard.actions.${action.id}.description` as keyof import('../i18n/types').TranslationKeys),
  }));

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
            aria-label={t('dashboard.aria.openMenu')}
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
          {/* Language Selector */}
          <LanguageSelector size="sm" />

          {/* Theme Toggle */}
          <ThemeToggle size="sm" />

          {/* Notification Bell */}
          <div className="notification-wrapper">
            <button
              className="notification-btn"
              onClick={() => setShowNotifications(!showNotifications)}
              aria-label={t('dashboard.aria.notifications')}
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
                    <h4>{t('dashboard.notifications.title')}</h4>
                    <button onClick={() => setNotifications(notifications.map(n => ({ ...n, read: true })))}>
                      {t('dashboard.notifications.markAllRead')}
                    </button>
                  </div>
                  <div className="notification-list">
                    {notifications.length === 0 ? (
                      <div className="notification-empty">{t('dashboard.notifications.empty')}</div>
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
                ⚙️ {t('admin.menu')}
              </button>
            )}
            <button className="nav-btn logout" onClick={logout}>
              {t('common.nav.logout')}
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
            {quickActions.map((action) => (
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
                <span>{t('admin.title')}</span>
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
            <span>{t('common.loading')}</span>
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
              <h2>{t('dashboard.welcome', { name: user?.name || 'User' })} 👋</h2>
              <p>{t('dashboard.welcomeMessage')}</p>
            </motion.section>

            {/* System Status Cards */}
            {systemStatus && (
              <motion.section
                className="status-section"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.1 }}
              >
                <h3 className="section-title">🖥️ {t('dashboard.systemStatus')}</h3>
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
                        <span className="metric-label">{t('dashboard.memory')}</span>
                        <div className="metric-bar-container">
                          <div
                            className="metric-bar"
                            style={{
                              width: `${(systemStatus.gpu.memory_used / systemStatus.gpu.memory_total) * 100}%`,
                              background: systemStatus.gpu.memory_used / systemStatus.gpu.memory_total > 0.8 ? '#ef4444' : '#818cf8',
                            }}
                          />
                        </div>
                        <span className="metric-value">
                          {systemStatus.gpu.memory_used.toFixed(1)} / {systemStatus.gpu.memory_total}GB
                        </span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.utilization')}</span>
                        <span className="metric-value large">{systemStatus.gpu.utilization}%</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.temperature')}</span>
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
                    <h4>{t('dashboard.model')}</h4>
                    <p className="status-name">{systemStatus.model.name}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.version')}</span>
                        <span className="metric-value">{systemStatus.model.version}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.status')}</span>
                        <span className="metric-value status-text" style={{ color: getStatusColor(systemStatus.model.status) }}>
                          {systemStatus.model.status === 'loaded' ? t('dashboard.statusValues.normal') : systemStatus.model.status}
                        </span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.inferenceTime')}</span>
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
                    <h4>{t('dashboard.vectorIndex')}</h4>
                    <p className="status-name">{systemStatus.index.status === 'ready' ? t('dashboard.statusValues.ready') : systemStatus.index.status}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.documents')}</span>
                        <span className="metric-value large">{systemStatus.index.total_documents.toLocaleString()}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.chunks')}</span>
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
                    <h4>{t('dashboard.graphDb')}</h4>
                    <p className="status-name">Neo4j {systemStatus.neo4j.status === 'connected' ? t('dashboard.statusValues.connected') : t('dashboard.statusValues.disconnected')}</p>
                    <div className="status-metrics">
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.nodes')}</span>
                        <span className="metric-value large">{systemStatus.neo4j.node_count.toLocaleString()}</span>
                      </div>
                      <div className="metric">
                        <span className="metric-label">{t('dashboard.relationships')}</span>
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
              <h3 className="section-title">⚡ {t('dashboard.quickActions')}</h3>
              <div className="actions-grid">
                {quickActions.map((action, index) => (
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
                <h3 className="section-title">📚 {t('dashboard.knowledgeSources')}</h3>
                <button className="btn-secondary" onClick={() => navigate('/documents')}>
                  {t('common.viewAll')}
                </button>
              </div>
              <div className="sources-grid">
                {knowledgeSources.map((source) => (
                  <div key={source.id} className="source-card">
                    <div className="source-icon">{getSourceIcon(source.type)}</div>
                    <div className="source-info">
                      <h4>{getSourceName(source.name)}</h4>
                      <p>{t('dashboard.sources.documentCount', { count: source.document_count.toLocaleString() })}</p>
                    </div>
                    <div className="source-status">
                      <span
                        className="status-dot"
                        style={{ background: getStatusColor(source.status) }}
                      />
                      <span className="sync-time">{getTimeAgo(source.last_sync)}</span>
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
              <h3 className="section-title">📈 {t('dashboard.recentActivity')}</h3>
              <div className="activity-grid">
                <div className="activity-card">
                  <span className="activity-icon">🔍</span>
                  <div className="activity-content">
                    <span className="activity-value">247</span>
                    <span className="activity-label">{t('dashboard.todaySearches')}</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">📄</span>
                  <div className="activity-content">
                    <span className="activity-value">15</span>
                    <span className="activity-label">{t('dashboard.newDocuments')}</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">💬</span>
                  <div className="activity-content">
                    <span className="activity-value">89</span>
                    <span className="activity-label">{t('dashboard.aiResponses')}</span>
                  </div>
                </div>
                <div className="activity-card">
                  <span className="activity-icon">⏱️</span>
                  <div className="activity-content">
                    <span className="activity-value">1.2s</span>
                    <span className="activity-label">{t('dashboard.avgResponse')}</span>
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
    </div>
  );
};

export default MainDashboard;
