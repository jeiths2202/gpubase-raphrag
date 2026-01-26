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
  Brain,
  Thermometer,
  Zap,
  HardDrive,
  Server,
  Search,
  ThumbsUp,
  ThumbsDown,
  FileText,
  Target,
  Gauge,
  Filter,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Info,
  XCircle,
  ShieldAlert,
  User,
  Settings,
  Eye,
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
import { LearningManagementTab } from '../components/admin/learning';
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

// GPU Status Types
interface GpuInfo {
  index: number;
  name: string;
  memory_used: number;
  memory_total: number;
  memory_percent: number;
  utilization: number;
  temperature: number;
  power_draw: number;
  power_limit: number;
}

interface GpuStatus {
  available: boolean;
  gpu_count: number;
  gpus: GpuInfo[];
  error?: string;
}

// GPU Detail Types
interface GpuDetailInfo extends GpuInfo {
  uuid: string;
  memory_free: number;
  utilization_gpu: number;
  utilization_memory: number;
  pstate: string;
  clock_sm: number;
  clock_mem: number;
  driver_version: string;
  cuda_version: string;
}

interface GpuProcess {
  pid: number;
  name: string;
  memory_mb: number;
  user: string;
  runtime: string;
  command: string;
}

interface GpuAssignedService {
  name: string;
  port: number | null;
  model: string | null;
  container: string | null;
}

interface GpuDetailResponse {
  available: boolean;
  gpu?: GpuDetailInfo;
  processes?: GpuProcess[];
  assigned_service?: GpuAssignedService;
  process_count?: number;
  error?: string;
}

// RAG Metrics Types
interface RAGStrategyMetrics {
  strategy: string;
  total_queries: number;
  success_rate: number;
  avg_retrieval_time_ms: number;
  avg_generation_time_ms: number;
  avg_result_count: number;
  avg_similarity_score: number;
  avg_confidence_score: number;
}

interface RAGQualityMetrics {
  avg_user_rating: number | null;
  thumbs_up_count: number;
  thumbs_down_count: number;
  satisfaction_rate: number | null;
  queries_with_sources_pct: number;
}

interface RAGMetricsData {
  total_queries: number;
  overall_success_rate: number;
  strategies: RAGStrategyMetrics[];
  quality: RAGQualityMetrics;
  trend: Array<{ date: string; queries: number; success_rate: number }>;
  top_knowledge_sources: Array<{ source: string; query_count: number; avg_score: number }>;
}

// Audit Types
type AuditCategory = 'USER_MANAGEMENT' | 'CONTENT' | 'SYSTEM' | 'SECURITY' | 'GOVERNANCE' | 'AGENT';
type AuditSeverity = 'info' | 'warning' | 'error' | 'critical';

interface AuditLogEntry {
  id: string;
  timestamp: string;
  user_id: string;
  user_email: string;
  user_role: string;
  action: string;
  action_category: AuditCategory;
  severity: AuditSeverity;
  resource_type: string;
  resource_id?: string;
  resource_name?: string;
  ip_address?: string;
  success: boolean;
  error_message?: string;
  changes?: Record<string, unknown>;
}

interface AuditLogsResponse {
  entries: AuditLogEntry[];
  total: number;
  page: number;
  limit: number;
  has_more: boolean;
}

interface AuditStats {
  total_events: number;
  events_by_category: Record<string, number>;
  events_by_severity: Record<string, number>;
  events_by_user: Array<{ user_id: string; count: number }>;
  recent_security_events: AuditLogEntry[];
}

// Tab configuration
type TabId = 'executive' | 'users' | 'tokens' | 'agents' | 'health' | 'enhance' | 'learning' | 'rag' | 'audit';

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
  { id: 'learning', labelKey: 'Learning', icon: <Brain size={18} /> },
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
        {activeTab === 'learning' && (
          <LearningManagementTab />
        )}
        {activeTab === 'rag' && (
          <RAGTab />
        )}
        {activeTab === 'audit' && (
          <AuditTab />
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

// GPU Detail Modal Component
const GpuDetailModal: React.FC<{
  gpuIndex: number;
  onClose: () => void;
}> = ({ gpuIndex, onClose }) => {
  const [detail, setDetail] = useState<GpuDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        setLoading(true);
        const response = await fetch(`/api/v1/verified-knowledge/monitor/gpu/${gpuIndex}`, {
          credentials: 'include',
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        setDetail(result);
      } catch (err) {
        console.error('Failed to fetch GPU detail:', err);
        setDetail({ available: false, error: 'Failed to load GPU details' });
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
    // Auto-refresh every 5 seconds
    const interval = setInterval(fetchDetail, 5000);
    return () => clearInterval(interval);
  }, [gpuIndex]);

  // Get utilization color
  const getUtilColor = (percent: number): string => {
    if (percent >= 90) return '#ef4444';
    if (percent >= 70) return '#f59e0b';
    return '#22c55e';
  };

  // Get temperature color
  const getTempColor = (temp: number): string => {
    if (temp >= 80) return '#ef4444';
    if (temp >= 65) return '#f59e0b';
    return '#22c55e';
  };

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div className="admin-gpu-modal" onClick={(e) => e.stopPropagation()}>
        <div className="admin-gpu-modal-header">
          <h2>
            <Cpu size={24} />
            GPU {gpuIndex} Detail
          </h2>
          <button className="admin-modal-close" onClick={onClose}>
            <XCircle size={20} />
          </button>
        </div>

        {loading && !detail && (
          <div className="admin-gpu-modal-loading">
            <Loader2 className="spinning" size={32} />
            <span>Loading GPU details...</span>
          </div>
        )}

        {detail && !detail.available && (
          <div className="admin-gpu-modal-error">
            <AlertTriangle size={32} />
            <span>{detail.error || 'GPU information unavailable'}</span>
          </div>
        )}

        {detail && detail.available && detail.gpu && (
          <div className="admin-gpu-modal-content">
            {/* Assigned Service */}
            {detail.assigned_service && (
              <section className="admin-gpu-detail-section">
                <h3>
                  <Server size={18} />
                  Assigned Service
                </h3>
                <div className="admin-gpu-service-info">
                  <div className="admin-gpu-service-name">
                    {detail.assigned_service.name}
                  </div>
                  {detail.assigned_service.port && (
                    <div className="admin-gpu-service-detail">
                      <span className="label">Port:</span>
                      <span className="value">{detail.assigned_service.port}</span>
                    </div>
                  )}
                  {detail.assigned_service.model && (
                    <div className="admin-gpu-service-detail">
                      <span className="label">Model:</span>
                      <span className="value">{detail.assigned_service.model}</span>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* Hardware Info */}
            <section className="admin-gpu-detail-section">
              <h3>
                <HardDrive size={18} />
                Hardware
              </h3>
              <div className="admin-gpu-detail-grid">
                <div className="admin-gpu-detail-item">
                  <span className="label">Model</span>
                  <span className="value">{detail.gpu.name}</span>
                </div>
                <div className="admin-gpu-detail-item">
                  <span className="label">UUID</span>
                  <span className="value small">{detail.gpu.uuid}</span>
                </div>
                <div className="admin-gpu-detail-item">
                  <span className="label">Driver</span>
                  <span className="value">{detail.gpu.driver_version}</span>
                </div>
                <div className="admin-gpu-detail-item">
                  <span className="label">CUDA</span>
                  <span className="value">{detail.gpu.cuda_version}</span>
                </div>
                <div className="admin-gpu-detail-item">
                  <span className="label">P-State</span>
                  <span className="value">{detail.gpu.pstate}</span>
                </div>
              </div>
            </section>

            {/* Memory */}
            <section className="admin-gpu-detail-section">
              <h3>
                <Database size={18} />
                Memory
              </h3>
              <div className="admin-gpu-memory-bar-container">
                <div className="admin-gpu-memory-labels">
                  <span>Used: {(detail.gpu.memory_used / 1024).toFixed(2)} GB</span>
                  <span>Free: {(detail.gpu.memory_free / 1024).toFixed(2)} GB</span>
                  <span>Total: {(detail.gpu.memory_total / 1024).toFixed(2)} GB</span>
                </div>
                <div className="admin-gpu-memory-bar">
                  <div
                    className="admin-gpu-memory-bar-fill"
                    style={{
                      width: `${detail.gpu.memory_percent}%`,
                      backgroundColor: getUtilColor(detail.gpu.memory_percent),
                    }}
                  />
                </div>
                <div className="admin-gpu-memory-percent">
                  {detail.gpu.memory_percent.toFixed(1)}% used
                </div>
              </div>
            </section>

            {/* Utilization */}
            <section className="admin-gpu-detail-section">
              <h3>
                <Activity size={18} />
                Utilization
              </h3>
              <div className="admin-gpu-util-grid">
                <div className="admin-gpu-util-item">
                  <div className="admin-gpu-util-label">GPU Core</div>
                  <div className="admin-gpu-util-bar">
                    <div
                      className="admin-gpu-util-bar-fill"
                      style={{
                        width: `${detail.gpu.utilization_gpu}%`,
                        backgroundColor: getUtilColor(detail.gpu.utilization_gpu),
                      }}
                    />
                  </div>
                  <div className="admin-gpu-util-value" style={{ color: getUtilColor(detail.gpu.utilization_gpu) }}>
                    {detail.gpu.utilization_gpu.toFixed(0)}%
                  </div>
                </div>
                <div className="admin-gpu-util-item">
                  <div className="admin-gpu-util-label">Memory BW</div>
                  <div className="admin-gpu-util-bar">
                    <div
                      className="admin-gpu-util-bar-fill"
                      style={{
                        width: `${detail.gpu.utilization_memory}%`,
                        backgroundColor: getUtilColor(detail.gpu.utilization_memory),
                      }}
                    />
                  </div>
                  <div className="admin-gpu-util-value" style={{ color: getUtilColor(detail.gpu.utilization_memory) }}>
                    {detail.gpu.utilization_memory.toFixed(0)}%
                  </div>
                </div>
              </div>
            </section>

            {/* Clocks & Power */}
            <section className="admin-gpu-detail-section">
              <h3>
                <Gauge size={18} />
                Clocks & Power
              </h3>
              <div className="admin-gpu-stats-grid">
                <div className="admin-gpu-stat-item">
                  <Thermometer size={20} style={{ color: getTempColor(detail.gpu.temperature) }} />
                  <div className="admin-gpu-stat-info">
                    <span className="value" style={{ color: getTempColor(detail.gpu.temperature) }}>
                      {detail.gpu.temperature.toFixed(0)}°C
                    </span>
                    <span className="label">Temperature</span>
                  </div>
                </div>
                <div className="admin-gpu-stat-item">
                  <Zap size={20} />
                  <div className="admin-gpu-stat-info">
                    <span className="value">
                      {detail.gpu.power_draw.toFixed(0)}W / {detail.gpu.power_limit.toFixed(0)}W
                    </span>
                    <span className="label">Power</span>
                  </div>
                </div>
                <div className="admin-gpu-stat-item">
                  <Cpu size={20} />
                  <div className="admin-gpu-stat-info">
                    <span className="value">{detail.gpu.clock_sm} MHz</span>
                    <span className="label">SM Clock</span>
                  </div>
                </div>
                <div className="admin-gpu-stat-item">
                  <Database size={20} />
                  <div className="admin-gpu-stat-info">
                    <span className="value">{detail.gpu.clock_mem} MHz</span>
                    <span className="label">Mem Clock</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Workloads */}
            <section className="admin-gpu-detail-section">
              <h3>
                <Activity size={18} />
                Running Workloads
              </h3>
              {detail.processes && detail.processes.length > 0 ? (
                <div className="admin-gpu-process-table">
                  <table>
                    <thead>
                      <tr>
                        <th>PID</th>
                        <th>User</th>
                        <th>Memory</th>
                        <th>Runtime</th>
                        <th>Command</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.processes.map((proc) => (
                        <tr key={proc.pid}>
                          <td className="pid">{proc.pid}</td>
                          <td className="user">{proc.user}</td>
                          <td className="memory">{proc.memory_mb.toFixed(0)} MB</td>
                          <td className="runtime">{proc.runtime}</td>
                          <td className="command" title={proc.command}>
                            {proc.command.length > 50 ? proc.command.slice(0, 47) + '...' : proc.command}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : detail.assigned_service && detail.assigned_service.container ? (
                <div className="admin-gpu-container-info">
                  <div className="admin-gpu-container-row">
                    <Server size={16} />
                    <span className="label">Container:</span>
                    <span className="value">{detail.assigned_service.container}</span>
                  </div>
                  <div className="admin-gpu-container-row">
                    <Activity size={16} />
                    <span className="label">Status:</span>
                    <span className="value status-running">Running in Docker</span>
                  </div>
                  <div className="admin-gpu-container-row">
                    <Database size={16} />
                    <span className="label">Memory Used:</span>
                    <span className="value">{(detail.gpu.memory_used / 1024).toFixed(1)} GB</span>
                  </div>
                  <div className="admin-gpu-container-note">
                    GPU processes run inside Docker containers and are not visible to host nvidia-smi
                  </div>
                </div>
              ) : (
                <div className="admin-gpu-no-processes">
                  No compute processes running
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
};

// Health Tab with GPU Monitoring
const HealthTab: React.FC<{ data: ExecutiveDashboard }> = ({ data }) => {
  const [gpuStatus, setGpuStatus] = useState<GpuStatus | null>(null);
  const [gpuLoading, setGpuLoading] = useState(true);
  const [gpuError, setGpuError] = useState<string | null>(null);
  const [selectedGpu, setSelectedGpu] = useState<number | null>(null);

  const components = Object.entries(data.system_health.components || {});

  // Fetch GPU status (show_all=true for admin dashboard)
  const fetchGpuStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/verified-knowledge/monitor/gpu?show_all=true', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setGpuStatus(result);
      setGpuError(null);
    } catch (err) {
      console.error('Failed to fetch GPU status:', err);
      setGpuError('Failed to load GPU status');
    } finally {
      setGpuLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGpuStatus();
    // Auto-refresh GPU status every 10 seconds
    const interval = setInterval(fetchGpuStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchGpuStatus]);

  // GPU utilization color based on percentage
  const getUtilizationColor = (percent: number): string => {
    if (percent >= 90) return '#ef4444';
    if (percent >= 70) return '#f59e0b';
    return '#22c55e';
  };

  // Temperature color
  const getTemperatureColor = (temp: number): string => {
    if (temp >= 80) return '#ef4444';
    if (temp >= 65) return '#f59e0b';
    return '#22c55e';
  };

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

      {/* GPU Monitoring Section */}
      <section className="admin-gpu-section">
        <div className="admin-section-header">
          <h3 className="admin-section-title">
            <Cpu size={20} />
            GPU Monitoring
          </h3>
          <button
            className="admin-refresh-btn admin-refresh-btn--small"
            onClick={fetchGpuStatus}
            disabled={gpuLoading}
          >
            <RefreshCw size={14} className={gpuLoading ? 'spinning' : ''} />
          </button>
        </div>

        {gpuLoading && !gpuStatus && (
          <div className="admin-gpu-loading">
            <Loader2 className="spinning" size={24} />
            <span>Loading GPU status...</span>
          </div>
        )}

        {gpuError && !gpuStatus && (
          <div className="admin-gpu-error">
            <AlertTriangle size={20} />
            <span>{gpuError}</span>
          </div>
        )}

        {gpuStatus && !gpuStatus.available && (
          <div className="admin-gpu-unavailable">
            <AlertTriangle size={20} />
            <span>{gpuStatus.error || 'GPU monitoring not available'}</span>
          </div>
        )}

        {gpuStatus && gpuStatus.available && gpuStatus.gpus.length > 0 && (
          <div className="admin-gpu-grid">
            {gpuStatus.gpus.map((gpu) => (
              <div
                key={gpu.index}
                className="admin-gpu-card admin-gpu-card--clickable"
                onClick={() => setSelectedGpu(gpu.index)}
                onDoubleClick={() => setSelectedGpu(gpu.index)}
                title="Click for details"
              >
                <div className="admin-gpu-header">
                  <div className="admin-gpu-index">GPU {gpu.index}</div>
                  <div className="admin-gpu-name" title={gpu.name}>
                    {gpu.name.length > 25 ? gpu.name.slice(0, 22) + '...' : gpu.name}
                  </div>
                </div>

                {/* Memory Usage */}
                <div className="admin-gpu-metric">
                  <div className="admin-gpu-metric-header">
                    <HardDrive size={14} />
                    <span>Memory</span>
                    <span className="admin-gpu-metric-value">
                      {(gpu.memory_used / 1024).toFixed(1)} / {(gpu.memory_total / 1024).toFixed(1)} GB
                    </span>
                  </div>
                  <div className="admin-gpu-progress-bar">
                    <div
                      className="admin-gpu-progress-fill"
                      style={{
                        width: `${gpu.memory_percent}%`,
                        backgroundColor: getUtilizationColor(gpu.memory_percent),
                      }}
                    />
                  </div>
                  <span className="admin-gpu-metric-percent">{gpu.memory_percent.toFixed(1)}%</span>
                </div>

                {/* GPU Utilization */}
                <div className="admin-gpu-metric">
                  <div className="admin-gpu-metric-header">
                    <Activity size={14} />
                    <span>Utilization</span>
                    <span className="admin-gpu-metric-value">{gpu.utilization.toFixed(0)}%</span>
                  </div>
                  <div className="admin-gpu-progress-bar">
                    <div
                      className="admin-gpu-progress-fill"
                      style={{
                        width: `${gpu.utilization}%`,
                        backgroundColor: getUtilizationColor(gpu.utilization),
                      }}
                    />
                  </div>
                </div>

                {/* Temperature & Power */}
                <div className="admin-gpu-stats">
                  <div className="admin-gpu-stat">
                    <Thermometer size={14} style={{ color: getTemperatureColor(gpu.temperature) }} />
                    <span style={{ color: getTemperatureColor(gpu.temperature) }}>
                      {gpu.temperature.toFixed(0)}°C
                    </span>
                  </div>
                  <div className="admin-gpu-stat">
                    <Zap size={14} />
                    <span>{gpu.power_draw.toFixed(0)}W / {gpu.power_limit.toFixed(0)}W</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {gpuStatus && gpuStatus.available && gpuStatus.gpus.length === 0 && (
          <div className="admin-gpu-unavailable">
            <span>No GPUs found in monitoring range</span>
          </div>
        )}
      </section>

      {/* Components Section */}
      {components.length > 0 && (
        <section className="admin-components-grid">
          <h3 className="admin-section-title">
            <Server size={20} />
            Services
          </h3>
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

      {/* GPU Detail Modal */}
      {selectedGpu !== null && (
        <GpuDetailModal
          gpuIndex={selectedGpu}
          onClose={() => setSelectedGpu(null)}
        />
      )}
    </div>
  );
};

// RAG Metrics Tab
const RAGTab: React.FC = () => {
  const [data, setData] = useState<RAGMetricsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRAGMetrics = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/v1/admin/analytics/rag-metrics?days=7', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setData(result.data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch RAG metrics:', err);
      setError('Failed to load RAG metrics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRAGMetrics();
  }, [fetchRAGMetrics]);

  // Strategy color mapping
  const getStrategyColor = (strategy: string): string => {
    const colors: Record<string, string> = {
      'VECTOR': '#6366f1',
      'GRAPH': '#8b5cf6',
      'HYBRID': '#06b6d4',
      'CODE': '#f59e0b',
      'AUTO': '#22c55e',
    };
    return colors[strategy.toUpperCase()] || '#64748b';
  };

  // Format percentage
  const formatPercent = (value: number | null | undefined): string => {
    if (value === null || value === undefined) return 'N/A';
    return `${(value * 100).toFixed(1)}%`;
  };

  if (loading) {
    return (
      <div className="admin-tab-content">
        <div className="admin-loading-state">
          <Loader2 className="spinning" size={32} />
          <span>Loading RAG metrics...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="admin-tab-content">
        <div className="admin-error-state">
          <AlertTriangle size={32} />
          <span>{error || 'No data available'}</span>
          <button className="admin-refresh-btn" onClick={fetchRAGMetrics}>
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      </div>
    );
  }

  // Prepare trend data for chart
  const trendData = data.trend?.map((item) => ({
    date: new Date(item.date).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' }),
    queries: item.queries,
    successRate: item.success_rate * 100,
  })) || [];

  // Calculate satisfaction rate
  const totalFeedback = data.quality.thumbs_up_count + data.quality.thumbs_down_count;
  const satisfactionRate = totalFeedback > 0
    ? (data.quality.thumbs_up_count / totalFeedback) * 100
    : null;

  return (
    <div className="admin-tab-content">
      {/* Overview Section */}
      <section className="admin-rag-overview">
        <div className="admin-section-header">
          <h3 className="admin-section-title">
            <Database size={20} />
            RAG Performance Overview
          </h3>
          <button
            className="admin-refresh-btn admin-refresh-btn--small"
            onClick={fetchRAGMetrics}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          </button>
        </div>

        <div className="admin-rag-stats-grid">
          <div className="admin-rag-stat-card">
            <div className="admin-rag-stat-icon" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
              <Search size={24} style={{ color: '#6366f1' }} />
            </div>
            <div className="admin-rag-stat-content">
              <span className="admin-rag-stat-value">{data.total_queries.toLocaleString()}</span>
              <span className="admin-rag-stat-label">Total Queries</span>
            </div>
          </div>

          <div className="admin-rag-stat-card">
            <div className="admin-rag-stat-icon" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
              <Target size={24} style={{ color: '#22c55e' }} />
            </div>
            <div className="admin-rag-stat-content">
              <span className="admin-rag-stat-value">{formatPercent(data.overall_success_rate)}</span>
              <span className="admin-rag-stat-label">Success Rate</span>
            </div>
          </div>

          <div className="admin-rag-stat-card">
            <div className="admin-rag-stat-icon" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
              <ThumbsUp size={24} style={{ color: '#22c55e' }} />
            </div>
            <div className="admin-rag-stat-content">
              <span className="admin-rag-stat-value">{data.quality.thumbs_up_count}</span>
              <span className="admin-rag-stat-label">Positive Feedback</span>
            </div>
          </div>

          <div className="admin-rag-stat-card">
            <div className="admin-rag-stat-icon" style={{ background: 'rgba(239, 68, 68, 0.1)' }}>
              <ThumbsDown size={24} style={{ color: '#ef4444' }} />
            </div>
            <div className="admin-rag-stat-content">
              <span className="admin-rag-stat-value">{data.quality.thumbs_down_count}</span>
              <span className="admin-rag-stat-label">Negative Feedback</span>
            </div>
          </div>
        </div>
      </section>

      {/* Strategy Performance Section */}
      {data.strategies && data.strategies.length > 0 && (
        <section className="admin-rag-strategies">
          <h3 className="admin-section-title">
            <Gauge size={20} />
            Strategy Performance
          </h3>
          <div className="admin-rag-strategy-grid">
            {data.strategies.map((strategy) => (
              <div key={strategy.strategy} className="admin-rag-strategy-card">
                <div className="admin-rag-strategy-header">
                  <span
                    className="admin-rag-strategy-badge"
                    style={{ backgroundColor: getStrategyColor(strategy.strategy) }}
                  >
                    {strategy.strategy}
                  </span>
                  <span className="admin-rag-strategy-queries">
                    {strategy.total_queries.toLocaleString()} queries
                  </span>
                </div>
                <div className="admin-rag-strategy-metrics">
                  <div className="admin-rag-strategy-metric">
                    <span className="admin-rag-metric-label">Success Rate</span>
                    <span className="admin-rag-metric-value">{formatPercent(strategy.success_rate)}</span>
                  </div>
                  <div className="admin-rag-strategy-metric">
                    <span className="admin-rag-metric-label">Avg Retrieval</span>
                    <span className="admin-rag-metric-value">{strategy.avg_retrieval_time_ms}ms</span>
                  </div>
                  <div className="admin-rag-strategy-metric">
                    <span className="admin-rag-metric-label">Avg Results</span>
                    <span className="admin-rag-metric-value">{strategy.avg_result_count.toFixed(1)}</span>
                  </div>
                  <div className="admin-rag-strategy-metric">
                    <span className="admin-rag-metric-label">Confidence</span>
                    <span className="admin-rag-metric-value">{formatPercent(strategy.avg_confidence_score)}</span>
                  </div>
                </div>
                {/* Success rate bar */}
                <div className="admin-rag-strategy-bar">
                  <div
                    className="admin-rag-strategy-bar-fill"
                    style={{
                      width: `${(strategy.success_rate || 0) * 100}%`,
                      backgroundColor: getStrategyColor(strategy.strategy)
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Quality Metrics & Trend Section */}
      <div className="admin-rag-bottom-grid">
        {/* Quality Metrics */}
        <section className="admin-rag-quality">
          <h3 className="admin-section-title">
            <CheckCircle size={20} />
            Quality Metrics
          </h3>
          <div className="admin-rag-quality-content">
            <div className="admin-rag-quality-item">
              <div className="admin-rag-quality-label">User Satisfaction</div>
              <div className="admin-rag-quality-value">
                {satisfactionRate !== null ? (
                  <>
                    <span className={satisfactionRate >= 70 ? 'positive' : satisfactionRate >= 50 ? 'neutral' : 'negative'}>
                      {satisfactionRate.toFixed(1)}%
                    </span>
                    <span className="admin-rag-quality-detail">
                      ({data.quality.thumbs_up_count} / {totalFeedback})
                    </span>
                  </>
                ) : (
                  <span className="neutral">No feedback yet</span>
                )}
              </div>
            </div>
            <div className="admin-rag-quality-item">
              <div className="admin-rag-quality-label">Queries with Sources</div>
              <div className="admin-rag-quality-value">
                <span>{formatPercent(data.quality.queries_with_sources_pct)}</span>
              </div>
            </div>
            {data.quality.avg_user_rating && (
              <div className="admin-rag-quality-item">
                <div className="admin-rag-quality-label">Average Rating</div>
                <div className="admin-rag-quality-value">
                  <span>{data.quality.avg_user_rating.toFixed(1)} / 5</span>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Trend Chart */}
        {trendData.length > 0 && (
          <section className="admin-rag-trend">
            <h3 className="admin-section-title">
              <TrendingUp size={20} />
              Query Trend (7 Days)
            </h3>
            <div className="admin-chart-container">
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="ragQueryGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e2e8f0)" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 12, fill: 'var(--color-text-secondary, #64748b)' }}
                  />
                  <YAxis
                    tick={{ fontSize: 12, fill: 'var(--color-text-secondary, #64748b)' }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--color-bg-elevated, #fff)',
                      border: '1px solid var(--color-border, #e2e8f0)',
                      borderRadius: '8px'
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="queries"
                    stroke="#6366f1"
                    fill="url(#ragQueryGradient)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>
        )}
      </div>

      {/* Top Knowledge Sources */}
      {data.top_knowledge_sources && data.top_knowledge_sources.length > 0 && (
        <section className="admin-rag-sources">
          <h3 className="admin-section-title">
            <FileText size={20} />
            Top Knowledge Sources
          </h3>
          <div className="admin-rag-sources-table">
            <table>
              <thead>
                <tr>
                  <th>Source</th>
                  <th>Queries</th>
                  <th>Avg Score</th>
                </tr>
              </thead>
              <tbody>
                {data.top_knowledge_sources.map((source, idx) => (
                  <tr key={idx}>
                    <td className="admin-rag-source-name">{source.source}</td>
                    <td>{source.query_count.toLocaleString()}</td>
                    <td>{(source.avg_score * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
};

// Audit Tab
const AuditTab: React.FC = () => {
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [logs, setLogs] = useState<AuditLogsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [filterCategory, setFilterCategory] = useState<string>('');
  const [filterSeverity, setFilterSeverity] = useState<string>('');
  const [filterUserId, setFilterUserId] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 20;

  // Fetch audit stats
  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch('/api/v1/admin/analytics/audit-stats?hours=24', {
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setStats(result.data);
    } catch (err) {
      console.error('Failed to fetch audit stats:', err);
      setError('Failed to load audit statistics');
    }
  }, []);

  // Fetch audit logs with filters
  const fetchLogs = useCallback(async () => {
    try {
      setLogsLoading(true);
      const params = new URLSearchParams({
        page: currentPage.toString(),
        limit: pageSize.toString(),
      });
      if (filterCategory) params.append('action_category', filterCategory);
      if (filterSeverity) params.append('severity', filterSeverity);
      if (filterUserId) params.append('user_id', filterUserId);

      const response = await fetch(`/api/v1/admin/analytics/audit-logs?${params}`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      setLogs(result.data);
    } catch (err) {
      console.error('Failed to fetch audit logs:', err);
    } finally {
      setLogsLoading(false);
    }
  }, [currentPage, filterCategory, filterSeverity, filterUserId]);

  // Initial fetch
  useEffect(() => {
    const fetchAll = async () => {
      setLoading(true);
      await Promise.all([fetchStats(), fetchLogs()]);
      setLoading(false);
    };
    fetchAll();
  }, [fetchStats, fetchLogs]);

  // Refetch logs when filters change
  useEffect(() => {
    if (!loading) {
      fetchLogs();
    }
  }, [currentPage, filterCategory, filterSeverity, filterUserId, fetchLogs, loading]);

  // Category color mapping
  const getCategoryColor = (category: string): string => {
    const colors: Record<string, string> = {
      'USER_MANAGEMENT': '#6366f1',
      'CONTENT': '#8b5cf6',
      'SYSTEM': '#06b6d4',
      'SECURITY': '#ef4444',
      'GOVERNANCE': '#f59e0b',
      'AGENT': '#22c55e',
    };
    return colors[category] || '#64748b';
  };

  // Severity color mapping
  const getSeverityColor = (severity: string): string => {
    const colors: Record<string, string> = {
      'info': '#3b82f6',
      'warning': '#f59e0b',
      'error': '#ef4444',
      'critical': '#dc2626',
    };
    return colors[severity] || '#64748b';
  };

  // Severity icon
  const getSeverityIcon = (severity: string): React.ReactNode => {
    switch (severity) {
      case 'info': return <Info size={14} />;
      case 'warning': return <AlertTriangle size={14} />;
      case 'error': return <XCircle size={14} />;
      case 'critical': return <ShieldAlert size={14} />;
      default: return <AlertCircle size={14} />;
    }
  };

  // Category icon
  const getCategoryIcon = (category: string): React.ReactNode => {
    switch (category) {
      case 'USER_MANAGEMENT': return <Users size={16} />;
      case 'CONTENT': return <FileText size={16} />;
      case 'SYSTEM': return <Settings size={16} />;
      case 'SECURITY': return <Shield size={16} />;
      case 'GOVERNANCE': return <Eye size={16} />;
      case 'AGENT': return <Cpu size={16} />;
      default: return <Activity size={16} />;
    }
  };

  // Format timestamp
  const formatTimestamp = (ts: string): string => {
    return new Date(ts).toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Reset filters
  const resetFilters = () => {
    setFilterCategory('');
    setFilterSeverity('');
    setFilterUserId('');
    setCurrentPage(1);
  };

  if (loading) {
    return (
      <div className="admin-tab-content">
        <div className="admin-loading-state">
          <Loader2 className="spinning" size={32} />
          <span>Loading audit data...</span>
        </div>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="admin-tab-content">
        <div className="admin-error-state">
          <AlertTriangle size={32} />
          <span>{error || 'No data available'}</span>
          <button className="admin-refresh-btn" onClick={fetchStats}>
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      </div>
    );
  }

  // Prepare chart data
  const categoryData = Object.entries(stats.events_by_category || {}).map(([name, value]) => ({
    name,
    value,
    color: getCategoryColor(name),
  }));

  const severityData = Object.entries(stats.events_by_severity || {}).map(([name, value]) => ({
    name,
    value,
    color: getSeverityColor(name),
  }));

  const totalPages = logs ? Math.ceil(logs.total / pageSize) : 0;

  return (
    <div className="admin-tab-content">
      {/* Overview Section */}
      <section className="admin-audit-overview">
        <div className="admin-section-header">
          <h3 className="admin-section-title">
            <Shield size={20} />
            Audit Log Overview (Last 24 Hours)
          </h3>
          <button
            className="admin-refresh-btn admin-refresh-btn--small"
            onClick={() => { fetchStats(); fetchLogs(); }}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spinning' : ''} />
          </button>
        </div>

        <div className="admin-audit-stats-grid">
          <div className="admin-audit-stat-card">
            <div className="admin-audit-stat-icon" style={{ background: 'rgba(99, 102, 241, 0.1)' }}>
              <Activity size={24} style={{ color: '#6366f1' }} />
            </div>
            <div className="admin-audit-stat-content">
              <span className="admin-audit-stat-value">{stats.total_events.toLocaleString()}</span>
              <span className="admin-audit-stat-label">Total Events</span>
            </div>
          </div>

          <div className="admin-audit-stat-card">
            <div className="admin-audit-stat-icon" style={{ background: 'rgba(239, 68, 68, 0.1)' }}>
              <ShieldAlert size={24} style={{ color: '#ef4444' }} />
            </div>
            <div className="admin-audit-stat-content">
              <span className="admin-audit-stat-value">
                {(stats.events_by_severity?.critical || 0) + (stats.events_by_severity?.error || 0)}
              </span>
              <span className="admin-audit-stat-label">Critical/Error Events</span>
            </div>
          </div>

          <div className="admin-audit-stat-card">
            <div className="admin-audit-stat-icon" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
              <Users size={24} style={{ color: '#22c55e' }} />
            </div>
            <div className="admin-audit-stat-content">
              <span className="admin-audit-stat-value">
                {(stats.events_by_user || []).length}
              </span>
              <span className="admin-audit-stat-label">Active Users</span>
            </div>
          </div>

          <div className="admin-audit-stat-card">
            <div className="admin-audit-stat-icon" style={{ background: 'rgba(245, 158, 11, 0.1)' }}>
              <Shield size={24} style={{ color: '#f59e0b' }} />
            </div>
            <div className="admin-audit-stat-content">
              <span className="admin-audit-stat-value">
                {stats.events_by_category?.SECURITY || 0}
              </span>
              <span className="admin-audit-stat-label">Security Events</span>
            </div>
          </div>
        </div>
      </section>

      {/* Distribution Charts */}
      <section className="admin-audit-charts">
        <div className="admin-audit-chart-card">
          <h4 className="admin-audit-chart-title">Events by Category</h4>
          <div className="admin-audit-distribution">
            {categoryData.map((item) => (
              <div key={item.name} className="admin-audit-dist-item">
                <div className="admin-audit-dist-header">
                  <span className="admin-audit-dist-icon" style={{ color: item.color }}>
                    {getCategoryIcon(item.name)}
                  </span>
                  <span className="admin-audit-dist-name">{item.name.replace('_', ' ')}</span>
                  <span className="admin-audit-dist-value">{item.value}</span>
                </div>
                <div className="admin-audit-dist-bar">
                  <div
                    className="admin-audit-dist-bar-fill"
                    style={{
                      width: `${(item.value / stats.total_events) * 100}%`,
                      backgroundColor: item.color,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="admin-audit-chart-card">
          <h4 className="admin-audit-chart-title">Events by Severity</h4>
          <div className="admin-audit-severity-grid">
            {severityData.map((item) => (
              <div
                key={item.name}
                className="admin-audit-severity-card"
                style={{ borderLeftColor: item.color }}
              >
                <div className="admin-audit-severity-icon" style={{ color: item.color }}>
                  {getSeverityIcon(item.name)}
                </div>
                <div className="admin-audit-severity-info">
                  <span className="admin-audit-severity-value">{item.value}</span>
                  <span className="admin-audit-severity-name">{item.name}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Recent Security Events */}
      {stats.recent_security_events && stats.recent_security_events.length > 0 && (
        <section className="admin-audit-security">
          <h3 className="admin-section-title">
            <ShieldAlert size={20} />
            Recent Security Events
          </h3>
          <div className="admin-audit-security-list">
            {stats.recent_security_events.slice(0, 5).map((event) => (
              <div key={event.id} className="admin-audit-security-item">
                <div
                  className="admin-audit-security-severity"
                  style={{ backgroundColor: getSeverityColor(event.severity) }}
                >
                  {getSeverityIcon(event.severity)}
                </div>
                <div className="admin-audit-security-content">
                  <div className="admin-audit-security-action">{event.action}</div>
                  <div className="admin-audit-security-meta">
                    <span>{event.user_email || 'System'}</span>
                    <span className="admin-audit-security-time">
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Audit Logs Table */}
      <section className="admin-audit-logs">
        <div className="admin-section-header">
          <h3 className="admin-section-title">
            <FileText size={20} />
            Audit Logs
          </h3>
          <span className="admin-audit-logs-count">
            {logs?.total.toLocaleString() || 0} total records
          </span>
        </div>

        {/* Filters */}
        <div className="admin-audit-filters">
          <div className="admin-audit-filter-group">
            <Filter size={16} />
            <select
              value={filterCategory}
              onChange={(e) => { setFilterCategory(e.target.value); setCurrentPage(1); }}
              className="admin-audit-filter-select"
            >
              <option value="">All Categories</option>
              <option value="USER_MANAGEMENT">User Management</option>
              <option value="CONTENT">Content</option>
              <option value="SYSTEM">System</option>
              <option value="SECURITY">Security</option>
              <option value="GOVERNANCE">Governance</option>
              <option value="AGENT">Agent</option>
            </select>

            <select
              value={filterSeverity}
              onChange={(e) => { setFilterSeverity(e.target.value); setCurrentPage(1); }}
              className="admin-audit-filter-select"
            >
              <option value="">All Severities</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>

            <input
              type="text"
              value={filterUserId}
              onChange={(e) => { setFilterUserId(e.target.value); setCurrentPage(1); }}
              placeholder="Filter by User ID..."
              className="admin-audit-filter-input"
            />

            {(filterCategory || filterSeverity || filterUserId) && (
              <button className="admin-audit-filter-reset" onClick={resetFilters}>
                Reset
              </button>
            )}
          </div>
        </div>

        {/* Logs Table */}
        <div className="admin-audit-table-container">
          {logsLoading && (
            <div className="admin-audit-table-loading">
              <Loader2 className="spinning" size={20} />
            </div>
          )}

          <table className="admin-audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>User</th>
                <th>Action</th>
                <th>Category</th>
                <th>Severity</th>
                <th>Resource</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {logs?.entries && logs.entries.length > 0 ? (
                logs.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="admin-audit-cell-time">
                      {formatTimestamp(entry.timestamp)}
                    </td>
                    <td className="admin-audit-cell-user">
                      <User size={14} />
                      <span title={entry.user_id}>{entry.user_email || entry.user_id}</span>
                    </td>
                    <td className="admin-audit-cell-action">{entry.action}</td>
                    <td>
                      <span
                        className="admin-audit-badge"
                        style={{ backgroundColor: `${getCategoryColor(entry.action_category)}20`, color: getCategoryColor(entry.action_category) }}
                      >
                        {entry.action_category.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span
                        className="admin-audit-badge admin-audit-badge--severity"
                        style={{ backgroundColor: `${getSeverityColor(entry.severity)}20`, color: getSeverityColor(entry.severity) }}
                      >
                        {getSeverityIcon(entry.severity)}
                        {entry.severity}
                      </span>
                    </td>
                    <td className="admin-audit-cell-resource">
                      {entry.resource_name || entry.resource_type || '-'}
                    </td>
                    <td>
                      {entry.success ? (
                        <CheckCircle size={16} className="admin-audit-success" />
                      ) : (
                        <XCircle size={16} className="admin-audit-failure" />
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7} className="admin-audit-empty">
                    No audit logs found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {logs && logs.total > pageSize && (
          <div className="admin-audit-pagination">
            <button
              className="admin-audit-page-btn"
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage === 1}
            >
              <ChevronLeft size={16} />
              Previous
            </button>
            <span className="admin-audit-page-info">
              Page {currentPage} of {totalPages}
            </span>
            <button
              className="admin-audit-page-btn"
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
            >
              Next
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </section>
    </div>
  );
};

// EnhanceRequestsTab is imported from '../components/admin/enhance'

export default AdminDashboardPage;
