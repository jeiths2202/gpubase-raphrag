/**
 * API Module Index
 *
 * Central export point for all API-related modules.
 *
 * Usage:
 * ```typescript
 * import { apiClient, authApi, isApiError } from '@/api';
 *
 * // Using auth API
 * const user = await authApi.login({ username: 'user', password: 'pass' });
 *
 * // Using raw client for custom endpoints
 * const data = await apiClient.get('/custom/endpoint');
 *
 * // Error handling
 * try {
 *   await authApi.login(credentials);
 * } catch (error) {
 *   if (isApiError(error)) {
 *     console.log(error.code, error.message);
 *   }
 * }
 * ```
 */

// API Client
export { default as apiClient } from './client';
export {
  setSessionExpiredCallback,
  isApiError,
  getErrorMessage,
  type ApiError,
} from './client';

// Auth API
export { default as authApi } from './auth.api';
export {
  login,
  register,
  verifyEmail,
  resendVerification,
  loginWithGoogle,
  initiateSSOLogin,
  getCurrentUser,
  refreshToken,
  logout,
} from './auth.api';

// Types
export type {
  // Common
  ApiResponse,
  ApiErrorResponse,
  // User
  UserRole,
  AuthProvider,
  UserProfile,
  // Auth Requests
  LoginRequest,
  RegisterRequest,
  VerifyEmailRequest,
  ResendVerificationRequest,
  GoogleAuthRequest,
  SSORequest,
  RefreshTokenRequest,
  // Auth Responses
  TokenResponse,
  LoginResponse,
  RegisterResponse,
  VerifyEmailResponse,
  GoogleAuthResponse,
  SSOResponse,
  RefreshResponse,
  // Error
  AuthErrorCode,
} from './types';

export { AUTH_ERROR_CODES } from './types';
