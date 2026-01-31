/**
 * Sidebar Component (Left Navigation)
 *
 * ChatGPT-style responsive sidebar with smooth slide animations.
 *
 * Features:
 * - Desktop: Open by default, closes with slide-out animation
 * - Mobile/Tablet: Closed by default, overlay mode with backdrop
 * - Close button at top of sidebar (ChatGPT style)
 * - Keyboard accessible (Tab, Enter, Escape)
 * - ARIA attributes for accessibility
 *
 * Breakpoints:
 * - Desktop: > 1024px - Sidebar pushes content
 * - Tablet/Mobile: <= 1024px - Sidebar overlays content
 */

import React, { useState, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Database,
  Brain,
  FileText,
  BarChart3,
  Settings,
  Shield,
  ExternalLink,
  ChevronDown,
  PanelLeftClose,
  HelpCircle,
  Bot,
  Lightbulb,
  Sparkles,
  Cpu,
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

// Navigation items configuration
const NAV_ITEMS: NavItem[] = [
  {
    id: 'agent',
    path: '/agent',
    icon: <Bot size={20} />,
    labelKey: 'common.nav.agent',
  },
  {
    id: 'openAgent',
    path: '/open-agent',
    icon: <Sparkles size={20} />,
    labelKey: 'common.nav.openAgent',
  },
  {
    id: 'openframeRag',
    path: '/openframe-rag',
    icon: <Cpu size={20} />,
    labelKey: 'common.nav.openframeRag',
  },
  {
    id: 'mindmap',
    path: '/mindmap',
    icon: <Brain size={20} />,
    labelKey: 'common.nav.mindmap',
  },
  {
    id: 'ims',
    path: '/ims',
    icon: <Database size={20} />,
    labelKey: 'common.nav.ims',
  },
  {
    id: 'faq',
    path: '/faq',
    icon: <HelpCircle size={20} />,
    labelKey: 'common.nav.faq',
  },
  {
    id: 'documents',
    path: '/documents',
    icon: <FileText size={20} />,
    labelKey: 'common.nav.documents',
    requiredRole: 'admin',
  },
  {
    id: 'analytics',
    path: '/analytics',
    icon: <BarChart3 size={20} />,
    labelKey: 'common.nav.analytics',
    requiredRole: 'admin',
  },
  {
    id: 'improvements',
    path: '/improvements',
    icon: <Lightbulb size={20} />,
    labelKey: 'common.nav.improvements',
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
  const { leftSidebarOpen, isMobile, setLeftSidebarOpen } = useUIStore();

  // Track expanded submenus
  const [expandedMenus, setExpandedMenus] = useState<Set<string>>(new Set());

  // Close sidebar handler
  const handleCloseSidebar = useCallback(() => {
    setLeftSidebarOpen(false);
  }, [setLeftSidebarOpen]);

  // Close sidebar on mobile when navigating
  const handleNavClick = useCallback(() => {
    if (isMobile) {
      setLeftSidebarOpen(false);
    }
  }, [isMobile, setLeftSidebarOpen]);

  // Handle Escape key to close sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && leftSidebarOpen) {
        handleCloseSidebar();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [leftSidebarOpen, handleCloseSidebar]);

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

    const roleHierarchy: Record<string, number> = {
      admin: 5,
      leader: 4,
      senior: 3,
      user: 2,
      viewer: 1,
      guest: 1,
    };
    const userLevel = roleHierarchy[user.role] ?? 1;
    const requiredLevel = roleHierarchy[requiredRole] ?? 1;
    return userLevel >= requiredLevel;
  };

  // Check if any child is active
  const isChildActive = (children?: SubNavItem[]) => {
    if (!children) return false;
    return children.some(
      child => location.pathname === child.path || location.pathname.startsWith(child.path + '/')
    );
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
            className={`sidebar-nav-item ${isActive || childActive ? 'active' : ''}`}
            onClick={() => toggleSubmenu(item.id)}
            aria-expanded={isExpanded}
          >
            <span className="sidebar-nav-icon">{item.icon}</span>
            <span className="sidebar-nav-label">{t(item.labelKey)}</span>
            <ChevronDown
              size={16}
              className={`sidebar-nav-chevron ${isExpanded ? 'expanded' : ''}`}
            />
          </button>
          {isExpanded && (
            <div className="sidebar-submenu">
              {item.children!.map(child => (
                <NavLink
                  key={child.id}
                  to={child.path}
                  className={`sidebar-submenu-item ${location.pathname === child.path ? 'active' : ''}`}
                  onClick={handleNavClick}
                >
                  <span className="sidebar-submenu-label">{t(child.labelKey)}</span>
                </NavLink>
              ))}
            </div>
          )}
        </div>
      );
    }

    const className = `sidebar-nav-item ${isActive ? 'active' : ''}`;

    if (item.external) {
      return (
        <a
          key={item.id}
          href={item.path}
          target="_blank"
          rel="noopener noreferrer"
          className={className}
          onClick={handleNavClick}
        >
          <span className="sidebar-nav-icon">{item.icon}</span>
          <span className="sidebar-nav-label">{t(item.labelKey)}</span>
        </a>
      );
    }

    return (
      <NavLink
        key={item.id}
        to={item.path}
        className={className}
        onClick={handleNavClick}
      >
        <span className="sidebar-nav-icon">{item.icon}</span>
        <span className="sidebar-nav-label">{t(item.labelKey)}</span>
      </NavLink>
    );
  };

  return (
    <aside
      id="main-sidebar"
      className={`portal-sidebar ${leftSidebarOpen ? 'open' : 'closed'}`}
      aria-hidden={!leftSidebarOpen}
      role="navigation"
      aria-label={t('common.nav.mainNavigation') || 'Main navigation'}
    >
      {/* Sidebar Header with Logo and Close Button */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <img src="/tmax-logo.png" alt="Tmax Logo" className="sidebar-logo-img" />
        </div>
        <button
          className="sidebar-close-button"
          onClick={handleCloseSidebar}
          aria-label={t('common.collapseSidebar')}
          aria-expanded={leftSidebarOpen}
          aria-controls="main-sidebar"
          title={t('common.collapseSidebar')}
          tabIndex={leftSidebarOpen ? 0 : -1}
        >
          <PanelLeftClose size={20} />
        </button>
      </div>

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
    </aside>
  );
};

export default Sidebar;
