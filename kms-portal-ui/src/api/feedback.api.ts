/**
 * User Feedback API Client
 *
 * API client for submitting user feedback (thumbs up/down) on chat messages.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Quick feedback request (thumbs up/down)
 */
export interface QuickFeedbackRequest {
  message_id: string;
  feedback_type: 'thumbs_up' | 'thumbs_down';
  query?: string;      // User's question
  answer?: string;     // Assistant's response
  conversation_id?: string;
}

/**
 * Feedback response from API
 */
export interface FeedbackResponse {
  status: 'success' | 'error';
  feedback_id?: string;
  message?: string;
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Submit quick feedback (thumbs up/down) for a message
 */
export const submitQuickFeedback = async (
  request: QuickFeedbackRequest
): Promise<FeedbackResponse> => {
  const response = await apiClient.post<FeedbackResponse>('/feedback/quick', request);
  return response.data;
};

/**
 * Cancel/delete feedback for a message
 */
export const cancelFeedback = async (messageId: string): Promise<{ success: boolean }> => {
  const response = await apiClient.delete<{ success: boolean }>(`/feedback/cancel/${messageId}`);
  return response.data;
};

/**
 * Get user's feedback for a message
 */
export const getUserFeedback = async (messageId: string): Promise<{ feedback_type: string | null }> => {
  const response = await apiClient.get<{ feedback_type: string | null }>(`/feedback/message/${messageId}/user-feedback`);
  return response.data;
};

// =============================================================================
// Export default API object
// =============================================================================

export const feedbackApi = {
  submitQuickFeedback,
  cancelFeedback,
  getUserFeedback,
};

export default feedbackApi;
