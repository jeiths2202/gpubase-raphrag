/**
 * Home Page (Dashboard)
 *
 * Main landing page after login with quick access cards and stats
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  Database,
  Brain,
  FileText,
  Search,
  TrendingUp,
  TrendingDown,
  Users,
  Clock,
  ArrowRight,
  Loader2,
  MessageSquare,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useSimplePageContext } from '../hooks/usePageContext';
import { useAuthStore } from '../store/authStore';
import { getDashboardData, type DashboardData, type UserActivity } from '../api/dashboard.api';

// Quick action card interface
interface QuickAction {
  id: string;
  path: string;
  icon: React.ReactNode;
  titleKey: string;
  descriptionKey: string;
  color: string;
}

// Stats interface
interface Stat {
  id: string;
  icon: React.ReactNode;
  value: string;
  labelKey: string;
  trend?: number;
  trendDirection?: 'up' | 'down' | 'stable';
}

// Quick actions configuration
const QUICK_ACTIONS: QuickAction[] = [
  {
    id: 'knowledge',
    path: '/knowledge',
    icon: <BookOpen size={24} />,
    titleKey: 'common.nav.knowledge',
    descriptionKey: 'Browse and search documentation',
    color: 'var(--color-primary)',
  },
  {
    id: 'ims',
    path: '/ims',
    icon: <Database size={24} />,
    titleKey: 'common.nav.ims',
    descriptionKey: 'Manage document crawling',
    color: 'var(--color-success)',
  },
  {
    id: 'mindmap',
    path: '/mindmap',
    icon: <Brain size={24} />,
    titleKey: 'common.nav.mindmap',
    descriptionKey: 'Visualize knowledge connections',
    color: 'var(--color-warning)',
  },
  {
    id: 'documents',
    path: '/documents',
    icon: <FileText size={24} />,
    titleKey: 'common.nav.documents',
    descriptionKey: 'Upload and manage files',
    color: 'var(--color-info)',
  },
];

// Format number with commas
const formatNumber = (num: number): string => {
  return num.toLocaleString();
};

// Format trend percentage
const formatTrend = (trend?: number): string | undefined => {
  if (trend === undefined || trend === null) return undefined;
  const sign = trend >= 0 ? '+' : '';
  return `${sign}${Math.round(trend)}%`;
};

export const HomePage: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();

  // State for dashboard data
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [_error, setError] = useState<string | null>(null);

  // Fetch dashboard data
  const fetchDashboardData = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const data = await getDashboardData();
      setDashboardData(data);
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
      setError('Failed to load dashboard data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch data on mount and refresh every 5 minutes
  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  // Register page context for AI awareness
  useSimplePageContext(['dashboard', 'quick-actions', 'stats']);

  // Build stats array from dashboard data
  const stats: Stat[] = dashboardData ? [
    {
      id: 'documents',
      icon: <FileText size={20} />,
      value: formatNumber(dashboardData.stats.documentsIndexed),
      labelKey: 'common.home.stats.documentsIndexed',
      trend: dashboardData.stats.documentsTrend,
      trendDirection: dashboardData.stats.documentsTrend !== undefined
        ? (dashboardData.stats.documentsTrend > 0 ? 'up' : dashboardData.stats.documentsTrend < 0 ? 'down' : 'stable')
        : undefined,
    },
    {
      id: 'queries',
      icon: <Search size={20} />,
      value: formatNumber(dashboardData.stats.queriesThisMonth),
      labelKey: 'common.home.stats.queriesThisMonth',
      trend: dashboardData.stats.queriesTrend,
      trendDirection: dashboardData.stats.queriesTrend !== undefined
        ? (dashboardData.stats.queriesTrend > 0 ? 'up' : dashboardData.stats.queriesTrend < 0 ? 'down' : 'stable')
        : undefined,
    },
    {
      id: 'users',
      icon: <Users size={20} />,
      value: formatNumber(dashboardData.stats.activeUsers),
      labelKey: 'common.home.stats.activeUsers',
      trend: dashboardData.stats.usersTrend,
      trendDirection: dashboardData.stats.usersTrend !== undefined
        ? (dashboardData.stats.usersTrend > 0 ? 'up' : dashboardData.stats.usersTrend < 0 ? 'down' : 'stable')
        : undefined,
    },
    {
      id: 'response',
      icon: <Clock size={20} />,
      value: dashboardData.stats.avgResponseTime,
      labelKey: 'common.home.stats.avgResponseTime',
      trend: dashboardData.stats.responseTrend,
      // For response time, lower is better, so reverse the direction indicator
      trendDirection: dashboardData.stats.responseTrend !== undefined
        ? (dashboardData.stats.responseTrend < 0 ? 'up' : dashboardData.stats.responseTrend > 0 ? 'down' : 'stable')
        : undefined,
    },
  ] : [];

  // Get recent activity from dashboard data
  const recentActivity: UserActivity[] = dashboardData?.recentActivity || [];

  return (
    <div className="home-page">
      {/* Welcome section */}
      <section className="home-welcome">
        <div className="home-welcome-content">
          <h1 className="home-welcome-title">
            Welcome back, <span className="home-welcome-name">{user?.name || 'User'}</span>
          </h1>
          <p className="home-welcome-subtitle">
            Here's what's happening with your knowledge base today.
          </p>
        </div>
        <div className="home-welcome-search">
          <div className="home-search-bar">
            <Search size={20} className="home-search-icon" />
            <input
              type="text"
              className="home-search-input"
              placeholder="Search across all knowledge..."
            />
          </div>
        </div>
      </section>

      {/* Stats section */}
      <section className="home-stats">
        {isLoading ? (
          // Loading skeleton
          Array.from({ length: 4 }).map((_, idx) => (
            <div key={idx} className="home-stat-card home-stat-loading">
              <div className="home-stat-icon">
                <Loader2 size={20} className="animate-spin" />
              </div>
              <div className="home-stat-content">
                <div className="home-stat-value">--</div>
                <div className="home-stat-label">Loading...</div>
              </div>
            </div>
          ))
        ) : (
          stats.map((stat) => (
            <div key={stat.id} className="home-stat-card">
              <div className="home-stat-icon">{stat.icon}</div>
              <div className="home-stat-content">
                <div className="home-stat-value">{stat.value}</div>
                <div className="home-stat-label">{t(stat.labelKey)}</div>
              </div>
              {stat.trend !== undefined && (
                <div
                  className={`home-stat-trend ${stat.trendDirection === 'up' ? 'positive' : stat.trendDirection === 'down' ? 'negative' : ''}`}
                >
                  {stat.trendDirection === 'up' ? (
                    <TrendingUp size={14} />
                  ) : stat.trendDirection === 'down' ? (
                    <TrendingDown size={14} />
                  ) : null}
                  <span>{formatTrend(stat.trend)}</span>
                </div>
              )}
            </div>
          ))
        )}
      </section>

      {/* Quick actions */}
      <section className="home-actions">
        <h2 className="home-section-title">Quick Actions</h2>
        <div className="home-actions-grid">
          {QUICK_ACTIONS.map((action) => (
            <Link
              key={action.id}
              to={action.path}
              className="home-action-card card-interactive"
            >
              <div
                className="home-action-icon"
                style={{ backgroundColor: `${action.color}15`, color: action.color }}
              >
                {action.icon}
              </div>
              <div className="home-action-content">
                <h3 className="home-action-title">{t(action.titleKey)}</h3>
                <p className="home-action-description">{action.descriptionKey}</p>
              </div>
              <ArrowRight size={16} className="home-action-arrow" />
            </Link>
          ))}
        </div>
      </section>

      {/* Recent activity */}
      <section className="home-activity">
        <div className="home-activity-header">
          <h2 className="home-section-title">{t('common.home.recentActivity')}</h2>
          <Link to="/agent" className="home-activity-link">
            {t('common.viewAll')} <ArrowRight size={14} />
          </Link>
        </div>
        <div className="home-activity-list">
          {isLoading ? (
            // Loading skeleton
            Array.from({ length: 4 }).map((_, idx) => (
              <div key={idx} className="home-activity-item home-activity-loading">
                <div className="home-activity-dot" />
                <div className="home-activity-content">
                  <span className="home-activity-message">Loading...</span>
                  <span className="home-activity-time">--</span>
                </div>
              </div>
            ))
          ) : recentActivity.length > 0 ? (
            recentActivity.map((activity) => (
              <Link
                key={activity.id}
                to={activity.type === 'chat' ? `/agent?conversation=${activity.id}` : '/agent'}
                className="home-activity-item home-activity-link-item"
              >
                <div className="home-activity-icon">
                  <MessageSquare size={14} />
                </div>
                <div className="home-activity-content">
                  <span className="home-activity-message">{activity.message}</span>
                  <span className="home-activity-time">{activity.time}</span>
                </div>
              </Link>
            ))
          ) : (
            <div className="home-activity-empty">
              <p>{t('common.home.noRecentActivity')}</p>
              <Link to="/agent" className="home-activity-start">
                {t('common.home.startConversation')} <ArrowRight size={14} />
              </Link>
            </div>
          )}
        </div>
      </section>
    </div>
  );
};

export default HomePage;
