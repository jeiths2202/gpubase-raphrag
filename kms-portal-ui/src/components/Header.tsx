/**
 * Header Component
 *
 * Top navigation bar with logo, search, user menu, and theme toggle
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Menu,
  Search,
  Bell,
  Sun,
  Moon,
  ChevronDown,
  LogOut,
  Settings,
  User,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import { useUIStore } from '../store/uiStore';

interface HeaderProps {
  onMenuClick?: () => void;
  showAISidebarToggle?: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onMenuClick, showAISidebarToggle = true }) => {
  const { t, language, setLanguage, languages } = useTranslation();
  const { user, logout } = useAuthStore();
  const { theme, setTheme, rightSidebarOpen, toggleRightSidebar } = useUIStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showLangMenu, setShowLangMenu] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const langMenuRef = useRef<HTMLDivElement>(null);

  // Close menus on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
      }
      if (langMenuRef.current && !langMenuRef.current.contains(event.target as Node)) {
        setShowLangMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // TODO: Implement search
    console.log('Search:', searchQuery);
  };

  const handleLogout = () => {
    logout();
    setShowUserMenu(false);
  };

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : theme === 'light' ? 'system' : 'dark');
  };

  return (
    <header className="portal-header">
      {/* Left section */}
      <div className="header-left">
        {onMenuClick && (
          <button
            className="btn btn-ghost header-menu-btn"
            onClick={onMenuClick}
            aria-label="Toggle menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="header-logo">
          <div className="header-logo-icon">K</div>
          <span className="header-logo-text">{t('common.appName')}</span>
        </div>
      </div>

      {/* Center section - Search */}
      <div className="header-center">
        <form className="header-search" onSubmit={handleSearch}>
          <Search size={18} className="header-search-icon" />
          <input
            type="text"
            className="header-search-input"
            placeholder={t('common.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>
      </div>

      {/* Right section */}
      <div className="header-right">
        {/* AI Sidebar Toggle */}
        {showAISidebarToggle && (
          <button
            className="btn btn-ghost header-icon-btn"
            onClick={toggleRightSidebar}
            aria-label={rightSidebarOpen ? 'Close AI sidebar' : 'Open AI sidebar'}
            title={rightSidebarOpen ? 'Close AI sidebar' : 'Open AI sidebar'}
          >
            {rightSidebarOpen ? <PanelRightClose size={20} /> : <PanelRightOpen size={20} />}
          </button>
        )}

        {/* Notifications */}
        <button className="btn btn-ghost header-icon-btn" aria-label="Notifications">
          <Bell size={20} />
        </button>

        {/* Theme toggle */}
        <button
          className="btn btn-ghost header-icon-btn"
          onClick={toggleTheme}
          aria-label="Toggle theme"
          title={`Theme: ${theme}`}
        >
          {theme === 'dark' ? <Moon size={20} /> : <Sun size={20} />}
        </button>

        {/* Language selector */}
        <div className="header-dropdown" ref={langMenuRef}>
          <button
            className="btn btn-ghost header-lang-btn"
            onClick={() => setShowLangMenu(!showLangMenu)}
          >
            <span className="header-lang-flag">{languages[language].flag}</span>
            <ChevronDown size={14} />
          </button>

          {showLangMenu && (
            <div className="header-dropdown-menu">
              {Object.values(languages).map((lang) => (
                <button
                  key={lang.code}
                  className={`header-dropdown-item ${language === lang.code ? 'active' : ''}`}
                  onClick={() => {
                    setLanguage(lang.code);
                    setShowLangMenu(false);
                  }}
                >
                  <span className="header-lang-flag">{lang.flag}</span>
                  <span>{lang.nativeName}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* User menu */}
        {user && (
          <div className="header-dropdown" ref={userMenuRef}>
            <button
              className="btn btn-ghost header-user-btn"
              onClick={() => setShowUserMenu(!showUserMenu)}
            >
              <div className="header-user-avatar">
                {user.avatar ? (
                  <img src={user.avatar} alt={user.name} />
                ) : (
                  <span>{user.name.charAt(0).toUpperCase()}</span>
                )}
              </div>
              <span className="header-user-name">{user.name}</span>
              <ChevronDown size={14} />
            </button>

            {showUserMenu && (
              <div className="header-dropdown-menu">
                <div className="header-dropdown-header">
                  <div className="header-user-info">
                    <span className="header-user-info-name">{user.name}</span>
                    <span className="header-user-info-email">{user.email}</span>
                    <span className="header-user-info-role">{user.role}</span>
                  </div>
                </div>
                <div className="header-dropdown-divider" />
                <button className="header-dropdown-item">
                  <User size={16} />
                  <span>Profile</span>
                </button>
                <button className="header-dropdown-item">
                  <Settings size={16} />
                  <span>{t('common.nav.settings')}</span>
                </button>
                <div className="header-dropdown-divider" />
                <button className="header-dropdown-item danger" onClick={handleLogout}>
                  <LogOut size={16} />
                  <span>{t('common.nav.logout')}</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
};

export default Header;
