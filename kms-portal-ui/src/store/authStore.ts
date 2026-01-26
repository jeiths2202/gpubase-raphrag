/**
 * Auth Store
 *
 * Zustand store for authentication state management.
 *
 * SECURITY FEATURES:
 * - No token storage in JavaScript (HttpOnly cookies used)
 * - Only non-sensitive user profile data stored in state
 * - Session expired callback for automatic logout
 * - Centralized error handling via API layer
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import {
  authApi,
  setSessionExpiredCallback,
  isApiError,
  getErrorMessage,
  type UserProfile,
  type UserRole,
} from '../api';
import { useUIStore } from './uiStore';

// =============================================================================
// Types
// =============================================================================

/**
 * User interface for frontend use
 * Maps from API's UserProfile to frontend-friendly structure
 */
export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  department?: string;
  avatar?: string | null;
  language?: 'en' | 'ko' | 'ja';
  provider?: AuthProvider;
}

/**
 * Authentication provider
 */
export type AuthProvider = 'email' | 'google' | 'sso';

/**
 * Auth state interface
 */
interface AuthState {
  // State
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isInitialized: boolean;
  error: string | null;
  pendingEmail: string | null;

  // Actions - Authentication
  login: (userId: string, password: string) => Promise<boolean>;
  register: (userId: string, email: string, password: string) => Promise<boolean>;
  verifyEmail: (email: string, code: string) => Promise<boolean>;
  resendVerification: (email: string) => Promise<boolean>;
  loginWithGoogle: (credential: string) => Promise<boolean>;
  loginWithSSO: (email: string) => Promise<string>;
  logout: () => Promise<void>;

  // Actions - Session
  checkAuth: () => Promise<boolean>;

  // Actions - State management
  clearError: () => void;
  setLoading: (loading: boolean) => void;
  setPendingEmail: (email: string | null) => void;
  setInitialized: (initialized: boolean) => void;
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Map API UserProfile to frontend User
 */
const mapUserProfile = (profile: UserProfile, provider?: AuthProvider): User => ({
  id: profile.id,
  email: profile.email,
  name: profile.display_name || profile.username || profile.email,
  role: profile.role,
  department: profile.department,
  avatar: profile.avatar,
  language: profile.language,
  provider: provider || 'email',
});

// =============================================================================
// Store Creation
// =============================================================================

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => {
      // Register session expired callback
      // This will be called by API client when refresh fails
      setSessionExpiredCallback(() => {
        console.debug('[Auth] Session expired, logging out');
        set({
          user: null,
          isAuthenticated: false,
          error: null,
        });
      });

      return {
        // Initial state
        user: null,
        isAuthenticated: false,
        isLoading: false,
        isInitialized: false,
        error: null,
        pendingEmail: null,

        // =====================================================================
        // Login with username/password
        // =====================================================================
        login: async (userId: string, password: string): Promise<boolean> => {
          set({ isLoading: true, error: null });

          try {
            // Call login API - server sets HttpOnly cookies
            await authApi.login({ username: userId, password });

            // Fetch user profile - cookies sent automatically
            const profile = await authApi.getCurrentUser();
            const user = mapUserProfile(profile);

            set({
              user,
              isAuthenticated: true,
              isLoading: false,
              error: null,
            });

            // Ensure sidebar is open after successful login
            useUIStore.getState().setLeftSidebarOpen(true);

            return true;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return false;
          }
        },

        // =====================================================================
        // Register new account
        // =====================================================================
        register: async (
          userId: string,
          email: string,
          password: string
        ): Promise<boolean> => {
          set({ isLoading: true, error: null });

          try {
            await authApi.register({ user_id: userId, email, password });

            // Store email for verification step
            set({
              pendingEmail: email,
              isLoading: false,
              error: null,
            });

            return true;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return false;
          }
        },

        // =====================================================================
        // Verify email with code
        // =====================================================================
        verifyEmail: async (email: string, code: string): Promise<boolean> => {
          set({ isLoading: true, error: null });

          try {
            // Verify email - server sets HttpOnly cookies on success
            await authApi.verifyEmail({ email, code });

            // Fetch user profile
            const profile = await authApi.getCurrentUser();
            const user = mapUserProfile(profile);

            set({
              user,
              isAuthenticated: true,
              isLoading: false,
              pendingEmail: null,
              error: null,
            });

            // Ensure sidebar is open after successful verification
            useUIStore.getState().setLeftSidebarOpen(true);

            return true;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return false;
          }
        },

        // =====================================================================
        // Resend verification code
        // =====================================================================
        resendVerification: async (email: string): Promise<boolean> => {
          set({ isLoading: true, error: null });

          try {
            await authApi.resendVerification({ email });
            set({ isLoading: false });
            return true;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return false;
          }
        },

        // =====================================================================
        // Google OAuth login
        // =====================================================================
        loginWithGoogle: async (credential: string): Promise<boolean> => {
          set({ isLoading: true, error: null });

          try {
            // Send Google credential - server validates and sets cookies
            const response = await authApi.loginWithGoogle({ credential });

            // Map user from response or fetch profile
            let user: User;
            if (response.user) {
              user = mapUserProfile(response.user, 'google');
            } else {
              const profile = await authApi.getCurrentUser();
              user = mapUserProfile(profile, 'google');
            }

            set({
              user,
              isAuthenticated: true,
              isLoading: false,
              error: null,
            });

            // Ensure sidebar is open after successful Google login
            useUIStore.getState().setLeftSidebarOpen(true);

            return true;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return false;
          }
        },

        // =====================================================================
        // Initiate SSO login
        // =====================================================================
        loginWithSSO: async (email: string): Promise<string> => {
          set({ isLoading: true, error: null });

          try {
            const response = await authApi.initiateSSOLogin({ email });
            set({ isLoading: false });
            return response.sso_url;
          } catch (error) {
            const message = getErrorMessage(error);
            set({
              isLoading: false,
              error: message,
            });
            return '';
          }
        },

        // =====================================================================
        // Logout
        // =====================================================================
        logout: async (): Promise<void> => {
          try {
            // Call logout API - server clears HttpOnly cookies
            await authApi.logout();
          } catch {
            // Ignore logout errors - clear state anyway
            console.debug('[Auth] Logout API failed, clearing local state');
          }

          // Clear local state
          set({
            user: null,
            isAuthenticated: false,
            isLoading: false,
            error: null,
            pendingEmail: null,
          });
        },

        // =====================================================================
        // Check authentication status
        // =====================================================================
        checkAuth: async (): Promise<boolean> => {
          // Don't set loading for background checks
          const { isAuthenticated } = get();

          try {
            // Try to get current user - cookies sent automatically
            const profile = await authApi.getCurrentUser();
            const user = mapUserProfile(profile);

            set({
              user,
              isAuthenticated: true,
              isInitialized: true,
              error: null,
            });

            return true;
          } catch (error) {
            // If we thought we were authenticated, this is unexpected
            if (isAuthenticated) {
              console.debug('[Auth] Session validation failed');
            }

            // Check if it's an auth error vs network error
            if (isApiError(error) && error.status === 401) {
              // Not authenticated - this is expected for new visitors
              set({
                user: null,
                isAuthenticated: false,
                isInitialized: true,
              });
            } else {
              // Network or other error - keep current state but mark initialized
              set({ isInitialized: true });
            }

            return false;
          }
        },

        // =====================================================================
        // State management actions
        // =====================================================================
        clearError: () => set({ error: null }),

        setLoading: (loading: boolean) => set({ isLoading: loading }),

        setPendingEmail: (email: string | null) => set({ pendingEmail: email }),

        setInitialized: (initialized: boolean) => set({ isInitialized: initialized }),
      };
    },
    {
      name: 'kms-portal-auth',
      storage: createJSONStorage(() => localStorage),
      // SECURITY: Only persist non-sensitive user data
      // Tokens are stored in HttpOnly cookies by the server
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        // NOTE: accessToken and refreshToken intentionally NOT stored
        // They exist only in HttpOnly cookies (inaccessible to JavaScript)
      }),
    }
  )
);

// =============================================================================
// Selector Hooks
// =============================================================================

/** Get current user */
export const useUser = () => useAuthStore((state) => state.user);

/** Check if authenticated */
export const useIsAuthenticated = () => useAuthStore((state) => state.isAuthenticated);

/** Get loading state */
export const useAuthLoading = () => useAuthStore((state) => state.isLoading);

/** Get error state */
export const useAuthError = () => useAuthStore((state) => state.error);

/** Check if auth has been initialized */
export const useAuthInitialized = () => useAuthStore((state) => state.isInitialized);

/** Get pending email for verification */
export const usePendingEmail = () => useAuthStore((state) => state.pendingEmail);
