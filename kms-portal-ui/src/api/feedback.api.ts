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

// =============================================================================
// Export default API object
// =============================================================================

export const feedbackApi = {
  submitQuickFeedback,
};

export default feedbackApi;
