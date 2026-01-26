/**
 * AuthGuard Component
 *
 * Enhanced authentication guard that:
 * - Waits for session initialization before redirecting
 * - Shows loading state during auth check
 * - Supports role-based access control
 * - Integrates with the useAuth hook
 */

import React from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import type { UserRole } from '../../api';

interface AuthGuardProps {
  /**
   * Minimum role required to access the route
   * If not specified, any authenticated user can access
   */
  requiredRole?: UserRole;

  /**
   * Custom loading component
   */
  loadingComponent?: React.ReactNode;

  /**
   * Redirect path when not authenticated
   * @default '/login'
   */
  redirectTo?: string;

  /**
   * Redirect path when user doesn't have required role
   * @default '/'
   */
  unauthorizedRedirectTo?: string;
}

/**
 * Default loading spinner component
 */
const DefaultLoadingComponent: React.FC = () => (
  <div className="auth-guard-loading">
    <div className="auth-guard-spinner" />
  </div>
);

export const AuthGuard: React.FC<AuthGuardProps> = ({
  requiredRole,
  loadingComponent,
  redirectTo = '/login',
  unauthorizedRedirectTo = '/',
}) => {
  const location = useLocation();
  const { isAuthenticated, isLoading, isInitialized, hasRole } = useAuth();

  // Show loading state while checking auth
  if (!isInitialized || isLoading) {
    return <>{loadingComponent ?? <DefaultLoadingComponent />}</>;
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    // Save the attempted URL for post-login redirect
    return <Navigate to={redirectTo} state={{ from: location }} replace />;
  }

  // Check role-based access
  if (requiredRole && !hasRole(requiredRole)) {
    return <Navigate to={unauthorizedRedirectTo} replace />;
  }

  // Render the protected content
  return <Outlet />;
};

export default AuthGuard;
