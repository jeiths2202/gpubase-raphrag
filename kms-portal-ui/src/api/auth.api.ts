/**
 * Auth API
 *
 * Type-safe wrappers for authentication endpoints.
 * All endpoints use HttpOnly cookie authentication.
 */

import apiClient from './client';
import type {
  ApiResponse,
  UserProfile,
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  VerifyEmailRequest,
  VerifyEmailResponse,
  ResendVerificationRequest,
  GoogleAuthRequest,
  GoogleAuthResponse,
  SSORequest,
  SSOResponse,
  RefreshResponse,
} from './types';

// =============================================================================
// Auth Endpoints
// =============================================================================

/**
 * Login with username and password
 *
 * @param credentials - Username and password
 * @returns Login response with optional tokens (HttpOnly cookies set by server)
 *
 * Flow:
 * 1. POST credentials to /auth/login
 * 2. Server validates and sets HttpOnly cookies
 * 3. Response may include token data for backward compatibility
 */
export const login = async (credentials: LoginRequest): Promise<LoginResponse> => {
  const response = await apiClient.post<ApiResponse<LoginResponse>>('/auth/login', credentials);
  return response.data.data;
};

/**
 * Register a new user account
 *
 * @param data - User registration data
 * @returns Registration response with verification instructions
 *
 * Flow:
 * 1. POST registration data to /auth/register
 * 2. Server creates pending user and sends verification email
 * 3. User must verify email before login
 */
export const register = async (data: RegisterRequest): Promise<RegisterResponse> => {
  const response = await apiClient.post<ApiResponse<RegisterResponse>>('/auth/register', data);
  return response.data.data;
};

/**
 * Verify email with verification code
 *
 * @param data - Email and verification code
 * @returns Verification response (HttpOnly cookies set by server on success)
 *
 * Flow:
 * 1. POST email and code to /auth/verify
 * 2. Server validates code and activates user
 * 3. Server sets HttpOnly cookies for immediate login
 */
export const verifyEmail = async (data: VerifyEmailRequest): Promise<VerifyEmailResponse> => {
  const response = await apiClient.post<ApiResponse<VerifyEmailResponse>>('/auth/verify', data);
  return response.data.data;
};

/**
 * Resend verification code to email
 *
 * @param data - Email address
 * @returns Success message
 */
export const resendVerification = async (
  data: ResendVerificationRequest
): Promise<{ message: string }> => {
  const response = await apiClient.post<ApiResponse<{ message: string }>>(
    '/auth/resend-verification',
    data
  );
  return response.data.data;
};

/**
 * Authenticate with Google OAuth
 *
 * @param data - Google credential token from OAuth flow
 * @returns User profile and optional tokens (HttpOnly cookies set by server)
 *
 * Flow:
 * 1. Client completes Google OAuth and receives credential
 * 2. POST credential to /auth/google
 * 3. Server validates with Google API and creates/updates user
 * 4. Server sets HttpOnly cookies
 */
export const loginWithGoogle = async (data: GoogleAuthRequest): Promise<GoogleAuthResponse> => {
  const response = await apiClient.post<ApiResponse<GoogleAuthResponse>>('/auth/google', data);
  return response.data.data;
};

/**
 * Initiate SSO authentication
 *
 * @param data - Corporate email address
 * @returns SSO redirect URL
 *
 * Flow:
 * 1. POST corporate email to /auth/sso
 * 2. Server validates email domain
 * 3. Server returns SSO provider URL
 * 4. Client redirects to SSO URL
 * 5. After SSO, user returns to /auth/sso/callback
 */
export const initiateSSOLogin = async (data: SSORequest): Promise<SSOResponse> => {
  const response = await apiClient.post<ApiResponse<SSOResponse>>('/auth/sso', data);
  return response.data.data;
};

/**
 * Get current user profile
 *
 * @returns Current user profile if authenticated
 *
 * Used for:
 * - Initial session validation on app mount
 * - Fetching user profile after login
 * - Checking authentication status
 */
export const getCurrentUser = async (): Promise<UserProfile> => {
  const response = await apiClient.get<ApiResponse<UserProfile>>('/auth/me');
  return response.data.data;
};

/**
 * Refresh access token
 *
 * @returns New access token (HttpOnly cookies updated by server)
 *
 * Note: This is automatically called by the axios interceptor on 401.
 * Can also be called manually for proactive refresh.
 */
export const refreshToken = async (): Promise<RefreshResponse> => {
  const response = await apiClient.post<ApiResponse<RefreshResponse>>('/auth/refresh');
  return response.data.data;
};

/**
 * Logout and invalidate session
 *
 * Flow:
 * 1. POST to /auth/logout
 * 2. Server invalidates tokens (if using token blacklist)
 * 3. Server clears HttpOnly cookies
 * 4. Client clears local state
 */
export const logout = async (): Promise<void> => {
  await apiClient.post('/auth/logout');
};

// =============================================================================
// Export all as namespace for convenient access
// =============================================================================

export const authApi = {
  login,
  register,
  verifyEmail,
  resendVerification,
  loginWithGoogle,
  initiateSSOLogin,
  getCurrentUser,
  refreshToken,
  logout,
};

export default authApi;
