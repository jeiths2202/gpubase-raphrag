// KnowledgeSidebar Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors, TabType, Project, Notification, ThemeType } from '../types';
import { TranslateFunction } from '../../../i18n/types';

interface User {
  id: string;
  email: string;
  name: string;
  username?: string;
  avatar?: string;
  role: string;
  provider: 'email' | 'google' | 'sso';
}

interface KnowledgeSidebarProps {
  // State
  sidebarCollapsed: boolean;
  showNotifications: boolean;
  notifications: Notification[];
  unreadCount: number;
  activeTab: TabType;
  projects: Project[];
  selectedProject: Project | null;
  theme: ThemeType;
  user: User | null;

  // State setters
  setSidebarCollapsed: (collapsed: boolean) => void;
  setShowNotifications: (show: boolean) => void;
  setActiveTab: (tab: TabType) => void;
  setSelectedProject: (project: Project | null) => void;
  setShowSettingsPopup: (show: boolean) => void;

  // Functions
  markAllNotificationsAsRead: () => void;
  markNotificationAsRead: (ids: string[]) => void;
  toggleTheme: () => void;
  logout: () => void;
  navigate: (path: string) => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;
  tabStyle: (isActive: boolean) => React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const KnowledgeSidebar: React.FC<KnowledgeSidebarProps> = ({
  sidebarCollapsed,
  showNotifications,
  notifications,
  unreadCount,
  activeTab,
  projects,
  selectedProject,
  theme,
  user,
  setSidebarCollapsed,
  setShowNotifications,
  setActiveTab,
  setSelectedProject,
  setShowSettingsPopup,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  toggleTheme,
  logout,
  navigate,
  themeColors,
  cardStyle,
  tabStyle,
  t
}) => {
  return (
    <motion.aside
      initial={{ width: 280 }}
      animate={{ width: sidebarCollapsed ? 60 : 280 }}
      style={{
        ...cardStyle,
        borderRadius: 0,
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        overflowY: 'auto',
        overflowX: 'hidden'
      }}
    >
      {/* Logo & Toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
        {!sidebarCollapsed && <h1 style={{ fontSize: '20px', fontWeight: 700 }}>KMS</h1>}
        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          style={{ background: 'transparent', border: 'none', color: themeColors.text, cursor: 'pointer', fontSize: '20px' }}
        >
          {sidebarCollapsed ? '>' : '<'}
        </button>
      </div>

      {/* User Info with Notification Bell */}
      {!sidebarCollapsed && (
        <div style={{ padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontWeight: 600 }}>{user?.username || 'User'}</div>
              <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>{user?.email}</div>
            </div>
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setShowNotifications(!showNotifications)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '20px',
                  position: 'relative'
                }}
              >
                🔔
                {unreadCount > 0 && (
                  <span style={{
                    position: 'absolute',
                    top: '-5px',
                    right: '-5px',
                    background: '#E74C3C',
                    color: 'white',
                    borderRadius: '50%',
                    width: '18px',
                    height: '18px',
                    fontSize: '10px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                  }}>
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
              {/* Notification Dropdown */}
              {showNotifications && (
                <div style={{
                  position: 'absolute',
                  top: '100%',
                  right: 0,
                  marginTop: '8px',
                  width: '300px',
                  maxHeight: '400px',
                  overflow: 'auto',
                  background: themeColors.cardBg,
                  border: `1px solid ${themeColors.cardBorder}`,
                  borderRadius: '8px',
                  boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                  zIndex: 1000
                }}>
                  <div style={{ padding: '12px', borderBottom: `1px solid ${themeColors.cardBorder}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600 }}>{t('knowledge.notifications.title')}</span>
                    {unreadCount > 0 && (
                      <button
                        onClick={markAllNotificationsAsRead}
                        style={{ background: 'transparent', border: 'none', color: themeColors.accent, cursor: 'pointer', fontSize: '12px' }}
                      >
                        {t('knowledge.notifications.markAllRead')}
                      </button>
                    )}
                  </div>
                  {notifications.length === 0 ? (
                    <div style={{ padding: '20px', textAlign: 'center', color: themeColors.textSecondary }}>
                      {t('knowledge.notifications.empty')}
                    </div>
                  ) : (
                    notifications.map(notif => (
                      <div
                        key={notif.id}
                        onClick={() => {
                          if (!notif.is_read) markNotificationAsRead([notif.id]);
                          if (notif.reference_type === 'knowledge' && notif.reference_id) {
                            setActiveTab('knowledge-articles');
                          }
                          setShowNotifications(false);
                        }}
                        style={{
                          padding: '12px',
                          borderBottom: `1px solid ${themeColors.cardBorder}`,
                          cursor: 'pointer',
                          background: notif.is_read ? 'transparent' : 'rgba(74,144,217,0.1)'
                        }}
                      >
                        <div style={{ fontWeight: notif.is_read ? 400 : 600, fontSize: '13px' }}>{notif.title}</div>
                        <div style={{ fontSize: '12px', color: themeColors.textSecondary, marginTop: '4px' }}>{notif.message}</div>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {[
          { key: 'chat', labelKey: 'knowledge.sidebar.chat', icon: '💬' },
          { key: 'web-sources', labelKey: 'knowledge.sidebar.webSources', icon: '🌐' },
          { key: 'notes', labelKey: 'knowledge.sidebar.notes', icon: '📝' },
          { key: 'content', labelKey: 'knowledge.sidebar.aiContent', icon: '🤖' },
          { key: 'projects', labelKey: 'knowledge.sidebar.projects', icon: '📁' },
          { key: 'mindmap', labelKey: 'knowledge.sidebar.mindmap', icon: '🧠' },
          { key: 'knowledge-graph', labelKey: 'knowledge.sidebar.knowledgeGraph', icon: '🔗' },
          { key: 'knowledge-articles', labelKey: 'knowledge.sidebar.knowledgeBase', icon: '📚' }
        ].map(tab => (
          <button
            key={tab.key}
            onClick={() => {
              if (tab.key === 'mindmap') {
                navigate('/mindmap');
              } else {
                setActiveTab(tab.key as TabType);
              }
            }}
            style={{
              ...tabStyle(activeTab === tab.key),
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              justifyContent: sidebarCollapsed ? 'center' : 'flex-start'
            }}
          >
            <span>{tab.icon}</span>
            {!sidebarCollapsed && <span>{t(tab.labelKey as keyof import('../../../i18n/types').TranslationKeys)}</span>}
          </button>
        ))}
      </nav>

      {/* Projects List */}
      {!sidebarCollapsed && activeTab !== 'projects' && (
        <div style={{ flex: 1, overflow: 'auto' }}>
          <h3 style={{ fontSize: '14px', color: themeColors.textSecondary, marginBottom: '8px' }}>{t('knowledge.sidebar.projects')}</h3>
          {projects.map(project => (
            <div
              key={project.id}
              onClick={() => setSelectedProject(selectedProject?.id === project.id ? null : project)}
              style={{
                padding: '10px',
                borderRadius: '8px',
                cursor: 'pointer',
                background: selectedProject?.id === project.id ? 'rgba(74,144,217,0.2)' : 'transparent',
                marginBottom: '4px'
              }}
            >
              <div style={{ fontWeight: 500 }}>{project.name}</div>
              <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                {project.document_count} docs
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bottom Actions */}
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <button
          onClick={toggleTheme}
          style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
        >
          <span>{theme === 'dark' ? '🌙' : '☀️'}</span>
          {!sidebarCollapsed && <span>{theme === 'dark' ? t('knowledge.sidebar.dark') : t('knowledge.sidebar.light')}</span>}
        </button>
        {user?.role === 'admin' && (
          <button
            onClick={() => navigate('/admin')}
            style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
          >
            <span>👤</span>
            {!sidebarCollapsed && <span>{t('knowledge.sidebar.admin')}</span>}
          </button>
        )}
        <button
          onClick={logout}
          style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
        >
          <span>🚪</span>
          {!sidebarCollapsed && <span>{t('knowledge.sidebar.logout')}</span>}
        </button>
        <button
          onClick={() => setShowSettingsPopup(true)}
          style={{ ...tabStyle(false), display: 'flex', alignItems: 'center', gap: '12px', justifyContent: sidebarCollapsed ? 'center' : 'flex-start' }}
        >
          <span>⚙️</span>
          {!sidebarCollapsed && <span>{t('knowledge.sidebar.settings')}</span>}
        </button>
      </div>
    </motion.aside>
  );
};

export default KnowledgeSidebar;
