/**
 * useAuth Hook Unit Tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAuthStore } from '../store/authStore';
import { useAuth, useRequireRole, useIsAdmin } from './useAuth';

describe('useAuth', () => {
  beforeEach(() => {
    // Reset store state
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: true,
      error: null,
    });
  });

  describe('initial state', () => {
    it('should return correct initial state', () => {
      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.isAdmin).toBe(false);
    });
  });

  describe('hasRole', () => {
    it('should return false when user is null', () => {
      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.hasRole('user')).toBe(false);
    });

    it('should return true when user has required role', () => {
      useAuthStore.setState({
        user: {
          id: '1',
          name: 'Test User',
          email: 'test@example.com',
          role: 'admin',
        },
        isAuthenticated: true,
      });

      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.hasRole('user')).toBe(true);
      expect(result.current.hasRole('admin')).toBe(true);
    });

    it('should return false when user role is insufficient', () => {
      useAuthStore.setState({
        user: {
          id: '1',
          name: 'Test User',
          email: 'test@example.com',
          role: 'user',
        },
        isAuthenticated: true,
      });

      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.hasRole('admin')).toBe(false);
      expect(result.current.hasRole('leader')).toBe(false);
    });
  });

  describe('isAdmin', () => {
    it('should return false when user is not admin', () => {
      useAuthStore.setState({
        user: {
          id: '1',
          name: 'Test User',
          email: 'test@example.com',
          role: 'user',
        },
        isAuthenticated: true,
      });

      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.isAdmin).toBe(false);
    });

    it('should return true when user is admin', () => {
      useAuthStore.setState({
        user: {
          id: '1',
          name: 'Admin User',
          email: 'admin@example.com',
          role: 'admin',
        },
        isAuthenticated: true,
      });

      const { result } = renderHook(() => useAuth({ validateOnMount: false }));

      expect(result.current.isAdmin).toBe(true);
    });
  });
});

describe('useRequireRole', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: true,
      error: null,
    });
  });

  it('should return hasAccess false when not authenticated', () => {
    const { result } = renderHook(() => useRequireRole('user'));

    expect(result.current.hasAccess).toBe(false);
    expect(result.current.isLoading).toBe(false);
  });

  it('should return hasAccess true when user has required role', () => {
    useAuthStore.setState({
      user: {
        id: '1',
        name: 'Test User',
        email: 'test@example.com',
        role: 'admin',
      },
      isAuthenticated: true,
      isInitialized: true,
    });

    const { result } = renderHook(() => useRequireRole('user'));

    expect(result.current.hasAccess).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });
});

describe('useIsAdmin', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: true,
      error: null,
    });
  });

  it('should return false when not admin', () => {
    const { result } = renderHook(() => useIsAdmin());

    expect(result.current).toBe(false);
  });

  it('should return true when user is admin', () => {
    useAuthStore.setState({
      user: {
        id: '1',
        name: 'Admin User',
        email: 'admin@example.com',
        role: 'admin',
      },
      isAuthenticated: true,
    });

    const { result } = renderHook(() => useIsAdmin());

    expect(result.current).toBe(true);
  });
});
