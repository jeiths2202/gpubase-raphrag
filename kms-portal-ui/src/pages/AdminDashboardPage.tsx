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
  Play,
  Trash2,
  Eye,
  Search,
  Bot,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Square,
  List,
  Zap,
  PauseCircle,
  XCircle,
  Settings,
} from 'lucide-react';
import {
  UserManagementTable,
  UserDetailsModal,
  UserUsageModal,
  UserDeleteConfirmModal,
  PasswordResetModal,
} from '../components/admin';
import type { UserData } from '../components/admin';
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

// Enhancement Request Types
interface EnhanceRequest {
  id: string;
  title: string;
  type?: 'feature' | 'bug_fix' | 'improvement' | 'refactor' | 'documentation' | 'security' | 'performance';
  priority?: 'critical' | 'high' | 'medium' | 'low';
  status: 'submitted' | 'analyzing' | 'analyzed' | 'architecture_review' | 'approved' | 'rejected' | 'implementing' | 'code_review' | 'testing' | 'verified' | 'released' | 'closed';
  author_id: string;
  author_name: string;
  created_at: string;
  updated_at: string;
  ai_analyzed: boolean;
}

// Queue Types
interface QueuedTask {
  id: string;
  enhancement_id: string;
  agent_type: 'analyst' | 'architect' | 'coder' | 'qa';
  operation: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  created_at: string;
  started_at?: string;
  completed_at?: string;
  user_id: string;
  user_name: string;
  error_message?: string;
  duration_ms?: number;
  queue_position?: number;
}

interface AgentStatus {
  agent_type: 'analyst' | 'architect' | 'coder' | 'qa';
  is_running: boolean;
  current_task?: QueuedTask;
  total_processed: number;
  total_failed: number;
  last_activity?: string;
}

interface QueueStatus {
  queue: {
    total_queued: number;
    tasks: QueuedTask[];
  };
  agents: Record<string, AgentStatus>;
  running_tasks: QueuedTask[];
  recent_history: QueuedTask[];
}

// Enhance Requests Tab
const EnhanceRequestsTab: React.FC = () => {
  const [requests, setRequests] = useState<EnhanceRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalItems, setTotalItems] = useState(0);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);
  const [stats, setStats] = useState<{
    total: number;
    pending: number;
    analyzed: number;
    implemented: number;
  } | null>(null);

  // Queue monitoring state
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [showQueuePanel, setShowQueuePanel] = useState(true);
  const [stoppingTaskId, setStoppingTaskId] = useState<string | null>(null);
  const [stoppingAgentType, setStoppingAgentType] = useState<string | null>(null);
  const [clearingQueue, setClearingQueue] = useState(false);

  // Fetch enhancement requests
  const fetchRequests = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('limit', '10');
      if (statusFilter) params.append('status', statusFilter);
      if (searchQuery) params.append('search', searchQuery);

      const response = await fetch(`/api/v1/enhancements?${params.toString()}`, {
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to fetch enhancement requests');

      const data = await response.json();
      setRequests(data.data.items || []);
      setTotalPages(data.pagination?.total_pages || 1);
      setTotalItems(data.pagination?.total_items || 0);

      // Fetch stats
      const statsResponse = await fetch('/api/v1/enhancements/dashboard', {
        credentials: 'include',
      });
      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        const byStatus = statsData.data?.by_status || {};
        setStats({
          total: statsData.data?.total_requests || 0,
          pending: (byStatus['submitted'] || 0) + (byStatus['analyzing'] || 0),
          analyzed: byStatus['analyzed'] || 0,
          implemented: statsData.data?.implemented_count || 0,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load requests');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, searchQuery]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  // Execute (analyze) enhancement request
  const handleExecute = async (id: string) => {
    setExecutingId(id);
    try {
      const response = await fetch(`/api/v1/enhancements/${id}/analyze`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to analyze enhancement');

      // Refresh the list
      await fetchRequests();
    } catch (err) {
      console.error('Execute failed:', err);
      alert('Failed to execute enhancement analysis');
    } finally {
      setExecutingId(null);
    }
  };

  // Delete enhancement request
  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      const response = await fetch(`/api/v1/enhancements/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      });

      if (!response.ok) throw new Error('Failed to delete enhancement');

      setShowDeleteConfirm(null);
      await fetchRequests();
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Failed to delete enhancement request');
    } finally {
      setDeletingId(null);
    }
  };

  // Format date
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Status badge colors
  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      submitted: '#6366f1',
      analyzing: '#f59e0b',
      analyzed: '#22c55e',
      architecture_review: '#8b5cf6',
      approved: '#10b981',
      rejected: '#ef4444',
      implementing: '#3b82f6',
      code_review: '#8b5cf6',
      testing: '#f97316',
      verified: '#14b8a6',
      released: '#22c55e',
      closed: '#6b7280',
    };
    return colors[status] || '#6b7280';
  };

  // Priority badge colors
  const getPriorityColor = (priority?: string) => {
    const colors: Record<string, string> = {
      critical: '#ef4444',
      high: '#f97316',
      medium: '#f59e0b',
      low: '#22c55e',
    };
    return priority ? colors[priority] || '#6b7280' : '#6b7280';
  };

  // Type icons
  const getTypeIcon = (type?: string) => {
    const icons: Record<string, string> = {
      feature: '✨',
      bug_fix: '🐛',
      improvement: '📈',
      refactor: '🔧',
      documentation: '📝',
      security: '🔒',
      performance: '⚡',
    };
    return type ? icons[type] || '📋' : '📋';
  };

  // Check if request can be executed (only submitted status)
  const canExecute = (status: string) => status === 'submitted';

  // Fetch queue status
  const fetchQueueStatus = useCallback(async () => {
    setQueueLoading(true);
    try {
      const response = await fetch('/api/v1/enhancements/queue/status', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        setQueueStatus(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch queue status:', err);
    } finally {
      setQueueLoading(false);
    }
  }, []);

  // Auto-refresh queue status
  useEffect(() => {
    fetchQueueStatus();
    const interval = setInterval(fetchQueueStatus, 5000); // Refresh every 5 seconds
    return () => clearInterval(interval);
  }, [fetchQueueStatus]);

  // Force stop a task
  const handleForceStopTask = async (taskId: string) => {
    setStoppingTaskId(taskId);
    try {
      const response = await fetch(`/api/v1/enhancements/queue/force-stop/${taskId}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to stop task');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Force stop failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to stop task');
    } finally {
      setStoppingTaskId(null);
    }
  };

  // Force stop an agent
  const handleForceStopAgent = async (agentType: string) => {
    setStoppingAgentType(agentType);
    try {
      const response = await fetch(`/api/v1/enhancements/queue/force-stop-agent/${agentType}`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to stop agent');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Force stop agent failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to stop agent');
    } finally {
      setStoppingAgentType(null);
    }
  };

  // Clear the queue
  const handleClearQueue = async () => {
    if (!confirm('Are you sure you want to clear all queued tasks? This cannot be undone.')) {
      return;
    }
    setClearingQueue(true);
    try {
      const response = await fetch('/api/v1/enhancements/queue/clear', {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to clear queue');
      }
      await fetchQueueStatus();
    } catch (err) {
      console.error('Clear queue failed:', err);
      alert(err instanceof Error ? err.message : 'Failed to clear queue');
    } finally {
      setClearingQueue(false);
    }
  };

  // Format duration in ms to readable string
  const formatDurationMs = (ms?: number) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${(ms / 60000).toFixed(1)}m`;
  };

  // Get agent display name
  const getAgentDisplayName = (agentType: string) => {
    const names: Record<string, string> = {
      analyst: 'Analyst Agent',
      architect: 'Architect Agent',
      coder: 'Coder Agent',
      qa: 'QA Agent',
    };
    return names[agentType] || agentType;
  };

  // Get agent icon
  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case 'analyst': return <Search size={16} />;
      case 'architect': return <Settings size={16} />;
      case 'coder': return <Cpu size={16} />;
      case 'qa': return <CheckCircle size={16} />;
      default: return <Bot size={16} />;
    }
  };

  if (loading && requests.length === 0) {
    return (
      <div className="admin-tab-content">
        <div className="admin-loading">
          <Loader2 size={24} className="spinning" />
          <span>Loading enhancement requests...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="admin-tab-content">
      {/* Stats Cards */}
      {stats && (
        <section className="admin-kpi-grid">
          <KPICard
            title="Total Requests"
            value={stats.total}
            icon={<Lightbulb size={24} />}
            color="#6366f1"
          />
          <KPICard
            title="Pending Analysis"
            value={stats.pending}
            subtitle="Waiting for AI"
            icon={<Clock size={24} />}
            color="#f59e0b"
          />
          <KPICard
            title="Analyzed"
            value={stats.analyzed}
            subtitle="AI processed"
            icon={<Bot size={24} />}
            color="#22c55e"
          />
          <KPICard
            title="Implemented"
            value={stats.implemented}
            subtitle="Completed"
            icon={<CheckCircle size={24} />}
            color="#10b981"
          />
        </section>
      )}

      {/* Request Counter */}
      <section className="admin-request-counter-section">
        <div className="admin-request-counter">
          <div className="admin-request-counter-icon">
            <Activity size={32} />
          </div>
          <div className="admin-request-counter-info">
            <span className="admin-request-counter-label">Request Counter</span>
            <span className="admin-request-counter-value">
              {(queueStatus?.running_tasks.length || 0) + (queueStatus?.queue.total_queued || 0)}
            </span>
            <span className="admin-request-counter-detail">
              <span className="counter-running">
                <Zap size={14} />
                {queueStatus?.running_tasks.length || 0} Running
              </span>
              <span className="counter-queued">
                <List size={14} />
                {queueStatus?.queue.total_queued || 0} Queued
              </span>
            </span>
          </div>
          <div className="admin-request-counter-indicator">
            {(queueStatus?.running_tasks.length || 0) > 0 ? (
              <span className="indicator-active">
                <Loader2 size={20} className="spinning" />
                Processing
              </span>
            ) : (
              <span className="indicator-idle">
                <CheckCircle size={20} />
                Idle
              </span>
            )}
          </div>
        </div>
      </section>

      {/* Agent Queue Monitoring Panel */}
      <section className="admin-queue-monitoring">
        <div className="admin-queue-header">
          <h3 className="admin-section-title">
            <Cpu size={20} />
            Agent Queue Monitor
          </h3>
          <div className="admin-queue-actions">
            <button
              className="admin-btn admin-btn--secondary admin-btn--sm"
              onClick={() => setShowQueuePanel(!showQueuePanel)}
            >
              {showQueuePanel ? 'Hide' : 'Show'} Details
            </button>
            <button
              className={`admin-btn admin-btn--sm ${queueLoading ? 'admin-btn--loading' : ''}`}
              onClick={fetchQueueStatus}
              disabled={queueLoading}
            >
              <RefreshCw size={14} className={queueLoading ? 'spinning' : ''} />
              Refresh
            </button>
          </div>
        </div>

        {/* Agent Status Cards */}
        <div className="admin-agent-status-grid">
          {queueStatus && Object.entries(queueStatus.agents).map(([agentType, status]) => (
            <div
              key={agentType}
              className={`admin-agent-card ${status.is_running ? 'admin-agent-card--running' : 'admin-agent-card--idle'}`}
            >
              <div className="admin-agent-card-header">
                <div className="admin-agent-icon">
                  {getAgentIcon(agentType)}
                </div>
                <div className="admin-agent-info">
                  <span className="admin-agent-name">{getAgentDisplayName(agentType)}</span>
                  <span className={`admin-agent-status-badge ${status.is_running ? 'running' : 'idle'}`}>
                    {status.is_running ? (
                      <>
                        <Zap size={12} />
                        Running
                      </>
                    ) : (
                      <>
                        <PauseCircle size={12} />
                        Idle
                      </>
                    )}
                  </span>
                </div>
                {status.is_running && (
                  <button
                    className="admin-btn admin-btn--danger admin-btn--sm"
                    onClick={() => handleForceStopAgent(agentType)}
                    disabled={stoppingAgentType === agentType}
                    title="Force Stop Agent"
                  >
                    {stoppingAgentType === agentType ? (
                      <Loader2 size={14} className="spinning" />
                    ) : (
                      <Square size={14} />
                    )}
                  </button>
                )}
              </div>
              {status.is_running && status.current_task && (
                <div className="admin-agent-task-info">
                  <span className="admin-agent-task-op">
                    {status.current_task.operation}
                  </span>
                  <span className="admin-agent-task-duration">
                    {formatDurationMs(status.current_task.duration_ms)}
                  </span>
                </div>
              )}
              <div className="admin-agent-stats">
                <span>Processed: {status.total_processed}</span>
                <span>Failed: {status.total_failed}</span>
              </div>
            </div>
          ))}
        </div>

        {showQueuePanel && (
          <>
            {/* Running Tasks */}
            {queueStatus && queueStatus.running_tasks.length > 0 && (
              <div className="admin-queue-section">
                <div className="admin-queue-section-header">
                  <h4>
                    <Zap size={16} />
                    Running Tasks ({queueStatus.running_tasks.length})
                  </h4>
                </div>
                <div className="admin-queue-tasks">
                  {queueStatus.running_tasks.map((task) => (
                    <div key={task.id} className="admin-queue-task admin-queue-task--running">
                      <div className="admin-queue-task-icon">
                        {getAgentIcon(task.agent_type)}
                      </div>
                      <div className="admin-queue-task-info">
                        <span className="admin-queue-task-op">{task.operation}</span>
                        <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
                        <span className="admin-queue-task-id">Enhancement: {task.enhancement_id.slice(0, 8)}...</span>
                      </div>
                      <div className="admin-queue-task-duration">
                        {formatDurationMs(task.duration_ms)}
                      </div>
                      <button
                        className="admin-btn admin-btn--danger admin-btn--sm"
                        onClick={() => handleForceStopTask(task.id)}
                        disabled={stoppingTaskId === task.id}
                        title="Force Stop Task"
                      >
                        {stoppingTaskId === task.id ? (
                          <Loader2 size={14} className="spinning" />
                        ) : (
                          <XCircle size={14} />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Queued Tasks */}
            <div className="admin-queue-section">
              <div className="admin-queue-section-header">
                <h4>
                  <List size={16} />
                  Queued Tasks ({queueStatus?.queue.total_queued || 0})
                </h4>
                {queueStatus && queueStatus.queue.total_queued > 0 && (
                  <button
                    className="admin-btn admin-btn--danger admin-btn--sm"
                    onClick={handleClearQueue}
                    disabled={clearingQueue}
                    title="Clear All Queued Tasks"
                  >
                    {clearingQueue ? (
                      <Loader2 size={14} className="spinning" />
                    ) : (
                      <>
                        <Trash2 size={14} />
                        Clear Queue
                      </>
                    )}
                  </button>
                )}
              </div>
              {queueStatus && queueStatus.queue.tasks.length > 0 ? (
                <div className="admin-queue-tasks">
                  {queueStatus.queue.tasks.map((task, index) => (
                    <div key={task.id} className="admin-queue-task admin-queue-task--queued">
                      <div className="admin-queue-task-position">#{index + 1}</div>
                      <div className="admin-queue-task-icon">
                        {getAgentIcon(task.agent_type)}
                      </div>
                      <div className="admin-queue-task-info">
                        <span className="admin-queue-task-op">{task.operation}</span>
                        <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
                        <span className="admin-queue-task-id">Enhancement: {task.enhancement_id.slice(0, 8)}...</span>
                      </div>
                      <div className="admin-queue-task-user">
                        by {task.user_name}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="admin-queue-empty">
                  <CheckCircle size={24} />
                  <span>No tasks in queue</span>
                </div>
              )}
            </div>

            {/* Recent History */}
            {queueStatus && queueStatus.recent_history.length > 0 && (
              <div className="admin-queue-section">
                <div className="admin-queue-section-header">
                  <h4>
                    <Clock size={16} />
                    Recent History
                  </h4>
                </div>
                <div className="admin-queue-tasks">
                  {queueStatus.recent_history.slice(0, 5).map((task) => (
                    <div
                      key={task.id}
                      className={`admin-queue-task admin-queue-task--${task.status}`}
                    >
                      <div className="admin-queue-task-icon">
                        {task.status === 'completed' ? (
                          <CheckCircle size={16} className="text-success" />
                        ) : task.status === 'failed' ? (
                          <XCircle size={16} className="text-danger" />
                        ) : task.status === 'cancelled' ? (
                          <Square size={16} className="text-warning" />
                        ) : (
                          getAgentIcon(task.agent_type)
                        )}
                      </div>
                      <div className="admin-queue-task-info">
                        <span className="admin-queue-task-op">{task.operation}</span>
                        <span className="admin-queue-task-agent">{getAgentDisplayName(task.agent_type)}</span>
                      </div>
                      <div className="admin-queue-task-status">
                        <span className={`admin-queue-status-badge admin-queue-status-badge--${task.status}`}>
                          {task.status}
                        </span>
                      </div>
                      <div className="admin-queue-task-duration">
                        {formatDurationMs(task.duration_ms)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </section>

      {/* Filters */}
      <section className="admin-filters-section">
        <div className="admin-search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search requests..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="admin-filter-select"
        >
          <option value="">All Status</option>
          <option value="submitted">Submitted</option>
          <option value="analyzing">Analyzing</option>
          <option value="analyzed">Analyzed</option>
          <option value="approved">Approved</option>
          <option value="implementing">Implementing</option>
          <option value="verified">Verified</option>
          <option value="released">Released</option>
          <option value="closed">Closed</option>
        </select>
        <button className="admin-refresh-btn" onClick={fetchRequests}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </section>

      {/* Error State */}
      {error && (
        <div className="admin-error-message">
          <AlertTriangle size={20} />
          <span>{error}</span>
        </div>
      )}

      {/* Table */}
      <section className="admin-table-section">
        <div className="admin-table-scroll-wrapper">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Author</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.length === 0 ? (
                <tr>
                  <td colSpan={7} className="admin-table-empty">
                    <Lightbulb size={32} />
                    <p>No enhancement requests found</p>
                  </td>
                </tr>
              ) : (
                requests.map((req) => (
                  <tr key={req.id}>
                    <td className="admin-table-title">
                      <span className="enhance-type-icon">{getTypeIcon(req.type)}</span>
                      <span className="enhance-title-text">{req.title}</span>
                      {req.ai_analyzed && (
                        <span className="enhance-ai-badge">
                          <Bot size={12} />
                          AI
                        </span>
                      )}
                    </td>
                    <td>
                      {req.type ? (
                        <span className="enhance-type-badge">
                          {req.type.replace('_', ' ')}
                        </span>
                      ) : (
                        <span className="enhance-type-badge enhance-type-badge--none">-</span>
                      )}
                    </td>
                    <td>
                      {req.priority ? (
                        <span
                          className="enhance-priority-badge"
                          style={{ backgroundColor: `${getPriorityColor(req.priority)}20`, color: getPriorityColor(req.priority) }}
                        >
                          {req.priority}
                        </span>
                      ) : (
                        <span className="enhance-priority-badge enhance-priority-badge--none">-</span>
                      )}
                    </td>
                    <td>
                      <span
                        className="enhance-status-badge"
                        style={{ backgroundColor: `${getStatusColor(req.status)}20`, color: getStatusColor(req.status) }}
                      >
                        {req.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>{req.author_name}</td>
                    <td className="admin-table-date">{formatDate(req.created_at)}</td>
                    <td className="admin-table-actions">
                      <button
                        className="admin-action-btn admin-action-btn--view"
                        onClick={() => window.open(`/improvements/${req.id}`, '_blank')}
                        title="View Details"
                      >
                        <Eye size={16} />
                      </button>
                      {canExecute(req.status) && (
                        <button
                          className="admin-action-btn admin-action-btn--execute"
                          onClick={() => handleExecute(req.id)}
                          disabled={executingId === req.id}
                          title="Execute AI Analysis"
                        >
                          {executingId === req.id ? (
                            <Loader2 size={16} className="spinning" />
                          ) : (
                            <Play size={16} />
                          )}
                        </button>
                      )}
                      <button
                        className="admin-action-btn admin-action-btn--delete"
                        onClick={() => setShowDeleteConfirm(req.id)}
                        title="Delete Request"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Enhanced Pagination */}
      {totalPages >= 1 && (
        <div className="admin-pagination-enhanced">
          <div className="admin-pagination-summary">
            Showing {requests.length > 0 ? (page - 1) * 10 + 1 : 0} - {Math.min(page * 10, totalItems)} of {totalItems} items
          </div>
          <div className="admin-pagination-controls">
            <button
              className="admin-pagination-nav-btn"
              disabled={page === 1}
              onClick={() => setPage(1)}
              title="First page"
            >
              <ChevronsLeft size={16} />
            </button>
            <button
              className="admin-pagination-nav-btn"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              title="Previous page"
            >
              <ChevronLeft size={16} />
            </button>

            {/* Page numbers */}
            {(() => {
              const pages: (number | 'ellipsis')[] = [];
              const maxVisiblePages = 5;

              if (totalPages <= maxVisiblePages) {
                for (let i = 1; i <= totalPages; i++) pages.push(i);
              } else {
                pages.push(1);

                if (page > 3) pages.push('ellipsis');

                const start = Math.max(2, page - 1);
                const end = Math.min(totalPages - 1, page + 1);

                for (let i = start; i <= end; i++) {
                  if (!pages.includes(i)) pages.push(i);
                }

                if (page < totalPages - 2) pages.push('ellipsis');

                if (!pages.includes(totalPages)) pages.push(totalPages);
              }

              return pages.map((p, idx) =>
                p === 'ellipsis' ? (
                  <span key={`ellipsis-${idx}`} className="admin-pagination-ellipsis">...</span>
                ) : (
                  <button
                    key={p}
                    className={`admin-pagination-page-btn ${page === p ? 'active' : ''}`}
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </button>
                )
              );
            })()}

            <button
              className="admin-pagination-nav-btn"
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
              title="Next page"
            >
              <ChevronRight size={16} />
            </button>
            <button
              className="admin-pagination-nav-btn"
              disabled={page === totalPages}
              onClick={() => setPage(totalPages)}
              title="Last page"
            >
              <ChevronsRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className="admin-modal-overlay" onClick={() => setShowDeleteConfirm(null)}>
          <div className="admin-modal" onClick={(e) => e.stopPropagation()}>
            <div className="admin-modal-header">
              <AlertTriangle size={24} color="#ef4444" />
              <h3>Delete Enhancement Request</h3>
            </div>
            <div className="admin-modal-body">
              <p>Are you sure you want to delete this enhancement request?</p>
              <p className="admin-modal-warning">This action cannot be undone.</p>
            </div>
            <div className="admin-modal-footer">
              <button
                className="admin-btn admin-btn--secondary"
                onClick={() => setShowDeleteConfirm(null)}
              >
                Cancel
              </button>
              <button
                className="admin-btn admin-btn--danger"
                onClick={() => handleDelete(showDeleteConfirm)}
                disabled={deletingId === showDeleteConfirm}
              >
                {deletingId === showDeleteConfirm ? (
                  <>
                    <Loader2 size={16} className="spinning" />
                    Deleting...
                  </>
                ) : (
                  'Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminDashboardPage;
