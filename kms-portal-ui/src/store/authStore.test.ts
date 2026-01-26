/**
 * Auth Store Unit Tests
 *
 * Tests the auth store state management.
 * Note: Integration with API is tested via useAuth hook tests.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from './authStore';

describe('authStore', () => {
  beforeEach(() => {
    // Reset store state between tests
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isInitialized: false,
      error: null,
    });
  });

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = useAuthStore.getState();

      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('setState - direct state manipulation', () => {
    it('should update user state', () => {
      const mockUser = {
        id: '1',
        name: 'Test User',
        email: 'test@example.com',
        role: 'user' as const,
      };

      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
      });

      expect(useAuthStore.getState().user).toEqual(mockUser);
      expect(useAuthStore.getState().isAuthenticated).toBe(true);
    });

    it('should clear user state', () => {
      // First set a user
      useAuthStore.setState({
        user: {
          id: '1',
          name: 'Test User',
          email: 'test@example.com',
          role: 'user',
        },
        isAuthenticated: true,
      });

      // Then clear
      useAuthStore.setState({
        user: null,
        isAuthenticated: false,
      });

      expect(useAuthStore.getState().user).toBeNull();
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
  });

  describe('clearError', () => {
    it('should clear error state', () => {
      useAuthStore.setState({ error: 'Some error' });

      useAuthStore.getState().clearError();

      expect(useAuthStore.getState().error).toBeNull();
    });
  });

  describe('setInitialized', () => {
    it('should set initialized state to true', () => {
      expect(useAuthStore.getState().isInitialized).toBe(false);

      useAuthStore.getState().setInitialized(true);

      expect(useAuthStore.getState().isInitialized).toBe(true);
    });

    it('should set initialized state to false', () => {
      useAuthStore.setState({ isInitialized: true });

      useAuthStore.getState().setInitialized(false);

      expect(useAuthStore.getState().isInitialized).toBe(false);
    });
  });

  describe('actions are functions', () => {
    it('should have login action', () => {
      expect(typeof useAuthStore.getState().login).toBe('function');
    });

    it('should have logout action', () => {
      expect(typeof useAuthStore.getState().logout).toBe('function');
    });

    it('should have checkAuth action', () => {
      expect(typeof useAuthStore.getState().checkAuth).toBe('function');
    });

    it('should have clearError action', () => {
      expect(typeof useAuthStore.getState().clearError).toBe('function');
    });

    it('should have setInitialized action', () => {
      expect(typeof useAuthStore.getState().setInitialized).toBe('function');
    });
  });

  describe('loading state transitions', () => {
    it('should be able to set loading state', () => {
      useAuthStore.setState({ isLoading: true });
      expect(useAuthStore.getState().isLoading).toBe(true);

      useAuthStore.setState({ isLoading: false });
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
  });

  describe('error state', () => {
    it('should be able to set error state', () => {
      useAuthStore.setState({ error: 'Test error message' });
      expect(useAuthStore.getState().error).toBe('Test error message');
    });

    it('should clear error when clearError is called', () => {
      useAuthStore.setState({ error: 'Test error' });

      useAuthStore.getState().clearError();

      expect(useAuthStore.getState().error).toBeNull();
    });
  });
});
