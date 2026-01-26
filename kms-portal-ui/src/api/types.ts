/**
 * API Types
 *
 * TypeScript interfaces for API requests and responses.
 * Aligned with backend API contract.
 */

// =============================================================================
// Common Response Types
// =============================================================================

/**
 * Standard API success response wrapper
 */
export interface ApiResponse<T> {
  success: true;
  data: T;
  meta?: {
    request_id?: string;
    timestamp?: string;
  };
}

/**
 * Standard API error response
 */
export interface ApiErrorResponse {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  meta?: {
    request_id?: string;
    timestamp?: string;
  };
}

// =============================================================================
// User Types
// =============================================================================

/**
 * User role hierarchy
 */
export type UserRole = 'admin' | 'leader' | 'senior' | 'user' | 'guest';

/**
 * Authentication provider
 */
export type AuthProvider = 'email' | 'google' | 'sso' | 'microsoft' | 'github';

/**
 * User profile returned from /auth/me
 */
export interface UserProfile {
  id: string;
  email: string;
  username: string;
  display_name?: string;
  role: UserRole;
  department?: string;
  avatar?: string;
  language?: 'en' | 'ko' | 'ja';
  is_active: boolean;
  created_at: string;
  last_login_at?: string;
}

// =============================================================================
// Auth Request Types
// =============================================================================

/**
 * Login request payload
 */
export interface LoginRequest {
  username: string;
  password: string;
}

/**
 * Registration request payload
 */
export interface RegisterRequest {
  user_id: string;
  email: string;
  password: string;
}

/**
 * Email verification request payload
 */
export interface VerifyEmailRequest {
  email: string;
  code: string;
}

/**
 * Resend verification request payload
 */
export interface ResendVerificationRequest {
  email: string;
}

/**
 * Google OAuth request payload
 */
export interface GoogleAuthRequest {
  credential: string;
}

/**
 * SSO initiation request payload
 */
export interface SSORequest {
  email: string;
}

/**
 * Token refresh request payload
 * Note: In HttpOnly cookie mode, this may be empty as cookie is sent automatically
 */
export interface RefreshTokenRequest {
  refresh_token?: string;
}

// =============================================================================
// Auth Response Types
// =============================================================================

/**
 * Token response from login/register/verify
 * Note: With HttpOnly cookies, tokens may not be in response body
 */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

/**
 * Login response - combines token and user info
 */
export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token_type?: 'bearer';
  expires_in?: number;
  user?: UserProfile;
}

/**
 * Registration response
 */
export interface RegisterResponse {
  message: string;
  email: string;
}

/**
 * Email verification response
 */
export interface VerifyEmailResponse {
  message: string;
  access_token?: string;
  refresh_token?: string;
}

/**
 * Google auth response
 */
export interface GoogleAuthResponse {
  user: UserProfile;
  access_token?: string;
  refresh_token?: string;
}

/**
 * SSO initiation response
 */
export interface SSOResponse {
  sso_url: string;
  token?: string;
}

/**
 * Token refresh response
 */
export interface RefreshResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
}

// =============================================================================
// Error Codes
// =============================================================================

/**
 * Known authentication error codes
 */
export const AUTH_ERROR_CODES = {
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  AUTH_INVALID_CREDENTIALS: 'AUTH_INVALID_CREDENTIALS',
  AUTH_INVALID_TOKEN: 'AUTH_INVALID_TOKEN',
  AUTH_TOKEN_EXPIRED: 'AUTH_TOKEN_EXPIRED',
  AUTH_MISSING_TOKEN: 'AUTH_MISSING_TOKEN',
  AUTH_INSUFFICIENT_PERMISSION: 'AUTH_INSUFFICIENT_PERMISSION',
  AUTH_GOOGLE_FAILED: 'AUTH_GOOGLE_FAILED',
  EMAIL_ALREADY_EXISTS: 'EMAIL_ALREADY_EXISTS',
  INVALID_CODE: 'INVALID_CODE',
  VALIDATION_ERROR: 'VALIDATION_ERROR',
} as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[keyof typeof AUTH_ERROR_CODES];
