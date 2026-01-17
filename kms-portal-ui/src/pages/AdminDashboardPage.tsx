/**
 * Admin Dashboard Page
 * Enterprise-grade AI Agent Governance & Observability Platform
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Users,
  Coins,
  Activity,
  Shield,
  Cpu,
  HeartPulse,
  Database,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Clock,
  BarChart3,
  Loader2,
  Lightbulb,
} from 'lucide-react';
import {
  UserManagementTable,
  UserDetailsModal,
  UserUsageModal,
  UserDeleteConfirmModal,
  PasswordResetModal,
} from '../components/admin';
import type { UserData } from '../components/admin';
import { EnhanceRequestsTab } from '../components/admin/enhance';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts';
import './AdminDashboardPage.css';

// Types
interface ExecutiveDashboard {
  users: {
    total_users: number;
    active_users: number;
    new_users_7d: number;
    new_users_30d: number;
    users_by_role: Record<string, number>;
  };
  tokens: {
    total_tokens_today: number;
    total_tokens_7d: number;
    total_tokens_30d: number;
    estimated_cost_today: number;
    estimated_cost_30d: number;
    top_endpoints: Array<{ endpoint: string; tokens: number }>;
  };
  queries: {
    total_queries_today: number;
    total_queries_7d: number;
    success_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    queries_by_strategy: Record<string, number>;
    queries_by_agent: Record<string, number>;
  };
  system_health: {
    status: 'healthy' | 'degraded' | 'unhealthy';
    components: Record<string, { status: string; latency_ms?: number }>;
    uptime_seconds: number;
  };
  user_trend: Array<{ timestamp: string; value: number }>;
  query_trend: Array<{ timestamp: string; value: number }>;
  token_trend: Array<{ timestamp: string; value: number }>;
}

// Tab configuration
type TabId = 'executive' | 'users' | 'tokens' | 'agents' | 'health' | 'enhance' | 'rag' | 'audit';

interface TabConfig {
  id: TabId;
  labelKey: string;
  icon: React.ReactNode;
}

const TABS: TabConfig[] = [
  { id: 'executive', labelKey: 'Executive', icon: <BarChart3 size={18} /> },
  { id: 'users', labelKey: 'Users', icon: <Users size={18} /> },
  { id: 'tokens', labelKey: 'Tokens', icon: <Coins size={18} /> },
  { id: 'agents', labelKey: 'Agents', icon: <Cpu size={18} /> },
  { id: 'health', labelKey: 'Health', icon: <HeartPulse size={18} /> },
  { id: 'enhance', labelKey: 'Enhance Requests', icon: <Lightbulb size={18} /> },
  { id: 'rag', labelKey: 'RAG', icon: <Database size={18} /> },
  { id: 'audit', labelKey: 'Audit', icon: <Shield size={18} /> },
];

// Chart colors
const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#c4b5fd', '#ddd6fe'];
const STATUS_COLORS = {
  healthy: '#22c55e',
  degraded: '#f59e0b',
  unhealthy: '#ef4444',
};

// KPI Card Component
interface KPICardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
  color?: string;
}

const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendValue,
  color = 'var(--color-primary)',
}) => (
  <div className="admin-kpi-card">
    <div className="admin-kpi-icon" style={{ backgroundColor: `${color}15`, color }}>
      {icon}
    </div>
    <div className="admin-kpi-content">
      <div className="admin-kpi-title">{title}</div>
      <div className="admin-kpi-value">{value}</div>
      {(subtitle || trendValue) && (
        <div className="admin-kpi-footer">
          {subtitle && <span className="admin-kpi-subtitle">{subtitle}</span>}
          {trend && trendValue && (
            <span className={`admin-kpi-trend admin-kpi-trend--${trend}`}>
              {trend === 'up' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {trendValue}
            </span>
          )}
        </div>
      )}
    </div>
  </div>
);

// Health Status Badge
const HealthBadge: React.FC<{ status: string }> = ({ status }) => {
  const statusLower = status.toLowerCase();
  const icon = statusLower === 'healthy' ? <CheckCircle size={14} /> : <AlertTriangle size={14} />;
  return (
    <span className={`admin-health-badge admin-health-badge--${statusLower}`}>
      {icon}
      {status}
    </span>
  );
};

// Format number with K/M suffix
const formatNumber = (num: number): string => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

// Format duration
const formatDuration = (seconds: number): string => {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  if (days > 0) return `${days}d ${hours}h`;
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

// Main Component
export const AdminDashboardPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('executive');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ExecutiveDashboard | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch dashboard data
  const fetchData = async () => {
    try {
      setRefreshing(true);
      const response = await fetch('/api/v1/admin/analytics/executive?days=7', {
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const result = await response.json();
      setData(result.data);
      setError(null);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Loading state
  if (loading) {
    return (
      <div className="admin-dashboard admin-dashboard--loading">
        <Loader2 className="admin-loading-spinner" size={48} />
        <p>Loading dashboard...</p>
      </div>
    );
  }

  // Error state
  if (error && !data) {
    return (
      <div className="admin-dashboard admin-dashboard--error">
        <AlertTriangle size={48} />
        <h2>Error Loading Dashboard</h2>
        <p>{error}</p>
        <button onClick={fetchData} className="admin-retry-btn">
          <RefreshCw size={16} />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="admin-dashboard">
      {/* Header */}
      <header className="admin-dashboard-header">
        <div className="admin-dashboard-title">
          <h1>Admin Dashboard</h1>
          <p className="admin-dashboard-subtitle">AI Agent Governance & Observability</p>
        </div>
        <div className="admin-dashboard-actions">
          <button
            className="admin-refresh-btn"
            onClick={fetchData}
            disabled={refreshing}
          >
            <RefreshCw size={16} className={refreshing ? 'spinning' : ''} />
            Refresh
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="admin-dashboard-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`admin-tab ${activeTab === tab.id ? 'admin-tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon}
            <span>{tab.labelKey}</span>
          </button>
        ))}
      </nav>

      {/* Content */}
      <main className="admin-dashboard-content">
        {activeTab === 'executive' && data && (
          <ExecutiveTab data={data} />
        )}
        {activeTab === 'users' && data && (
          <UsersTab data={data} />
        )}
        {activeTab === 'tokens' && data && (
          <TokensTab data={data} />
        )}
        {activeTab === 'agents' && data && (
          <AgentsTab data={data} />
        )}
        {activeTab === 'health' && data && (
          <HealthTab data={data} />
        )}
        {activeTab === 'enhance' && (
          <EnhanceRequestsTab />
        )}
        {activeTab === 'rag' && (
          <div className="admin-placeholder">
            <Database size={48} />
            <h3>RAG Metrics</h3>
            <p>Coming soon...</p>
          </div>
        )}
        {activeTab === 'audit' && (
          <div className="admin-placeholder">
            <Shield size={48} />
            <h3>Audit Logs</h3>
            <p>Coming soon...</p>
          </div>
        )}
      </main>
    </div>
  );
};

// Executive Tab
const ExecutiveTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const queryTrend = data.query_trend?.map((point) => ({
    date: new Date(point.timestamp).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    queries: point.value,
  })) || [];

  const tokenTrend = data.token_trend?.map((point) => ({
    date: new Date(point.timestamp).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    tokens: Math.round(point.value / 1000),
  })) || [];

  return (
    <div className="admin-tab-content">
      {/* KPI Cards */}
      <section className="admin-kpi-grid">
        <KPICard
          title="Active Users"
          value={data.users.active_users}
          subtitle={`${data.users.new_users_7d} new this week`}
          icon={<Users size={24} />}
          trend="up"
          trendValue={`+${data.users.new_users_7d}`}
          color="#6366f1"
        />
        <KPICard
          title="Queries Today"
          value={formatNumber(data.queries.total_queries_today)}
          subtitle={`${(data.queries.success_rate * 100).toFixed(1)}% success`}
          icon={<Activity size={24} />}
          trend="up"
          trendValue={`${(data.queries.success_rate * 100).toFixed(0)}%`}
          color="#22c55e"
        />
        <KPICard
          title="Tokens Today"
          value={formatNumber(data.tokens.total_tokens_today)}
          subtitle={`$${data.tokens.estimated_cost_today.toFixed(2)} cost`}
          icon={<Coins size={24} />}
          color="#f59e0b"
        />
        <KPICard
          title="System Health"
          value={data.system_health.status.toUpperCase()}
          subtitle={`Uptime: ${formatDuration(data.system_health.uptime_seconds)}`}
          icon={<HeartPulse size={24} />}
          color={STATUS_COLORS[data.system_health.status]}
        />
      </section>

      {/* Charts */}
      <section className="admin-charts-grid">
        <div className="admin-chart-card">
          <h3 className="admin-chart-title">Query Volume (7 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={queryTrend}>
              <defs>
                <linearGradient id="queryGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="date" stroke="var(--color-text-secondary)" fontSize={12} />
              <YAxis stroke="var(--color-text-secondary)" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                }}
              />
              <Area
                type="monotone"
                dataKey="queries"
                stroke="#6366f1"
                fill="url(#queryGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="admin-chart-card">
          <h3 className="admin-chart-title">Token Usage (K)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={tokenTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="date" stroke="var(--color-text-secondary)" fontSize={12} />
              <YAxis stroke="var(--color-text-secondary)" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="tokens" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Metrics Summary */}
      <section className="admin-metrics-summary">
        <div className="admin-metric-box">
          <h4>Latency</h4>
          <div className="admin-metric-value">{data.queries.avg_latency_ms}ms</div>
          <div className="admin-metric-label">avg response time</div>
          <div className="admin-metric-secondary">P95: {data.queries.p95_latency_ms}ms</div>
        </div>
        <div className="admin-metric-box">
          <h4>Cost (30d)</h4>
          <div className="admin-metric-value">${data.tokens.estimated_cost_30d.toFixed(2)}</div>
          <div className="admin-metric-label">estimated</div>
          <div className="admin-metric-secondary">{formatNumber(data.tokens.total_tokens_30d)} tokens</div>
        </div>
        <div className="admin-metric-box">
          <h4>Users (30d)</h4>
          <div className="admin-metric-value">+{data.users.new_users_30d}</div>
          <div className="admin-metric-label">new registrations</div>
          <div className="admin-metric-secondary">{data.users.total_users} total</div>
        </div>
      </section>
    </div>
  );
};

// Users Tab
const UsersTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const [editUser, setEditUser] = useState<UserData | null>(null);
  const [usageUser, setUsageUser] = useState<UserData | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserData | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<UserData | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const roleData = Object.entries(data.users.users_by_role || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const handleEditUser = useCallback((user: UserData) => {
    setEditUser(user);
  }, []);

  const handleViewUsage = useCallback((user: UserData) => {
    setUsageUser(user);
  }, []);

  const handleResetPassword = useCallback((user: UserData) => {
    setResetPasswordUser(user);
  }, []);

  const handleDeleteUser = useCallback((user: UserData) => {
    setDeleteUser(user);
  }, []);

  const handleUserUpdated = useCallback((_updatedUser: UserData) => {
    setEditUser(null);
    setRefreshKey((prev) => prev + 1);
  }, []);

  const handleUserDeleted = useCallback(() => {
    setDeleteUser(null);
    setRefreshKey((prev) => prev + 1);
  }, []);

  return (
    <div className="admin-tab-content">
      {/* KPI Cards */}
      <section className="admin-kpi-grid">
        <KPICard
          title="Total Users"
          value={data.users.total_users}
          icon={<Users size={24} />}
          color="#6366f1"
        />
        <KPICard
          title="Active Users"
          value={data.users.active_users}
          subtitle={`${((data.users.active_users / data.users.total_users) * 100).toFixed(0)}% of total`}
          icon={<CheckCircle size={24} />}
          color="#22c55e"
        />
        <KPICard
          title="New This Week"
          value={data.users.new_users_7d}
          icon={<TrendingUp size={24} />}
          trend="up"
          trendValue={`+${data.users.new_users_7d}`}
          color="#f59e0b"
        />
        <KPICard
          title="New This Month"
          value={data.users.new_users_30d}
          icon={<TrendingUp size={24} />}
          color="#8b5cf6"
        />
      </section>

      {/* User Management Table */}
      <section className="admin-users-section">
        <h3 className="admin-section-title">User Management</h3>
        <UserManagementTable
          key={refreshKey}
          onEditUser={handleEditUser}
          onViewUsage={handleViewUsage}
          onResetPassword={handleResetPassword}
          onDeleteUser={handleDeleteUser}
        />
      </section>

      {/* Charts */}
      <section className="admin-charts-grid">
        <div className="admin-chart-card">
          <h3 className="admin-chart-title">Users by Role</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={roleData}
                cx="50%"
                cy="50%"
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
                label={({ name, percent }: { name: string; percent: number }) => `${name} (${(percent * 100).toFixed(0)}%)`}
              >
                {roleData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="admin-chart-card">
          <h3 className="admin-chart-title">User Registration Trend</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.user_trend?.map((p) => ({
              date: new Date(p.timestamp).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
              users: p.value,
            })) || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="date" stroke="var(--color-text-secondary)" fontSize={12} />
              <YAxis stroke="var(--color-text-secondary)" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                }}
              />
              <Line type="monotone" dataKey="users" stroke="#6366f1" strokeWidth={2} dot={{ fill: '#6366f1' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Modals */}
      {editUser && (
        <UserDetailsModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSave={handleUserUpdated}
        />
      )}
      {usageUser && (
        <UserUsageModal
          user={usageUser}
          onClose={() => setUsageUser(null)}
        />
      )}
      {deleteUser && (
        <UserDeleteConfirmModal
          user={deleteUser}
          onClose={() => setDeleteUser(null)}
          onConfirm={handleUserDeleted}
        />
      )}
      {resetPasswordUser && (
        <PasswordResetModal
          user={resetPasswordUser}
          onClose={() => setResetPasswordUser(null)}
        />
      )}
    </div>
  );
};

// Tokens Tab
const TokensTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const tokenTrend = data.token_trend?.map((point) => ({
    date: new Date(point.timestamp).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    tokens: Math.round(point.value / 1000),
  })) || [];

  return (
    <div className="admin-tab-content">
      <section className="admin-kpi-grid">
        <KPICard
          title="Tokens Today"
          value={formatNumber(data.tokens.total_tokens_today)}
          subtitle={`$${data.tokens.estimated_cost_today.toFixed(2)}`}
          icon={<Coins size={24} />}
          color="#f59e0b"
        />
        <KPICard
          title="Tokens (7 days)"
          value={formatNumber(data.tokens.total_tokens_7d)}
          icon={<Activity size={24} />}
          color="#6366f1"
        />
        <KPICard
          title="Tokens (30 days)"
          value={formatNumber(data.tokens.total_tokens_30d)}
          subtitle={`$${data.tokens.estimated_cost_30d.toFixed(2)}`}
          icon={<TrendingUp size={24} />}
          color="#8b5cf6"
        />
        <KPICard
          title="Cost (30 days)"
          value={`$${data.tokens.estimated_cost_30d.toFixed(2)}`}
          icon={<Coins size={24} />}
          color="#22c55e"
        />
      </section>

      <section className="admin-charts-grid">
        <div className="admin-chart-card admin-chart-card--full">
          <h3 className="admin-chart-title">Daily Token Usage (K)</h3>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={tokenTrend}>
              <defs>
                <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="date" stroke="var(--color-text-secondary)" fontSize={12} />
              <YAxis stroke="var(--color-text-secondary)" fontSize={12} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                }}
              />
              <Area
                type="monotone"
                dataKey="tokens"
                stroke="#f59e0b"
                fill="url(#tokenGradient)"
                strokeWidth={2}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      {data.tokens.top_endpoints && data.tokens.top_endpoints.length > 0 && (
        <section className="admin-table-section">
          <h3 className="admin-section-title">Top Endpoints by Token Usage</h3>
          <table className="admin-table">
            <thead>
              <tr>
                <th>Endpoint</th>
                <th>Tokens</th>
              </tr>
            </thead>
            <tbody>
              {data.tokens.top_endpoints.map((ep, i) => (
                <tr key={i}>
                  <td><code>{ep.endpoint}</code></td>
                  <td>{formatNumber(ep.tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
};

// Agents Tab
const AgentsTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const agentData = Object.entries(data.queries.queries_by_agent || {}).map(([name, value]) => ({
    name,
    value,
  }));

  const strategyData = Object.entries(data.queries.queries_by_strategy || {}).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="admin-tab-content">
      <section className="admin-kpi-grid">
        <KPICard
          title="Total Queries"
          value={formatNumber(data.queries.total_queries_7d)}
          subtitle="Last 7 days"
          icon={<Activity size={24} />}
          color="#6366f1"
        />
        <KPICard
          title="Success Rate"
          value={`${(data.queries.success_rate * 100).toFixed(1)}%`}
          icon={<CheckCircle size={24} />}
          color="#22c55e"
        />
        <KPICard
          title="Avg Latency"
          value={`${data.queries.avg_latency_ms}ms`}
          subtitle={`P95: ${data.queries.p95_latency_ms}ms`}
          icon={<Clock size={24} />}
          color="#f59e0b"
        />
        <KPICard
          title="Agent Types"
          value={Object.keys(data.queries.queries_by_agent || {}).length}
          icon={<Cpu size={24} />}
          color="#8b5cf6"
        />
      </section>

      <section className="admin-charts-grid">
        <div className="admin-chart-card">
          <h3 className="admin-chart-title">Queries by Agent</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={agentData}
                cx="50%"
                cy="50%"
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
                label={({ name, percent }: { name: string; percent: number }) => `${name} (${(percent * 100).toFixed(0)}%)`}
              >
                {agentData.map((_, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="admin-chart-card">
          <h3 className="admin-chart-title">Queries by Strategy</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={strategyData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis type="number" stroke="var(--color-text-secondary)" fontSize={12} />
              <YAxis type="category" dataKey="name" stroke="var(--color-text-secondary)" fontSize={12} width={80} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
};

// Health Tab
const HealthTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const components = Object.entries(data.system_health.components || {});

  return (
    <div className="admin-tab-content">
      <section className="admin-health-overview">
        <div className="admin-health-status-card">
          <div className={`admin-health-status-indicator admin-health-status-indicator--${data.system_health.status}`}>
            {data.system_health.status === 'healthy' ? (
              <CheckCircle size={48} />
            ) : (
              <AlertTriangle size={48} />
            )}
          </div>
          <div className="admin-health-status-info">
            <h2>System Status</h2>
            <HealthBadge status={data.system_health.status} />
            <p>Uptime: {formatDuration(data.system_health.uptime_seconds)}</p>
          </div>
        </div>
      </section>

      {components.length > 0 && (
        <section className="admin-components-grid">
          <h3 className="admin-section-title">Components</h3>
          <div className="admin-component-cards">
            {components.map(([name, info]) => (
              <div key={name} className="admin-component-card">
                <div className="admin-component-header">
                  <span className="admin-component-name">{name}</span>
                  <HealthBadge status={info.status || 'unknown'} />
                </div>
                {info.latency_ms !== undefined && (
                  <div className="admin-component-metric">
                    <Clock size={14} />
                    <span>{info.latency_ms}ms</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

// EnhanceRequestsTab is imported from '../components/admin/enhance'

export default AdminDashboardPage;
