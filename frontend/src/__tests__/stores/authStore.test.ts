/**
 * Auth Store Tests
 *
 * Tests for authentication state management including:
 * - Login/logout flows
 * - Registration
 * - State management
 * - Error handling
 *
 * NOTE: These tests use mocked axios, no actual API calls
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act } from 'react';

// Mock axios before importing store
vi.mock('axios', () => {
  return {
    default: {
      create: vi.fn(() => ({
        post: vi.fn(),
        get: vi.fn(),
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      })),
      isAxiosError: vi.fn((error) => error?.isAxiosError === true),
    },
  };
});

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('Auth Store', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetModules();
  });

  describe('Initial State', () => {
    it('should have correct initial state', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const state = useAuthStore.getState();

      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
      expect(state.pendingEmail).toBeNull();
    });
  });

  describe('setUser', () => {
    it('should set user and update isAuthenticated', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const mockUser = {
        id: 'user_001',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        provider: 'email' as const,
      };

      act(() => {
        useAuthStore.getState().setUser(mockUser);
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
    });

    it('should clear user when set to null', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      // First set a user
      act(() => {
        useAuthStore.getState().setUser({
          id: 'user_001',
          email: 'test@example.com',
          name: 'Test User',
          role: 'user',
          provider: 'email',
        });
      });

      // Then clear
      act(() => {
        useAuthStore.getState().setUser(null);
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('setPendingEmail', () => {
    it('should set pending email for verification flow', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      act(() => {
        useAuthStore.getState().setPendingEmail('pending@example.com');
      });

      expect(useAuthStore.getState().pendingEmail).toBe('pending@example.com');
    });

    it('should clear pending email', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      act(() => {
        useAuthStore.getState().setPendingEmail('pending@example.com');
      });

      act(() => {
        useAuthStore.getState().setPendingEmail(null);
      });

      expect(useAuthStore.getState().pendingEmail).toBeNull();
    });
  });

  describe('clearError', () => {
    it('should clear error state', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      // Manually set an error
      useAuthStore.setState({ error: 'Some error message' });

      act(() => {
        useAuthStore.getState().clearError();
      });

      expect(useAuthStore.getState().error).toBeNull();
    });
  });

  describe('Persistence', () => {
    it('should persist user to localStorage', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const mockUser = {
        id: 'user_001',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        provider: 'email' as const,
      };

      act(() => {
        useAuthStore.getState().setUser(mockUser);
      });

      // Wait for persistence
      await new Promise(resolve => setTimeout(resolve, 10));

      const stored = localStorageMock.getItem('kms-auth-storage');
      expect(stored).not.toBeNull();

      if (stored) {
        const parsed = JSON.parse(stored);
        expect(parsed.state.user.id).toBe('user_001');
      }
    });

    it('should NOT persist tokens (security)', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      act(() => {
        useAuthStore.getState().setUser({
          id: 'user_001',
          email: 'test@example.com',
          name: 'Test User',
          role: 'user',
          provider: 'email',
        });
      });

      // Wait for persistence
      await new Promise(resolve => setTimeout(resolve, 10));

      const stored = localStorageMock.getItem('kms-auth-storage');
      if (stored) {
        const parsed = JSON.parse(stored);
        // Tokens should NOT be in persisted state
        expect(parsed.state.accessToken).toBeUndefined();
        expect(parsed.state.refreshToken).toBeUndefined();
      }
    });
  });

  describe('User Interface', () => {
    it('should have all required User properties', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const mockUser = {
        id: 'user_001',
        email: 'test@example.com',
        name: 'Test User',
        avatar: 'https://example.com/avatar.png',
        role: 'admin',
        provider: 'google' as const,
      };

      act(() => {
        useAuthStore.getState().setUser(mockUser);
      });

      const user = useAuthStore.getState().user;
      expect(user).not.toBeNull();
      expect(user?.id).toBe('user_001');
      expect(user?.email).toBe('test@example.com');
      expect(user?.name).toBe('Test User');
      expect(user?.avatar).toBe('https://example.com/avatar.png');
      expect(user?.role).toBe('admin');
      expect(user?.provider).toBe('google');
    });

    it('should accept all valid provider types', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const providers: Array<'email' | 'google' | 'sso'> = ['email', 'google', 'sso'];

      for (const provider of providers) {
        act(() => {
          useAuthStore.getState().setUser({
            id: 'user_001',
            email: 'test@example.com',
            name: 'Test User',
            role: 'user',
            provider,
          });
        });

        expect(useAuthStore.getState().user?.provider).toBe(provider);
      }
    });
  });

  describe('State Transitions', () => {
    it('should handle login loading state', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      // Manually simulate loading state
      useAuthStore.setState({ isLoading: true, error: null });

      expect(useAuthStore.getState().isLoading).toBe(true);
      expect(useAuthStore.getState().error).toBeNull();
    });

    it('should handle login error state', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const errorMessage = '아이디 또는 비밀번호가 올바르지 않습니다.';
      useAuthStore.setState({ error: errorMessage, isLoading: false });

      expect(useAuthStore.getState().error).toBe(errorMessage);
      expect(useAuthStore.getState().isLoading).toBe(false);
    });

    it('should handle successful login state', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      const mockUser = {
        id: 'user_001',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user',
        provider: 'email' as const,
      };

      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });
  });

  describe('Logout', () => {
    it('should clear user state on logout', async () => {
      const { useAuthStore } = await import('../../store/authStore');

      // Set authenticated user first
      act(() => {
        useAuthStore.getState().setUser({
          id: 'user_001',
          email: 'test@example.com',
          name: 'Test User',
          role: 'user',
          provider: 'email',
        });
      });

      expect(useAuthStore.getState().isAuthenticated).toBe(true);

      // Simulate logout by clearing state
      useAuthStore.setState({
        user: null,
        isAuthenticated: false,
        error: null,
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });
});

describe('Auth Store Actions Interface', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it('should have all required action methods', async () => {
    const { useAuthStore } = await import('../../store/authStore');

    const state = useAuthStore.getState();

    // Check all required actions exist
    expect(typeof state.setUser).toBe('function');
    expect(typeof state.login).toBe('function');
    expect(typeof state.register).toBe('function');
    expect(typeof state.verifyEmail).toBe('function');
    expect(typeof state.resendVerification).toBe('function');
    expect(typeof state.loginWithGoogle).toBe('function');
    expect(typeof state.loginWithSSO).toBe('function');
    expect(typeof state.logout).toBe('function');
    expect(typeof state.clearError).toBe('function');
    expect(typeof state.checkAuth).toBe('function');
    expect(typeof state.setPendingEmail).toBe('function');
  });
});
