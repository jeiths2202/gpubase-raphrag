/**
 * API Client
 *
 * Centralized axios instance with request/response interceptors.
 * Implements HttpOnly cookie authentication pattern.
 *
 * Security Features:
 * - withCredentials: true for automatic cookie handling
 * - No tokens stored in JavaScript (HttpOnly cookies)
 * - Automatic 401 handling with session refresh
 * - Centralized error transformation
 */

import axios, {
  AxiosError,
  AxiosInstance,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios';
import { API_BASE_URL } from '../config/constants';
import type { ApiErrorResponse } from './types';

// =============================================================================
// Types
// =============================================================================

/**
 * Transformed API error for consistent error handling
 */
export interface ApiError {
  code: string;
  message: string;
  status: number;
  details?: Record<string, unknown>;
  originalError?: AxiosError;
}

/**
 * Callback for handling session expiration
 */
type SessionExpiredCallback = () => void;

// =============================================================================
// API Client Singleton
// =============================================================================

/**
 * Session expired callback - set by auth store
 */
let onSessionExpired: SessionExpiredCallback | null = null;

/**
 * Flag to prevent multiple refresh attempts
 */
let isRefreshing = false;

/**
 * Queue of requests waiting for token refresh
 */
let refreshSubscribers: Array<(success: boolean) => void> = [];

/**
 * Subscribe to token refresh completion
 */
const subscribeToRefresh = (callback: (success: boolean) => void) => {
  refreshSubscribers.push(callback);
};

/**
 * Notify all subscribers of refresh result
 */
const notifyRefreshSubscribers = (success: boolean) => {
  refreshSubscribers.forEach((callback) => callback(success));
  refreshSubscribers = [];
};

/**
 * Attempt to refresh the session
 */
const attemptRefresh = async (client: AxiosInstance): Promise<boolean> => {
  try {
    await client.post('/auth/refresh');
    return true;
  } catch {
    return false;
  }
};

// =============================================================================
// Axios Instance
// =============================================================================

/**
 * Create axios instance with base configuration
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  // SECURITY: Enable HttpOnly cookie authentication
  // Cookies are automatically included in requests and responses
  withCredentials: true,
  // Reasonable timeout for API requests
  timeout: 30000,
});

// =============================================================================
// Request Interceptor
// =============================================================================

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Log requests in development
    if (import.meta.env.DEV) {
      console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`);
    }

    // No need to add Authorization header - using HttpOnly cookies
    // Cookies are automatically sent with withCredentials: true

    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// =============================================================================
// Response Interceptor
// =============================================================================

apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // Log successful responses in development
    if (import.meta.env.DEV) {
      console.debug(`[API] ${response.status} ${response.config.url}`);
    }
    return response;
  },
  async (error: AxiosError<ApiErrorResponse>) => {
    const originalRequest = error.config;

    // Handle 401 Unauthorized - attempt token refresh
    if (error.response?.status === 401 && originalRequest) {
      // Skip refresh for auth endpoints to prevent infinite loops
      const isAuthEndpoint =
        originalRequest.url?.includes('/auth/login') ||
        originalRequest.url?.includes('/auth/refresh') ||
        originalRequest.url?.includes('/auth/logout');

      if (!isAuthEndpoint) {
        // If already refreshing, queue this request
        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            subscribeToRefresh((success) => {
              if (success) {
                // Retry the original request
                resolve(apiClient(originalRequest));
              } else {
                reject(error);
              }
            });
          });
        }

        isRefreshing = true;

        try {
          const refreshSuccess = await attemptRefresh(apiClient);

          if (refreshSuccess) {
            notifyRefreshSubscribers(true);
            isRefreshing = false;
            // Retry the original request
            return apiClient(originalRequest);
          } else {
            // Refresh failed - session expired
            notifyRefreshSubscribers(false);
            isRefreshing = false;

            if (onSessionExpired) {
              onSessionExpired();
            }

            return Promise.reject(transformError(error));
          }
        } catch {
          notifyRefreshSubscribers(false);
          isRefreshing = false;

          if (onSessionExpired) {
            onSessionExpired();
          }

          return Promise.reject(transformError(error));
        }
      }
    }

    // Transform and reject other errors
    return Promise.reject(transformError(error));
  }
);

// =============================================================================
// Error Transformation
// =============================================================================

/**
 * Transform axios error to consistent ApiError format
 */
const transformError = (error: AxiosError<ApiErrorResponse>): ApiError => {
  // Network error (no response)
  if (!error.response) {
    return {
      code: 'NETWORK_ERROR',
      message: 'Network error. Please check your connection.',
      status: 0,
      originalError: error,
    };
  }

  const { status, data } = error.response;

  // Server returned error response
  if (data?.error) {
    return {
      code: data.error.code || 'UNKNOWN_ERROR',
      message: data.error.message || 'An unexpected error occurred.',
      status,
      details: data.error.details,
      originalError: error,
    };
  }

  // Legacy error format (detail.message)
  const legacyMessage = (data as { detail?: { message?: string } })?.detail?.message;
  if (legacyMessage) {
    return {
      code: 'API_ERROR',
      message: legacyMessage,
      status,
      originalError: error,
    };
  }

  // Fallback error
  return {
    code: 'UNKNOWN_ERROR',
    message: error.message || 'An unexpected error occurred.',
    status,
    originalError: error,
  };
};

// =============================================================================
// Public API
// =============================================================================

/**
 * Set callback for session expiration
 * Called by auth store to handle logout
 */
export const setSessionExpiredCallback = (callback: SessionExpiredCallback | null) => {
  onSessionExpired = callback;
};

/**
 * Check if an error is an ApiError
 */
export const isApiError = (error: unknown): error is ApiError => {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'message' in error &&
    'status' in error
  );
};

/**
 * Get user-friendly error message
 */
export const getErrorMessage = (error: unknown): string => {
  if (isApiError(error)) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred.';
};

export default apiClient;
