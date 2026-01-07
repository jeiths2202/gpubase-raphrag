/**
 * Sidebar Component (Left Navigation)
 *
 * Main navigation sidebar with collapsible menu items
 */

import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Home,
  BookOpen,
  Database,
  Brain,
  FileText,
  BarChart3,
  Settings,
  Shield,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import { useUIStore } from '../store/uiStore';

// Navigation item interface
interface NavItem {
  id: string;
  path: string;
  icon: React.ReactNode;
  labelKey: string;
  requiredRole?: 'admin' | 'user' | 'viewer';
  external?: boolean;
}

// Navigation items configuration
const NAV_ITEMS: NavItem[] = [
  {
    id: 'home',
    path: '/',
    icon: <Home size={20} />,
    labelKey: 'common.nav.home',
  },
  {
    id: 'knowledge',
    path: '/knowledge',
    icon: <BookOpen size={20} />,
    labelKey: 'common.nav.knowledge',
  },
  {
    id: 'ims',
    path: '/ims',
    icon: <Database size={20} />,
    labelKey: 'common.nav.ims',
  },
  {
    id: 'mindmap',
    path: '/mindmap',
    icon: <Brain size={20} />,
    labelKey: 'common.nav.mindmap',
  },
  {
    id: 'documents',
    path: '/documents',
    icon: <FileText size={20} />,
    labelKey: 'common.nav.documents',
  },
  {
    id: 'analytics',
    path: '/analytics',
    icon: <BarChart3 size={20} />,
    labelKey: 'common.nav.analytics',
  },
];

const BOTTOM_NAV_ITEMS: NavItem[] = [
  {
    id: 'admin',
    path: '/admin',
    icon: <Shield size={20} />,
    labelKey: 'common.nav.admin',
    requiredRole: 'admin',
  },
  {
    id: 'settings',
    path: '/settings',
    icon: <Settings size={20} />,
    labelKey: 'common.nav.settings',
  },
  {
    id: 'external',
    path: '/portal',
    icon: <ExternalLink size={20} />,
    labelKey: 'common.nav.externalPortal',
    external: true,
  },
];

export const Sidebar: React.FC = () => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useAuthStore();
  const { leftSidebarOpen, toggleLeftSidebar } = useUIStore();

  // Check if user has required role
  const hasRole = (requiredRole?: 'admin' | 'user' | 'viewer') => {
    if (!requiredRole) return true;
    if (!user) return false;

    const roleHierarchy = { admin: 3, user: 2, viewer: 1 };
    return roleHierarchy[user.role] >= roleHierarchy[requiredRole];
  };

  // Render navigation item
  const renderNavItem = (item: NavItem) => {
    if (!hasRole(item.requiredRole)) return null;

    const isActive = location.pathname === item.path;
    const className = `sidebar-nav-item ${isActive ? 'active' : ''} ${!leftSidebarOpen ? 'collapsed' : ''}`;

    if (item.external) {
      return (
        <a
          key={item.id}
          href={item.path}
          target="_blank"
          rel="noopener noreferrer"
          className={className}
          title={!leftSidebarOpen ? t(item.labelKey) : undefined}
        >
          <span className="sidebar-nav-icon">{item.icon}</span>
          {leftSidebarOpen && <span className="sidebar-nav-label">{t(item.labelKey)}</span>}
        </a>
      );
    }

    return (
      <NavLink
        key={item.id}
        to={item.path}
        className={className}
        title={!leftSidebarOpen ? t(item.labelKey) : undefined}
      >
        <span className="sidebar-nav-icon">{item.icon}</span>
        {leftSidebarOpen && <span className="sidebar-nav-label">{t(item.labelKey)}</span>}
      </NavLink>
    );
  };

  return (
    <aside className={`portal-sidebar ${leftSidebarOpen ? 'open' : 'collapsed'}`}>
      {/* Navigation */}
      <nav className="sidebar-nav">
        <div className="sidebar-nav-section">
          {NAV_ITEMS.map(renderNavItem)}
        </div>

        <div className="sidebar-nav-spacer" />

        <div className="sidebar-nav-section sidebar-nav-bottom">
          {BOTTOM_NAV_ITEMS.map(renderNavItem)}
        </div>
      </nav>

      {/* Collapse toggle */}
      <button
        className="sidebar-toggle"
        onClick={toggleLeftSidebar}
        aria-label={leftSidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {leftSidebarOpen ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </button>
    </aside>
  );
};

export default Sidebar;
