/**
 * Dashboard API Service
 *
 * API client for fetching dashboard statistics and analytics.
 */

import apiClient from './client';

// =============================================================================
// Types
// =============================================================================

/**
 * Dashboard summary statistics
 */
export interface DashboardSummary {
  generated_at: string;
  period_start: string;
  period_end: string;
  total_queries: number;
  total_users: number;
  avg_response_time_ms: number;
  avg_quality_score: number;
  satisfaction_rate: number;
  error_rate: number;
  queries_trend: 'up' | 'down' | 'stable';
  queries_change_percent: number;
  quality_trend: 'up' | 'down' | 'stable';
  quality_change_percent: number;
  active_alerts: Array<{ type: string; message: string }>;
  top_issues: string[];
  top_queries: Array<{
    query: string;
    count: number;
    avg_response_time_ms: number;
  }>;
}

/**
 * Content analytics for document statistics
 */
export interface ContentAnalytics {
  period_start: string;
  period_end: string;
  total_documents: number;
  total_chunks: number;
  documents_cited: number;
  avg_citations_per_doc: number;
  overall_helpfulness: number;
}

/**
 * User activity item for recent activity
 */
export interface UserActivity {
  id: string;
  type: 'chat' | 'search' | 'document' | 'ims';
  message: string;
  time: string;
  timestamp: string;
}

/**
 * Combined dashboard data
 */
export interface DashboardData {
  stats: {
    documentsIndexed: number;
    queriesThisMonth: number;
    activeUsers: number;
    avgResponseTime: string;
    documentsTrend?: number;
    queriesTrend?: number;
    usersTrend?: number;
    responseTrend?: number;
  };
  recentActivity: UserActivity[];
}

// =============================================================================
// API Response Types
// =============================================================================

interface SuccessResponse<T> {
  data: T;
  meta: {
    request_id: string;
  };
}

// =============================================================================
// API Functions
// =============================================================================

/**
 * Calculate date range from days
 */
function getDateRange(days: number): { start_date: string; end_date: string } {
  const end_date = new Date();
  const start_date = new Date();
  start_date.setDate(start_date.getDate() - days);
  return {
    start_date: start_date.toISOString(),
    end_date: end_date.toISOString(),
  };
}

/**
 * Get dashboard summary statistics
 */
export async function getDashboardSummary(days: number = 30): Promise<DashboardSummary> {
  const { start_date, end_date } = getDateRange(days);
  const response = await apiClient.get<SuccessResponse<DashboardSummary>>(
    '/analytics/summary',
    { params: { start_date, end_date } }
  );
  return response.data.data;
}

/**
 * Get content/document analytics
 */
export async function getContentAnalytics(days: number = 30): Promise<ContentAnalytics> {
  const { start_date, end_date } = getDateRange(days);
  const response = await apiClient.get<SuccessResponse<ContentAnalytics>>(
    '/analytics/content',
    { params: { start_date, end_date } }
  );
  return response.data.data;
}

/**
 * Get usage analytics for active users
 */
export async function getUsageAnalytics(days: number = 30): Promise<{
  total_users: number;
  avg_queries_per_user: number;
}> {
  const { start_date, end_date } = getDateRange(days);
  const response = await apiClient.get<SuccessResponse<{
    total_users: number;
    avg_queries_per_user: number;
  }>>('/analytics/usage/users', { params: { start_date, end_date, days } });
  return response.data.data;
}

/**
 * Format response time for display
 */
function formatResponseTime(ms: number): string {
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Format relative time for display
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  return date.toLocaleDateString();
}

/**
 * Home dashboard stats response
 */
interface HomeDashboardStatsResponse {
  documents_indexed: number;
  queries_this_month: number;
  active_users: number;
  avg_response_time_ms: number;
  documents_trend?: number;
  queries_trend?: number;
  users_trend?: number;
  response_trend?: number;
}

/**
 * Get home dashboard stats from simple endpoint
 */
async function getHomeDashboardStats(): Promise<HomeDashboardStatsResponse | null> {
  try {
    const response = await apiClient.get<SuccessResponse<HomeDashboardStatsResponse>>(
      '/stats/home-dashboard'
    );
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch home dashboard stats:', error);
    return null;
  }
}

/**
 * Get combined dashboard data
 * Fetches all necessary data for the home page dashboard
 */
export async function getDashboardData(): Promise<DashboardData> {
  try {
    // Fetch data in parallel - use simple home-dashboard endpoint
    const [homeStatsResult, conversationsResult] = await Promise.allSettled([
      getHomeDashboardStats(),
      apiClient.get('/conversations', { params: { limit: 5, include_archived: false } }),
    ]);

    // Extract successful results with fallbacks
    const homeStats = homeStatsResult.status === 'fulfilled' ? homeStatsResult.value : null;
    const conversationsData = conversationsResult.status === 'fulfilled'
      ? conversationsResult.value.data?.data?.conversations || []
      : [];

    // Build stats object from home dashboard stats
    const stats = {
      documentsIndexed: homeStats?.documents_indexed || 0,
      queriesThisMonth: homeStats?.queries_this_month || 0,
      activeUsers: homeStats?.active_users || 0,
      avgResponseTime: formatResponseTime(homeStats?.avg_response_time_ms || 0),
      documentsTrend: homeStats?.documents_trend,
      queriesTrend: homeStats?.queries_trend,
      usersTrend: homeStats?.users_trend,
      responseTrend: homeStats?.response_trend,
    };

    // Build recent activity from conversations
    const recentActivity: UserActivity[] = conversationsData.map((conv: {
      id: string;
      title?: string;
      first_message_preview?: string;
      updated_at: string;
      agent_type?: string;
    }) => ({
      id: conv.id,
      type: 'chat' as const,
      message: conv.title || conv.first_message_preview || 'New conversation',
      time: formatRelativeTime(conv.updated_at),
      timestamp: conv.updated_at,
    }));

    return { stats, recentActivity };
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error);
    // Return empty data on error
    return {
      stats: {
        documentsIndexed: 0,
        queriesThisMonth: 0,
        activeUsers: 0,
        avgResponseTime: '0ms',
      },
      recentActivity: [],
    };
  }
}

// =============================================================================
// Exports
// =============================================================================

export const dashboardApi = {
  getSummary: getDashboardSummary,
  getContent: getContentAnalytics,
  getUsage: getUsageAnalytics,
  getData: getDashboardData,
};

export default dashboardApi;
