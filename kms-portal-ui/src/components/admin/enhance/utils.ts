/**
 * Utility functions for Enhancement Request components
 */
import React from 'react';
import { Search, Settings, Cpu, CheckCircle, Bot } from 'lucide-react';
import type { EnhanceRequestType, EnhancePriority, EnhanceStatus, AgentType } from './types';

// Format date to Korean locale
export const formatDate = (dateStr: string): string => {
  const date = new Date(dateStr);
  return date.toLocaleDateString('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

// Format duration in ms to readable string
export const formatDurationMs = (ms?: number): string => {
  if (!ms) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
};

// Status badge colors
export const getStatusColor = (status: EnhanceStatus | string): string => {
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
export const getPriorityColor = (priority?: EnhancePriority | string): string => {
  const colors: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#f59e0b',
    low: '#22c55e',
  };
  return priority ? colors[priority] || '#6b7280' : '#6b7280';
};

// Type icons
export const getTypeIcon = (type?: EnhanceRequestType | string): string => {
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
export const canExecute = (status: EnhanceStatus | string): boolean => {
  return status === 'submitted';
};

// Get agent display name
export const getAgentDisplayName = (agentType: AgentType | string): string => {
  const names: Record<string, string> = {
    analyst: 'Analyst Agent',
    architect: 'Architect Agent',
    coder: 'Coder Agent',
    qa: 'QA Agent',
  };
  return names[agentType] || agentType;
};

// Get agent icon component
export const getAgentIcon = (agentType: AgentType | string): React.ReactNode => {
  const iconSize = 16;
  switch (agentType) {
    case 'analyst':
      return React.createElement(Search, { size: iconSize });
    case 'architect':
      return React.createElement(Settings, { size: iconSize });
    case 'coder':
      return React.createElement(Cpu, { size: iconSize });
    case 'qa':
      return React.createElement(CheckCircle, { size: iconSize });
    default:
      return React.createElement(Bot, { size: iconSize });
  }
};

// Status options for filter
export const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'analyzing', label: 'Analyzing' },
  { value: 'analyzed', label: 'Analyzed' },
  { value: 'approved', label: 'Approved' },
  { value: 'implementing', label: 'Implementing' },
  { value: 'verified', label: 'Verified' },
  { value: 'released', label: 'Released' },
  { value: 'closed', label: 'Closed' },
];
