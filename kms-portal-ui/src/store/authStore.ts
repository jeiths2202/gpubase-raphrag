/**
 * Auth Store
 *
 * Zustand store for authentication state management
 * Uses localStorage for mock token persistence
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// User interface
export interface User {
  id: string;
  userId: string;
  email: string;
  name: string;
  role: 'admin' | 'user' | 'viewer';
  department?: string;
  avatar?: string | null;
  subscription?: 'free' | 'pro' | 'enterprise';
}

// Auth state interface
interface AuthState {
  // State
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (userId: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => void;
  refreshSession: () => Promise<void>;
  clearError: () => void;
  setLoading: (loading: boolean) => void;
}

// API base URL
const API_BASE = '/api/v1';

// Create auth store with persistence
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      // Login action
      login: async (userId: string, password: string) => {
        set({ isLoading: true, error: null });

        try {
          const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ username: userId, password }),
          });

          if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error?.message || 'Login failed');
          }

          const data = await response.json();
          const accessToken = data.data?.access_token || data.accessToken;
          const refreshToken = data.data?.refresh_token || data.refreshToken;

          // Fetch user info from /me endpoint
          const meResponse = await fetch(`${API_BASE}/auth/me`, {
            method: 'GET',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${accessToken}`,
            },
            credentials: 'include',
          });

          let user: User | null = null;
          if (meResponse.ok) {
            const meData = await meResponse.json();
            const userData = meData.data || meData;
            user = {
              id: userData.id,
              userId: userData.email,
              email: userData.email,
              name: userData.username || userData.display_name || userData.email,
              role: userData.role || 'user',
              department: userData.department,
              subscription: userData.subscription || 'free',
            };
          }

          set({
            user,
            accessToken,
            refreshToken,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Login failed',
          });
          throw error;
        }
      },

      // Google OAuth login (mock)
      loginWithGoogle: async () => {
        set({ isLoading: true, error: null });

        try {
          const response = await fetch(`${API_BASE}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          });

          if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Google login failed');
          }

          const data = await response.json();

          set({
            user: data.user,
            accessToken: data.accessToken,
            refreshToken: data.refreshToken,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          });
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Google login failed',
          });
          throw error;
        }
      },

      // Logout action
      logout: () => {
        const { accessToken } = get();

        // Call logout API (fire and forget)
        if (accessToken) {
          fetch(`${API_BASE}/auth/logout`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${accessToken}`,
            },
          }).catch(() => {
            // Ignore errors on logout
          });
        }

        // Clear state
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
          error: null,
        });
      },

      // Refresh session
      refreshSession: async () => {
        const { refreshToken } = get();

        if (!refreshToken) {
          throw new Error('No refresh token available');
        }

        try {
          const response = await fetch(`${API_BASE}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refreshToken }),
          });

          if (!response.ok) {
            // Refresh failed, logout
            get().logout();
            throw new Error('Session expired');
          }

          const data = await response.json();

          set({
            accessToken: data.accessToken,
          });
        } catch (error) {
          get().logout();
          throw error;
        }
      },

      // Clear error
      clearError: () => set({ error: null }),

      // Set loading
      setLoading: (loading: boolean) => set({ isLoading: loading }),
    }),
    {
      name: 'kms-portal-auth',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// Selector hooks for common use cases
export const useUser = () => useAuthStore((state) => state.user);
export const useIsAuthenticated = () => useAuthStore((state) => state.isAuthenticated);
export const useAuthLoading = () => useAuthStore((state) => state.isLoading);
export const useAuthError = () => useAuthStore((state) => state.error);
