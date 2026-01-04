/**
 * IMS Dashboard Component
 * Comprehensive statistics and analytics dashboard
 */

import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import type { TranslateFunction } from '../../../i18n/types';
import api from '../../../services/api';

interface Props {
  t: TranslateFunction;
}

interface ActivityMetrics {
  total_crawls: number;
  total_issues_crawled: number;
  total_attachments: number;
  last_crawl_date: string | null;
  avg_issues_per_crawl: number;
}

interface IssueMetrics {
  total_issues: number;
  open_issues: number;
  closed_issues: number;
  critical_issues: number;
  high_priority_issues: number;
  resolution_rate: number;
}

interface ProjectMetrics {
  project_key: string;
  total_issues: number;
  open_issues: number;
  closed_issues: number;
  critical_issues: number;
  last_updated: string;
}

interface TopReporter {
  reporter: string;
  issue_count: number;
  critical_count: number;
  open_count: number;
}

interface TrendData {
  date: string;
  count: number;
}

interface DashboardData {
  activity_metrics: ActivityMetrics;
  issue_metrics: IssueMetrics;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  top_projects: ProjectMetrics[];
  top_reporters: TopReporter[];
  issue_trend_7days: TrendData[];
  issue_trend_30days: TrendData[];
}

export const IMSDashboard: React.FC<Props> = ({ t }) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trendPeriod, setTrendPeriod] = useState<7 | 30>(7);

  useEffect(() => {
    loadDashboardData();
  }, [trendPeriod]);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await api.get(`/api/v1/ims-dashboard/statistics?trend_days=${trendPeriod}`);
      setData(response.data);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '400px',
        fontSize: '16px',
        color: 'var(--text-secondary)'
      }}>
        ⏳ Loading dashboard...
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{
        padding: '40px',
        textAlign: 'center',
        color: 'var(--text-secondary)'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '16px' }}>📊</div>
        <div>{error || 'No data available'}</div>
      </div>
    );
  }

  const selectedTrend = trendPeriod === 7 ? data.issue_trend_7days : data.issue_trend_30days;
  const maxTrendCount = Math.max(...selectedTrend.map(t => t.count), 1);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: '24px',
      width: '100%'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <h2 style={{ margin: 0, fontSize: '24px', fontWeight: 600 }}>
          📊 Dashboard
        </h2>
        <button
          onClick={() => loadDashboardData()}
          style={{
            padding: '8px 16px',
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '14px'
          }}
        >
          🔄 Refresh
        </button>
      </div>

      {/* Key Metrics Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: '16px'
      }}>
        <MetricCard
          icon="📝"
          label="Total Issues"
          value={data.issue_metrics.total_issues}
          subtitle={`${data.issue_metrics.open_issues} open`}
        />
        <MetricCard
          icon="🚨"
          label="Critical"
          value={data.issue_metrics.critical_issues}
          subtitle={`${data.issue_metrics.high_priority_issues} high priority`}
          color="#dc2626"
        />
        <MetricCard
          icon="✅"
          label="Resolution Rate"
          value={`${data.issue_metrics.resolution_rate}%`}
          subtitle={`${data.issue_metrics.closed_issues} closed`}
          color="#10b981"
        />
        <MetricCard
          icon="🔍"
          label="Total Crawls"
          value={data.activity_metrics.total_crawls}
          subtitle={`${data.activity_metrics.total_issues_crawled} issues`}
        />
        <MetricCard
          icon="📎"
          label="Attachments"
          value={data.activity_metrics.total_attachments}
          subtitle={`Avg ${data.activity_metrics.avg_issues_per_crawl} issues/crawl`}
        />
      </div>

      {/* Charts Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
        gap: '20px'
      }}>
        {/* Status Distribution */}
        <ChartCard title="By Status">
          <BarChart
            data={Object.entries(data.by_status).map(([label, value]) => ({ label, value }))}
            maxValue={Math.max(...Object.values(data.by_status))}
          />
        </ChartCard>

        {/* Priority Distribution */}
        <ChartCard title="By Priority">
          <BarChart
            data={Object.entries(data.by_priority).map(([label, value]) => ({ label, value }))}
            maxValue={Math.max(...Object.values(data.by_priority))}
            colorMap={{
              'CRITICAL': '#dc2626',
              'HIGH': '#f59e0b',
              'MEDIUM': '#3b82f6',
              'LOW': '#10b981'
            }}
          />
        </ChartCard>
      </div>

      {/* Issue Trend */}
      <ChartCard
        title="Issue Creation Trend"
        actions={
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setTrendPeriod(7)}
              style={{
                padding: '6px 12px',
                background: trendPeriod === 7 ? 'var(--accent)' : 'var(--card-bg)',
                color: trendPeriod === 7 ? '#fff' : 'var(--text)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              7 Days
            </button>
            <button
              onClick={() => setTrendPeriod(30)}
              style={{
                padding: '6px 12px',
                background: trendPeriod === 30 ? 'var(--accent)' : 'var(--card-bg)',
                color: trendPeriod === 30 ? '#fff' : 'var(--text)',
                border: '1px solid var(--border)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              30 Days
            </button>
          </div>
        }
      >
        <LineChart data={selectedTrend} maxValue={maxTrendCount} />
      </ChartCard>

      {/* Top Projects and Reporters */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
        gap: '20px'
      }}>
        {/* Top Projects */}
        <ChartCard title="Top Projects">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {data.top_projects.slice(0, 5).map((project, idx) => (
              <div
                key={project.project_key}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px',
                  background: 'var(--input-bg)',
                  borderRadius: '6px'
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>
                    #{idx + 1} {project.project_key}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    {project.open_issues} open • {project.critical_issues} critical
                  </div>
                </div>
                <div style={{
                  fontSize: '20px',
                  fontWeight: 700,
                  color: 'var(--accent)'
                }}>
                  {project.total_issues}
                </div>
              </div>
            ))}
          </div>
        </ChartCard>

        {/* Top Reporters */}
        <ChartCard title="Top Reporters">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {data.top_reporters.slice(0, 5).map((reporter, idx) => (
              <div
                key={reporter.reporter}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '12px',
                  background: 'var(--input-bg)',
                  borderRadius: '6px'
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>
                    #{idx + 1} {reporter.reporter}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    {reporter.open_count} open • {reporter.critical_count} critical
                  </div>
                </div>
                <div style={{
                  fontSize: '20px',
                  fontWeight: 700,
                  color: 'var(--accent)'
                }}>
                  {reporter.issue_count}
                </div>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>
    </div>
  );
};

// Metric Card Component
const MetricCard: React.FC<{
  icon: string;
  label: string;
  value: string | number;
  subtitle: string;
  color?: string;
}> = ({ icon, label, value, subtitle, color }) => (
  <motion.div
    whileHover={{ scale: 1.02 }}
    style={{
      padding: '20px',
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px'
    }}
  >
    <div style={{ fontSize: '32px', marginBottom: '8px' }}>{icon}</div>
    <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
      {label}
    </div>
    <div style={{
      fontSize: '28px',
      fontWeight: 700,
      color: color || 'var(--text)',
      marginBottom: '4px'
    }}>
      {value}
    </div>
    <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
      {subtitle}
    </div>
  </motion.div>
);

// Chart Card Wrapper
const ChartCard: React.FC<{
  title: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}> = ({ title, children, actions }) => (
  <div style={{
    padding: '20px',
    background: 'var(--card-bg)',
    border: '1px solid var(--border)',
    borderRadius: '12px'
  }}>
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '16px'
    }}>
      <h4 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>{title}</h4>
      {actions}
    </div>
    {children}
  </div>
);

// Bar Chart Component
const BarChart: React.FC<{
  data: Array<{ label: string; value: number }>;
  maxValue: number;
  colorMap?: Record<string, string>;
}> = ({ data, maxValue, colorMap }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
    {data.map(({ label, value }) => {
      const percentage = (value / maxValue) * 100;
      const color = colorMap?.[label] || 'var(--accent)';

      return (
        <div key={label}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginBottom: '6px',
            fontSize: '14px'
          }}>
            <span>{label}</span>
            <span style={{ fontWeight: 600 }}>{value}</span>
          </div>
          <div style={{
            width: '100%',
            height: '8px',
            background: 'var(--input-bg)',
            borderRadius: '4px',
            overflow: 'hidden'
          }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${percentage}%` }}
              transition={{ duration: 0.5 }}
              style={{
                height: '100%',
                background: color,
                borderRadius: '4px'
              }}
            />
          </div>
        </div>
      );
    })}
  </div>
);

// Line Chart Component
const LineChart: React.FC<{
  data: TrendData[];
  maxValue: number;
}> = ({ data, maxValue }) => {
  const width = 100; // percentage
  const height = 120;
  const padding = 20;

  const points = data.map((d, i) => {
    const x = (i / (data.length - 1)) * (width - padding * 2) + padding;
    const y = height - ((d.count / maxValue) * (height - padding * 2) + padding);
    return `${x},${y}`;
  }).join(' ');

  return (
    <div style={{ position: 'relative' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{
          width: '100%',
          height: '150px',
          background: 'var(--input-bg)',
          borderRadius: '8px'
        }}
      >
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <line
            key={ratio}
            x1={padding}
            y1={height - (ratio * (height - padding * 2) + padding)}
            x2={width - padding}
            y2={height - (ratio * (height - padding * 2) + padding)}
            stroke="var(--border)"
            strokeWidth="0.5"
          />
        ))}

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="2"
        />

        {/* Points */}
        {data.map((d, i) => {
          const x = (i / (data.length - 1)) * (width - padding * 2) + padding;
          const y = height - ((d.count / maxValue) * (height - padding * 2) + padding);

          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="2"
              fill="var(--accent)"
            />
          );
        })}
      </svg>

      {/* Date labels */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: '8px',
        fontSize: '11px',
        color: 'var(--text-secondary)'
      }}>
        <span>{new Date(data[0].date).toLocaleDateString()}</span>
        <span>{new Date(data[data.length - 1].date).toLocaleDateString()}</span>
      </div>
    </div>
  );
};
