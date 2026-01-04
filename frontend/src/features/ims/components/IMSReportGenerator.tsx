/**
 * IMS Report Generator Component
 * Generate and download markdown reports for IMS issues
 */

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import type { TranslateFunction } from '../../../i18n/types';
import api from '../../../services/api';

interface Props {
  t: TranslateFunction;
  searchQuery?: string;
}

interface ReportOptions {
  title: string;
  description: string;
  dateRangeStart: string;
  dateRangeEnd: string;
  statusFilter: string;
  priorityFilter: string;
  maxIssues: number;
}

export const IMSReportGenerator: React.FC<Props> = ({ t, searchQuery }) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [options, setOptions] = useState<ReportOptions>({
    title: 'IMS Issues Report',
    description: '',
    dateRangeStart: '',
    dateRangeEnd: '',
    statusFilter: '',
    priorityFilter: '',
    maxIssues: 1000
  });

  const handleGenerateReport = async () => {
    setIsGenerating(true);

    try {
      const payload = {
        title: options.title,
        description: options.description || null,
        date_range_start: options.dateRangeStart || null,
        date_range_end: options.dateRangeEnd || null,
        status_filter: options.statusFilter || null,
        priority_filter: options.priorityFilter || null,
        max_issues: options.maxIssues
      };

      const response = await api.post('/api/v1/ims-reports/generate-download', payload, {
        responseType: 'blob'
      });

      // Create download link
      const blob = new Blob([response.data], { type: 'text/markdown' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;

      // Extract filename from content-disposition header or use default
      const contentDisposition = response.headers['content-disposition'];
      const filename = contentDisposition
        ? contentDisposition.split('filename=')[1]?.replace(/"/g, '')
        : `ims_report_${Date.now()}.md`;

      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

    } catch (error) {
      console.error('Failed to generate report:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleGetQuickSummary = async () => {
    try {
      const response = await api.get('/api/v1/ims-reports/quick-summary');
      const stats = response.data;

      const summaryText = `
📊 Quick Summary

Total Issues: ${stats.total_issues}
Open Issues: ${stats.open_issues}
Closed Issues: ${stats.closed_issues}
Critical Issues: ${stats.critical_issues}
High Priority: ${stats.high_priority_issues}

By Status:
${Object.entries(stats.by_status).map(([status, count]) => `  ${status}: ${count}`).join('\n')}

By Priority:
${Object.entries(stats.by_priority).map(([status, count]) => `  ${status}: ${count}`).join('\n')}
      `.trim();

      alert(summaryText);
    } catch (error) {
      console.error('Failed to get summary:', error);
      alert('Failed to get summary. Please try again.');
    }
  };

  return (
    <div style={{
      padding: '24px',
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px'
    }}>
      {/* Header */}
      <div style={{ marginBottom: '24px' }}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 600 }}>
          📄 Generate Report
        </h3>
        <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-secondary)' }}>
          Generate markdown reports with statistics and issue summaries
        </p>
      </div>

      {/* Report Options */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Title */}
        <div>
          <label style={{
            display: 'block',
            fontSize: '14px',
            fontWeight: 500,
            marginBottom: '6px'
          }}>
            Report Title
          </label>
          <input
            type="text"
            value={options.title}
            onChange={(e) => setOptions({ ...options, title: e.target.value })}
            placeholder="IMS Issues Report"
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border)',
              background: 'var(--input-bg)',
              color: 'var(--text)',
              fontSize: '14px'
            }}
          />
        </div>

        {/* Description */}
        <div>
          <label style={{
            display: 'block',
            fontSize: '14px',
            fontWeight: 500,
            marginBottom: '6px'
          }}>
            Description (optional)
          </label>
          <textarea
            value={options.description}
            onChange={(e) => setOptions({ ...options, description: e.target.value })}
            placeholder="Report description..."
            rows={3}
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              border: '1px solid var(--border)',
              background: 'var(--input-bg)',
              color: 'var(--text)',
              fontSize: '14px',
              resize: 'vertical'
            }}
          />
        </div>

        {/* Date Range */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: 500,
              marginBottom: '6px'
            }}>
              From Date
            </label>
            <input
              type="date"
              value={options.dateRangeStart}
              onChange={(e) => setOptions({ ...options, dateRangeStart: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                background: 'var(--input-bg)',
                color: 'var(--text)',
                fontSize: '14px'
              }}
            />
          </div>
          <div>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: 500,
              marginBottom: '6px'
            }}>
              To Date
            </label>
            <input
              type="date"
              value={options.dateRangeEnd}
              onChange={(e) => setOptions({ ...options, dateRangeEnd: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                background: 'var(--input-bg)',
                color: 'var(--text)',
                fontSize: '14px'
              }}
            />
          </div>
        </div>

        {/* Filters */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: 500,
              marginBottom: '6px'
            }}>
              Status Filter
            </label>
            <select
              value={options.statusFilter}
              onChange={(e) => setOptions({ ...options, statusFilter: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                background: 'var(--input-bg)',
                color: 'var(--text)',
                fontSize: '14px'
              }}
            >
              <option value="">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="IN_PROGRESS">In Progress</option>
              <option value="RESOLVED">Resolved</option>
              <option value="CLOSED">Closed</option>
            </select>
          </div>
          <div>
            <label style={{
              display: 'block',
              fontSize: '14px',
              fontWeight: 500,
              marginBottom: '6px'
            }}>
              Priority Filter
            </label>
            <select
              value={options.priorityFilter}
              onChange={(e) => setOptions({ ...options, priorityFilter: e.target.value })}
              style={{
                width: '100%',
                padding: '10px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border)',
                background: 'var(--input-bg)',
                color: 'var(--text)',
                fontSize: '14px'
              }}
            >
              <option value="">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>

        {/* Max Issues */}
        <div>
          <label style={{
            display: 'block',
            fontSize: '14px',
            fontWeight: 500,
            marginBottom: '6px'
          }}>
            Maximum Issues: {options.maxIssues}
          </label>
          <input
            type="range"
            min="10"
            max="10000"
            step="10"
            value={options.maxIssues}
            onChange={(e) => setOptions({ ...options, maxIssues: parseInt(e.target.value) })}
            style={{
              width: '100%'
            }}
          />
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            marginTop: '4px'
          }}>
            <span>10</span>
            <span>10,000</span>
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleGenerateReport}
            disabled={isGenerating}
            style={{
              flex: 1,
              padding: '12px 20px',
              background: isGenerating ? 'var(--text-secondary)' : 'var(--accent)',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              fontSize: '15px',
              fontWeight: 600,
              cursor: isGenerating ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px'
            }}
          >
            {isGenerating ? (
              <>
                <span>⏳</span>
                <span>Generating...</span>
              </>
            ) : (
              <>
                <span>📥</span>
                <span>Generate & Download</span>
              </>
            )}
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleGetQuickSummary}
            style={{
              padding: '12px 20px',
              background: 'var(--card-bg)',
              color: 'var(--text)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              fontSize: '15px',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            📊 Quick Summary
          </motion.button>
        </div>
      </div>
    </div>
  );
};
