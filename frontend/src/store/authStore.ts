/**
 * Authentication Store
 *
 * SECURITY FEATURES:
 * - No localStorage token storage (prevents XSS token theft)
 * - HttpOnly cookies used for authentication
 * - withCredentials enables automatic cookie handling
 * - Only non-sensitive user info stored in memory
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import axios from 'axios';
import { API_BASE_URL } from '../config/constants';

export interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  role: string;
  provider: 'email' | 'google' | 'sso';
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  pendingEmail: string | null; // For email verification flow

  // Actions
  setUser: (user: User | null) => void;
  login: (userId: string, password: string) => Promise<boolean>;
  register: (userId: string, email: string, password: string) => Promise<boolean>;
  verifyEmail: (email: string, code: string) => Promise<boolean>;
  resendVerification: (email: string) => Promise<boolean>;
  loginWithGoogle: (credential: string) => Promise<boolean>;
  loginWithSSO: (email: string) => Promise<string>; // Returns redirect URL
  logout: () => Promise<void>;
  clearError: () => void;
  checkAuth: () => Promise<boolean>;
  setPendingEmail: (email: string | null) => void;
}

/**
 * SECURITY: API client with HttpOnly cookie authentication
 * - withCredentials: true enables automatic cookie inclusion
 * - No Authorization header needed - cookies are sent automatically
 */
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // SECURITY: Enable HttpOnly cookie authentication
});

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      pendingEmail: null,

      setUser: (user) => set({ user, isAuthenticated: !!user }),

      setPendingEmail: (email) => set({ pendingEmail: email }),

      login: async (userId: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          // Login - server sets HttpOnly cookies automatically
          await api.post('/auth/login', {
            username: userId,
            password: password,
          });

          // Get user info - cookies are sent automatically
          const userResponse = await api.get('/auth/me');
          const userData = userResponse.data.data;

          const user: User = {
            id: userData.id,
            email: userData.email || userId,
            name: userData.username,
            role: userData.role,
            provider: 'email',
          };

          set({
            user,
            isAuthenticated: true,
            isLoading: false,
          });

          return true;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || '로그인에 실패했습니다.'
            : '로그인에 실패했습니다.';
          set({ error: message, isLoading: false });
          return false;
        }
      },

      register: async (userId: string, email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          await api.post('/auth/register', {
            user_id: userId,
            email: email,
            password: password,
          });

          // Store email for verification step (not sensitive)
          set({ pendingEmail: email, isLoading: false });
          return true;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || '회원가입에 실패했습니다.'
            : '회원가입에 실패했습니다.';
          set({ error: message, isLoading: false });
          return false;
        }
      },

      verifyEmail: async (email: string, code: string) => {
        set({ isLoading: true, error: null });
        try {
          // Verify - server sets HttpOnly cookies automatically
          await api.post('/auth/verify', {
            email: email,
            code: code,
          });

          // Get user info - cookies are sent automatically
          const userResponse = await api.get('/auth/me');
          const userData = userResponse.data.data;

          const user: User = {
            id: userData.id,
            email: email,
            name: userData.username,
            role: userData.role,
            provider: 'email',
          };

          set({
            user,
            isAuthenticated: true,
            isLoading: false,
            pendingEmail: null,
          });

          return true;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || '인증에 실패했습니다.'
            : '인증에 실패했습니다.';
          set({ error: message, isLoading: false });
          return false;
        }
      },

      resendVerification: async (email: string) => {
        set({ isLoading: true, error: null });
        try {
          await api.post('/auth/resend-verification', { email });
          set({ isLoading: false });
          return true;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || '인증 코드 재발송에 실패했습니다.'
            : '인증 코드 재발송에 실패했습니다.';
          set({ error: message, isLoading: false });
          return false;
        }
      },

      loginWithGoogle: async (credential: string) => {
        set({ isLoading: true, error: null });
        try {
          // Google login - server sets HttpOnly cookies automatically
          const response = await api.post('/auth/google', { credential });
          const userData = response.data.data.user;

          const user: User = {
            id: userData.id,
            email: userData.email,
            name: userData.name,
            avatar: userData.picture,
            role: userData.role || 'user',
            provider: 'google',
          };

          set({
            user,
            isAuthenticated: true,
            isLoading: false,
          });

          return true;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || 'Google login failed'
            : 'Google login failed';
          set({ error: message, isLoading: false });
          return false;
        }
      },

      loginWithSSO: async (email: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await api.post('/auth/sso', { email });
          set({ isLoading: false });
          return response.data.data.sso_url;
        } catch (error: unknown) {
          const message = axios.isAxiosError(error)
            ? error.response?.data?.detail?.message || 'SSO 로그인에 실패했습니다.'
            : 'SSO 로그인에 실패했습니다.';
          set({ error: message, isLoading: false });
          return '';
        }
      },

      logout: async () => {
        try {
          // Call logout API - server clears HttpOnly cookies
          await api.post('/auth/logout');
        } catch {
          // Ignore logout errors
        }

        // Clear local state (not tokens - they're in HttpOnly cookies)
        set({
          user: null,
          isAuthenticated: false,
          error: null,
        });
      },

      clearError: () => set({ error: null }),

      checkAuth: async () => {
        try {
          // Check if session is valid - cookies are sent automatically
          const response = await api.get('/auth/me');
          const userData = response.data.data;

          set({
            user: {
              id: userData.id,
              email: userData.email || userData.username,
              name: userData.username,
              role: userData.role,
              provider: 'email',
            },
            isAuthenticated: true,
          });

          return true;
        } catch {
          // Session invalid or expired - try refresh (cookies sent automatically)
          try {
            await api.post('/auth/refresh');
            // Refresh successful, check auth again
            const response = await api.get('/auth/me');
            const userData = response.data.data;

            set({
              user: {
                id: userData.id,
                email: userData.email || userData.username,
                name: userData.username,
                role: userData.role,
                provider: 'email',
              },
              isAuthenticated: true,
            });
            return true;
          } catch {
            // Refresh failed - user needs to login again
            set({ user: null, isAuthenticated: false });
            return false;
          }
        }
      },
    }),
    {
      name: 'kms-auth-storage',
      // SECURITY: Only persist non-sensitive user info, NOT tokens
      // Tokens are stored in HttpOnly cookies by the server
      partialize: (state) => ({
        user: state.user,
        // NOTE: accessToken and refreshToken removed - using HttpOnly cookies
      }),
    }
  )
);
