/**
 * PublicGuard Component
 *
 * Guard for public routes (login, register, etc.) that:
 * - Redirects authenticated users away from public pages
 * - Waits for session initialization before redirecting
 * - Shows loading state during auth check
 */

import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

interface PublicGuardProps {
  /**
   * Redirect path when authenticated
   * @default '/'
   */
  redirectTo?: string;

  /**
   * Custom loading component
   */
  loadingComponent?: React.ReactNode;
}

/**
 * Default loading spinner component
 */
const DefaultLoadingComponent: React.FC = () => (
  <div className="auth-guard-loading">
    <div className="auth-guard-spinner" />
  </div>
);

export const PublicGuard: React.FC<PublicGuardProps> = ({
  redirectTo = '/',
  loadingComponent,
}) => {
  const location = useLocation();
  const { isAuthenticated, isLoading, isInitialized, user } = useAuth();

  // Show loading state while checking auth
  if (!isInitialized || isLoading) {
    return <>{loadingComponent ?? <DefaultLoadingComponent />}</>;
  }

  // If authenticated, redirect to home (or the page they came from)
  if (isAuthenticated) {
    // Check if there's a saved redirect location
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname;

    // Route based on user role
    let targetPath = redirectTo;
    if (user?.role === 'user') {
      targetPath = from || '/knowledge';
    } else {
      targetPath = from || redirectTo;
    }

    return <Navigate to={targetPath} replace />;
  }

  // Render the public content
  return <Outlet />;
};

export default PublicGuard;
