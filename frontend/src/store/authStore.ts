import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import axios from 'axios';
import { API_BASE_URL, AUTH_STORAGE_KEYS } from '../config/constants';

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
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  pendingEmail: string | null; // For email verification flow

  // Actions
  setUser: (user: User | null) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  login: (userId: string, password: string) => Promise<boolean>;
  register: (userId: string, email: string, password: string) => Promise<boolean>;
  verifyEmail: (email: string, code: string) => Promise<boolean>;
  resendVerification: (email: string) => Promise<boolean>;
  loginWithGoogle: (credential: string) => Promise<boolean>;
  loginWithSSO: (email: string) => Promise<string>; // Returns redirect URL
  logout: () => void;
  clearError: () => void;
  checkAuth: () => Promise<boolean>;
  setPendingEmail: (email: string | null) => void;
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      pendingEmail: null,

      setUser: (user) => set({ user, isAuthenticated: !!user }),

      setTokens: (accessToken, refreshToken) => {
        set({ accessToken, refreshToken });
        // Set default auth header
        api.defaults.headers.common['Authorization'] = `Bearer ${accessToken}`;
      },

      setPendingEmail: (email) => set({ pendingEmail: email }),

      login: async (userId: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const response = await api.post('/auth/login', {
            username: userId,
            password: password,
          });

          const { access_token, refresh_token } = response.data.data;

          // Get user info
          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
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
            accessToken: access_token,
            refreshToken: refresh_token,
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

          // Store email for verification step
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
          const response = await api.post('/auth/verify', {
            email: email,
            code: code,
          });

          const { access_token, refresh_token } = response.data.data;

          // Get user info
          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
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
            accessToken: access_token,
            refreshToken: refresh_token,
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
          const response = await api.post('/auth/google', { credential });
          const { access_token, refresh_token, user: userData } = response.data.data;

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
            accessToken: access_token,
            refreshToken: refresh_token,
            isAuthenticated: true,
            isLoading: false,
          });

          api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
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

      logout: () => {
        // Call logout API (fire and forget)
        const token = get().accessToken;
        if (token) {
          api.post('/auth/logout').catch(() => {});
        }

        // Clear state
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          error: null,
        });

        // Clear axios header
        delete api.defaults.headers.common['Authorization'];
      },

      clearError: () => set({ error: null }),

      checkAuth: async () => {
        const token = get().accessToken;
        if (!token) {
          set({ isAuthenticated: false });
          return false;
        }

        try {
          api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
          const response = await api.get('/auth/me');
          const userData = response.data.data;

          set({
            user: {
              id: userData.id,
              email: userData.username,
              name: userData.username,
              role: userData.role,
              provider: 'email',
            },
            isAuthenticated: true,
          });

          return true;
        } catch {
          // Try refresh token
          const refreshToken = get().refreshToken;
          if (refreshToken) {
            try {
              const refreshResponse = await api.post('/auth/refresh', {
                refresh_token: refreshToken,
              });
              const { access_token, refresh_token: newRefresh } = refreshResponse.data.data;
              set({ accessToken: access_token, refreshToken: newRefresh });
              api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
              return true;
            } catch {
              get().logout();
              return false;
            }
          }
          get().logout();
          return false;
        }
      },
    }),
    {
      name: 'kms-auth-storage',
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    }
  )
);
