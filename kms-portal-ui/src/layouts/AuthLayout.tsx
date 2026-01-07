/**
 * Auth Layout Component
 *
 * Simple centered layout for authentication pages (login, register)
 */

import React from 'react';
import { Outlet } from 'react-router-dom';
import { useTranslation } from '../hooks/useTranslation';
import { Sun, Moon, Globe } from 'lucide-react';
import { useUIStore } from '../store/uiStore';

export const AuthLayout: React.FC = () => {
  const { language, toggleLanguage, languages } = useTranslation();
  const { theme, setTheme } = useUIStore();

  const toggleTheme = () => {
    setTheme(theme === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="auth-layout">
      {/* Background decoration */}
      <div className="auth-background">
        <div className="auth-background-gradient" />
        <div className="auth-background-pattern" />
      </div>

      {/* Top controls */}
      <div className="auth-controls">
        <button
          className="btn btn-ghost auth-control-btn"
          onClick={toggleTheme}
          aria-label="Toggle theme"
        >
          {theme === 'dark' ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <button
          className="btn btn-ghost auth-control-btn"
          onClick={toggleLanguage}
          aria-label="Change language"
        >
          <Globe size={18} />
          <span>{languages[language].flag}</span>
        </button>
      </div>

      {/* Content */}
      <div className="auth-content">
        <Outlet />
      </div>

      {/* Footer */}
      <footer className="auth-footer">
        <span>&copy; 2024 KMS Portal. All rights reserved.</span>
      </footer>
    </div>
  );
};

export default AuthLayout;
