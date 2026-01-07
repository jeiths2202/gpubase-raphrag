/**
 * Sidebar Component (Left Navigation)
 *
 * Main navigation sidebar with collapsible menu items and submenu support
 */

import React, { useState } from 'react';
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
  ChevronDown,
  Book,
  Download,
  HelpCircle,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import { useUIStore } from '../store/uiStore';

// Sub-navigation item interface
interface SubNavItem {
  id: string;
  path: string;
  labelKey: string;
}

// Navigation item interface
interface NavItem {
  id: string;
  path: string;
  icon: React.ReactNode;
  labelKey: string;
  requiredRole?: 'admin' | 'user' | 'viewer';
  external?: boolean;
  children?: SubNavItem[];
}

// Product list for submenus
const PRODUCTS = ['tmax', 'jeus', 'tibero', 'openframe', 'openframeCobol', 'openframeAsm'];

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
    id: 'productManual',
    path: '/manual',
    icon: <Book size={20} />,
    labelKey: 'common.nav.productManual',
    children: PRODUCTS.map(product => ({
      id: `manual-${product}`,
      path: `/manual/${product}`,
      labelKey: `common.products.${product}`,
    })),
  },
  {
    id: 'installGuide',
    path: '/install',
    icon: <Download size={20} />,
    labelKey: 'common.nav.installGuide',
    children: PRODUCTS.map(product => ({
      id: `install-${product}`,
      path: `/install/${product}`,
      labelKey: `common.products.${product}`,
    })),
  },
  {
    id: 'faq',
    path: '/faq',
    icon: <HelpCircle size={20} />,
    labelKey: 'common.nav.faq',
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

  // Track expanded submenus
  const [expandedMenus, setExpandedMenus] = useState<Set<string>>(new Set());

  // Toggle submenu expansion
  const toggleSubmenu = (itemId: string) => {
    setExpandedMenus(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  // Check if user has required role
  const hasRole = (requiredRole?: 'admin' | 'user' | 'viewer') => {
    if (!requiredRole) return true;
    if (!user) return false;

    const roleHierarchy = { admin: 3, user: 2, viewer: 1 };
    return roleHierarchy[user.role] >= roleHierarchy[requiredRole];
  };

  // Check if any child is active
  const isChildActive = (children?: SubNavItem[]) => {
    if (!children) return false;
    return children.some(child => location.pathname === child.path || location.pathname.startsWith(child.path + '/'));
  };

  // Render navigation item
  const renderNavItem = (item: NavItem) => {
    if (!hasRole(item.requiredRole)) return null;

    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedMenus.has(item.id);
    const isActive = location.pathname === item.path || location.pathname.startsWith(item.path + '/');
    const childActive = isChildActive(item.children);

    // Item with children (expandable)
    if (hasChildren) {
      return (
        <div key={item.id} className="sidebar-nav-group">
          <button
            className={`sidebar-nav-item ${isActive || childActive ? 'active' : ''} ${!leftSidebarOpen ? 'collapsed' : ''}`}
            onClick={() => leftSidebarOpen && toggleSubmenu(item.id)}
            title={!leftSidebarOpen ? t(item.labelKey) : undefined}
          >
            <span className="sidebar-nav-icon">{item.icon}</span>
            {leftSidebarOpen && (
              <>
                <span className="sidebar-nav-label">{t(item.labelKey)}</span>
                <ChevronDown
                  size={16}
                  className={`sidebar-nav-chevron ${isExpanded ? 'expanded' : ''}`}
                />
              </>
            )}
          </button>
          {leftSidebarOpen && isExpanded && (
            <div className="sidebar-submenu">
              {item.children!.map(child => (
                <NavLink
                  key={child.id}
                  to={child.path}
                  className={`sidebar-submenu-item ${location.pathname === child.path ? 'active' : ''}`}
                >
                  <span className="sidebar-submenu-label">{t(child.labelKey)}</span>
                </NavLink>
              ))}
            </div>
          )}
        </div>
      );
    }

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
