/**
 * Home Page (Dashboard)
 *
 * Main landing page after login with quick access cards and stats
 */

import React from 'react';
import { Link } from 'react-router-dom';
import {
  BookOpen,
  Database,
  Brain,
  FileText,
  Search,
  TrendingUp,
  Users,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';

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
  trend?: string;
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

// Stats configuration
const STATS: Stat[] = [
  {
    id: 'documents',
    icon: <FileText size={20} />,
    value: '1,234',
    labelKey: 'Documents indexed',
    trend: '+12%',
  },
  {
    id: 'queries',
    icon: <Search size={20} />,
    value: '5,678',
    labelKey: 'Queries this month',
    trend: '+23%',
  },
  {
    id: 'users',
    icon: <Users size={20} />,
    value: '89',
    labelKey: 'Active users',
    trend: '+5%',
  },
  {
    id: 'response',
    icon: <Clock size={20} />,
    value: '1.2s',
    labelKey: 'Avg response time',
    trend: '-15%',
  },
];

// Recent activity mock data
const RECENT_ACTIVITY = [
  {
    id: 1,
    type: 'search',
    message: 'Searched for "API documentation"',
    time: '2 minutes ago',
  },
  {
    id: 2,
    type: 'upload',
    message: 'Uploaded "Q4 Report.pdf"',
    time: '15 minutes ago',
  },
  {
    id: 3,
    type: 'mindmap',
    message: 'Created mindmap "Product Architecture"',
    time: '1 hour ago',
  },
  {
    id: 4,
    type: 'crawl',
    message: 'IMS crawl completed (152 documents)',
    time: '3 hours ago',
  },
];

export const HomePage: React.FC = () => {
  const { t } = useTranslation();
  const { user } = useAuthStore();

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
        {STATS.map((stat) => (
          <div key={stat.id} className="home-stat-card">
            <div className="home-stat-icon">{stat.icon}</div>
            <div className="home-stat-content">
              <div className="home-stat-value">{stat.value}</div>
              <div className="home-stat-label">{stat.labelKey}</div>
            </div>
            {stat.trend && (
              <div
                className={`home-stat-trend ${stat.trend.startsWith('+') ? 'positive' : 'negative'}`}
              >
                <TrendingUp size={14} />
                <span>{stat.trend}</span>
              </div>
            )}
          </div>
        ))}
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
          <h2 className="home-section-title">Recent Activity</h2>
          <Link to="/analytics" className="home-activity-link">
            {t('common.viewAll')} <ArrowRight size={14} />
          </Link>
        </div>
        <div className="home-activity-list">
          {RECENT_ACTIVITY.map((activity) => (
            <div key={activity.id} className="home-activity-item">
              <div className="home-activity-dot" />
              <div className="home-activity-content">
                <span className="home-activity-message">{activity.message}</span>
                <span className="home-activity-time">{activity.time}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default HomePage;
