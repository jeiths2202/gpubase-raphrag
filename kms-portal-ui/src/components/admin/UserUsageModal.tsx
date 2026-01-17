/**
 * User Usage Modal Component
 * Shows detailed resource usage statistics with charts
 */

import React, { useState, useEffect } from 'react';
import { X, Loader2, Activity, Coins, DollarSign, Clock } from 'lucide-react';
import {
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { UserData } from './UserManagementTable';

interface UserUsageModalProps {
  user: UserData;
  onClose: () => void;
}

interface UsageSummary {
  user_id: string;
  total_queries: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
  last_activity: string | null;
}

interface UsageTrend {
  date: string;
  queries: number;
  tokens: number;
  cost: number;
}

interface AgentUsage {
  agent_type: string;
  query_count: number;
  token_count: number;
  percentage: number;
}

const COLORS = ['#6366f1', '#8b5cf6', '#a78bfa', '#f59e0b', '#22c55e', '#ef4444'];

// Format number with K/M suffix
const formatNumber = (num: number): string => {
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return num.toString();
};

// Format relative time
const formatRelativeTime = (dateStr: string | null): string => {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);

  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
};

const UserUsageModal: React.FC<UserUsageModalProps> = ({
  user,
  onClose,
}) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [trend, setTrend] = useState<UsageTrend[]>([]);
  const [agentUsage, setAgentUsage] = useState<AgentUsage[]>([]);
  const [period, setPeriod] = useState(7);

  // Fetch usage data
  const fetchUsageData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch all data in parallel
      const [summaryRes, trendRes, agentRes] = await Promise.all([
        fetch(`/api/v1/admin/users/${user.id}/usage`, { credentials: 'include' }),
        fetch(`/api/v1/admin/users/${user.id}/usage/trend?days=${period}`, { credentials: 'include' }),
        fetch(`/api/v1/admin/users/${user.id}/usage/by-agent`, { credentials: 'include' }),
      ]);

      if (!summaryRes.ok || !trendRes.ok || !agentRes.ok) {
        throw new Error('Failed to fetch usage data');
      }

      const [summaryData, trendData, agentData] = await Promise.all([
        summaryRes.json(),
        trendRes.json(),
        agentRes.json(),
      ]);

      setSummary(summaryData.data);
      setTrend(trendData.data);
      setAgentUsage(agentData.data);
    } catch (err) {
      console.error('Failed to fetch usage data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load usage data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsageData();
  }, [user.id, period]);

  // Close on escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-content--large" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2>User Usage</h2>
            <p className="modal-subtitle">{user.email}</p>
          </div>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="modal-loading">
              <Loader2 className="spinning" size={32} />
              <span>Loading usage data...</span>
            </div>
          ) : error ? (
            <div className="modal-error">
              <span>{error}</span>
              <button onClick={fetchUsageData}>Retry</button>
            </div>
          ) : (
            <>
              {/* KPI Cards */}
              <div className="usage-kpi-grid">
                <div className="usage-kpi-card">
                  <div className="usage-kpi-icon" style={{ backgroundColor: '#6366f115', color: '#6366f1' }}>
                    <Activity size={20} />
                  </div>
                  <div className="usage-kpi-content">
                    <div className="usage-kpi-label">Total Queries</div>
                    <div className="usage-kpi-value">{formatNumber(summary?.total_queries || 0)}</div>
                  </div>
                </div>
                <div className="usage-kpi-card">
                  <div className="usage-kpi-icon" style={{ backgroundColor: '#f59e0b15', color: '#f59e0b' }}>
                    <Coins size={20} />
                  </div>
                  <div className="usage-kpi-content">
                    <div className="usage-kpi-label">Total Tokens</div>
                    <div className="usage-kpi-value">{formatNumber(summary?.total_tokens || 0)}</div>
                  </div>
                </div>
                <div className="usage-kpi-card">
                  <div className="usage-kpi-icon" style={{ backgroundColor: '#22c55e15', color: '#22c55e' }}>
                    <DollarSign size={20} />
                  </div>
                  <div className="usage-kpi-content">
                    <div className="usage-kpi-label">Est. Cost</div>
                    <div className="usage-kpi-value">${summary?.estimated_cost?.toFixed(4) || '0.00'}</div>
                  </div>
                </div>
                <div className="usage-kpi-card">
                  <div className="usage-kpi-icon" style={{ backgroundColor: '#8b5cf615', color: '#8b5cf6' }}>
                    <Clock size={20} />
                  </div>
                  <div className="usage-kpi-content">
                    <div className="usage-kpi-label">Last Activity</div>
                    <div className="usage-kpi-value">{formatRelativeTime(summary?.last_activity || null)}</div>
                  </div>
                </div>
              </div>

              {/* Period Selector */}
              <div className="usage-period-selector">
                <span>Period:</span>
                <select value={period} onChange={(e) => setPeriod(Number(e.target.value))}>
                  <option value={7}>Last 7 days</option>
                  <option value={14}>Last 14 days</option>
                  <option value={30}>Last 30 days</option>
                </select>
              </div>

              {/* Usage Trend Chart */}
              <div className="usage-chart-section">
                <h3>Daily Usage Trend</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <AreaChart data={trend}>
                    <defs>
                      <linearGradient id="usageGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis
                      dataKey="date"
                      stroke="var(--color-text-secondary)"
                      fontSize={11}
                      tickFormatter={(val) => val.slice(5)}
                    />
                    <YAxis stroke="var(--color-text-secondary)" fontSize={11} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-bg-elevated)',
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                      }}
                      formatter={(value: number, name: string) => [
                        name === 'tokens' ? formatNumber(value) : value,
                        name === 'tokens' ? 'Tokens' : 'Queries'
                      ]}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="queries"
                      stroke="#6366f1"
                      fill="url(#usageGradient)"
                      strokeWidth={2}
                      name="Queries"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Agent Usage Section */}
              <div className="usage-chart-row">
                <div className="usage-chart-section usage-chart-section--half">
                  <h3>Usage by Agent</h3>
                  {agentUsage.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={agentUsage}
                          cx="50%"
                          cy="50%"
                          outerRadius={70}
                          fill="#8884d8"
                          dataKey="query_count"
                          nameKey="agent_type"
                          label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                          labelLine={false}
                        >
                          {agentUsage.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="usage-no-data">No agent usage data</div>
                  )}
                </div>

                <div className="usage-chart-section usage-chart-section--half">
                  <h3>Agent Breakdown</h3>
                  <div className="agent-usage-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Agent</th>
                          <th>Queries</th>
                          <th>Tokens</th>
                          <th>%</th>
                        </tr>
                      </thead>
                      <tbody>
                        {agentUsage.length > 0 ? (
                          agentUsage.map((agent, index) => (
                            <tr key={agent.agent_type}>
                              <td>
                                <span className="agent-color" style={{ backgroundColor: COLORS[index % COLORS.length] }} />
                                {agent.agent_type}
                              </td>
                              <td>{agent.query_count}</td>
                              <td>{formatNumber(agent.token_count)}</td>
                              <td>{agent.percentage.toFixed(1)}%</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={4} className="usage-no-data">No data</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              {/* Token Details */}
              <div className="usage-token-details">
                <div className="token-detail-item">
                  <span className="token-label">Input Tokens:</span>
                  <span className="token-value">{formatNumber(summary?.input_tokens || 0)}</span>
                </div>
                <div className="token-detail-item">
                  <span className="token-label">Output Tokens:</span>
                  <span className="token-value">{formatNumber(summary?.output_tokens || 0)}</span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn--primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default UserUsageModal;
