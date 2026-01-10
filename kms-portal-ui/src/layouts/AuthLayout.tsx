/**
 * Auth Layout Component
 *
 * Simple centered layout for authentication pages (login, register)
 * Note: Theme/language controls are rendered by individual pages (e.g., LoginPage)
 */

import React from 'react';
import { Outlet } from 'react-router-dom';

export const AuthLayout: React.FC = () => {
  return (
    <div className="auth-layout">
      {/* Background decoration */}
      <div className="auth-background">
        <div className="auth-background-gradient" />
        <div className="auth-background-pattern" />
      </div>

      {/* Content - pages render their own controls */}
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
