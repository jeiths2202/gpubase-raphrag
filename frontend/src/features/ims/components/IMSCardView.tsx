/**
 * IMS Card View Component
 * Card-based grid view for search results with virtual scrolling
 */

import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import type { IMSIssue } from './IMSTableView';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  issues: IMSIssue[];
  t: TranslateFunction;
  onIssueClick?: (issue: IMSIssue) => void;
}

export const IMSCardView: React.FC<Props> = ({ issues, t, onIssueClick }) => {
  const getPriorityColor = (priority: string) => {
    switch (priority.toUpperCase()) {
      case 'CRITICAL': return '#dc2626';
      case 'HIGH': return '#f59e0b';
      case 'MEDIUM': return '#3b82f6';
      case 'LOW': return '#10b981';
      default: return '#6b7280';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toUpperCase()) {
      case 'OPEN': return '#3b82f6';
      case 'IN_PROGRESS': return '#f59e0b';
      case 'RESOLVED': return '#10b981';
      case 'CLOSED': return '#6b7280';
      default: return '#6b7280';
    }
  };

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
      gap: '20px',
      width: '100%'
    }}>
      {issues.map((issue, idx) => (
        <motion.div
          key={issue.id}
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: idx * 0.03 }}
          whileHover={{ scale: 1.02, boxShadow: '0 4px 12px rgba(0,0,0,0.15)' }}
          onClick={() => onIssueClick?.(issue)}
          style={{
            padding: '20px',
            background: 'var(--card-bg)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            cursor: onIssueClick ? 'pointer' : 'default',
            transition: 'all 0.2s ease'
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'start',
            marginBottom: '12px'
          }}>
            <div style={{
              fontFamily: 'monospace',
              fontSize: '13px',
              fontWeight: 600,
              color: 'var(--accent)'
            }}>
              {issue.ims_id}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <span style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                background: `${getPriorityColor(issue.priority)}20`,
                color: getPriorityColor(issue.priority)
              }}>
                {issue.priority}
              </span>
              <span style={{
                padding: '3px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 600,
                background: `${getStatusColor(issue.status)}20`,
                color: getStatusColor(issue.status)
              }}>
                {issue.status}
              </span>
            </div>
          </div>

          {/* Title */}
          <h4 style={{
            margin: '0 0 12px 0',
            fontSize: '16px',
            fontWeight: 600,
            lineHeight: '1.4',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {issue.title}
          </h4>

          {/* Description */}
          <p style={{
            margin: '0 0 16px 0',
            fontSize: '14px',
            color: 'var(--text-secondary)',
            lineHeight: '1.5',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
          }}>
            {issue.description || 'No description'}
          </p>

          {/* Labels */}
          {issue.labels.length > 0 && (
            <div style={{
              display: 'flex',
              gap: '6px',
              flexWrap: 'wrap',
              marginBottom: '16px'
            }}>
              {issue.labels.slice(0, 3).map((label, i) => (
                <span
                  key={i}
                  style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    background: 'var(--input-bg)',
                    color: 'var(--text-secondary)'
                  }}
                >
                  {label}
                </span>
              ))}
              {issue.labels.length > 3 && (
                <span style={{
                  padding: '2px 8px',
                  fontSize: '11px',
                  color: 'var(--text-secondary)'
                }}>
                  +{issue.labels.length - 3} more
                </span>
              )}
            </div>
          )}

          {/* Footer */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            paddingTop: '12px',
            borderTop: '1px solid var(--border)',
            fontSize: '12px',
            color: 'var(--text-secondary)'
          }}>
            <div>
              <div style={{ marginBottom: '4px' }}>
                <strong>Reporter:</strong> {issue.reporter}
              </div>
              {issue.assignee && (
                <div>
                  <strong>Assignee:</strong> {issue.assignee}
                </div>
              )}
            </div>
            <div style={{ textAlign: 'right' }}>
              <div>{new Date(issue.created_at).toLocaleDateString()}</div>
              {issue.similarity_score !== undefined && (
                <div style={{
                  marginTop: '4px',
                  fontWeight: 600,
                  color: 'var(--accent)'
                }}>
                  {(issue.similarity_score * 100).toFixed(1)}%
                </div>
              )}
            </div>
          </div>
        </motion.div>
      ))}

      {issues.length === 0 && (
        <div style={{
          gridColumn: '1 / -1',
          padding: '60px 20px',
          textAlign: 'center',
          color: 'var(--text-secondary)'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>📭</div>
          <div style={{ fontSize: '16px', fontWeight: 500 }}>No issues found</div>
          <div style={{ fontSize: '14px', marginTop: '8px' }}>
            Try adjusting your search query or filters
          </div>
        </div>
      )}
    </div>
  );
};
