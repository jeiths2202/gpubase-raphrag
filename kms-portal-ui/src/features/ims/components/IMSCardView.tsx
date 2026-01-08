/**
 * IMS Card View Component
 *
 * Responsive grid card display for issues
 */

import React from 'react';
import { motion } from 'framer-motion';
import { User, Calendar, Tag, Percent, FileText } from 'lucide-react';
import type { IMSIssue, IssueStatus, IssuePriority } from '../types';

interface IMSCardViewProps {
  issues: IMSIssue[];
  onIssueClick?: (issue: IMSIssue) => void;
  t: (key: string) => string;
}

const STATUS_COLORS: Record<IssueStatus, string> = {
  open: 'status--open',
  in_progress: 'status--progress',
  resolved: 'status--resolved',
  closed: 'status--closed',
  pending: 'status--pending',
  rejected: 'status--rejected',
};

const PRIORITY_COLORS: Record<IssuePriority, string> = {
  critical: 'priority--critical',
  high: 'priority--high',
  medium: 'priority--medium',
  low: 'priority--low',
  trivial: 'priority--trivial',
};

export const IMSCardView: React.FC<IMSCardViewProps> = ({ issues, onIssueClick, t }) => {
  const truncateText = (text: string, maxLength: number) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  const formatScore = (score?: number) => {
    if (score === undefined || score === null) return null;
    return `${(score * 100).toFixed(0)}%`;
  };

  if (issues.length === 0) {
    return (
      <div className="ims-cards__empty">
        <FileText size={48} />
        <p>{t('ims.results.noResults')}</p>
      </div>
    );
  }

  return (
    <div className="ims-cards">
      {issues.map((issue, index) => (
        <motion.div
          key={issue.id}
          className="ims-card"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.02 }}
          whileHover={{ scale: 1.02 }}
          onClick={() => onIssueClick?.(issue)}
        >
          {/* Header */}
          <div className="ims-card__header">
            <span className="ims-card__id">{issue.ims_id}</span>
            <div className="ims-card__badges">
              <span className={`ims-badge ims-badge--sm ${STATUS_COLORS[issue.status]}`}>
                {t(`ims.status.${issue.status}`)}
              </span>
              <span className={`ims-badge ims-badge--sm ${PRIORITY_COLORS[issue.priority]}`}>
                {t(`ims.priority.${issue.priority}`)}
              </span>
            </div>
          </div>

          {/* Title */}
          <h3 className="ims-card__title" title={issue.title}>
            {truncateText(issue.title, 80)}
          </h3>

          {/* Description */}
          {issue.description && (
            <p className="ims-card__description">
              {truncateText(issue.description, 150)}
            </p>
          )}

          {/* Labels */}
          {issue.labels && issue.labels.length > 0 && (
            <div className="ims-card__labels">
              <Tag size={12} />
              {issue.labels.slice(0, 3).map((label) => (
                <span key={label} className="ims-card__label">
                  {label}
                </span>
              ))}
              {issue.labels.length > 3 && (
                <span className="ims-card__label-more">
                  +{issue.labels.length - 3}
                </span>
              )}
            </div>
          )}

          {/* Footer */}
          <div className="ims-card__footer">
            <div className="ims-card__meta">
              <span className="ims-card__meta-item">
                <User size={12} />
                {issue.reporter}
              </span>
              <span className="ims-card__meta-item">
                <Calendar size={12} />
                {formatDate(issue.created_at)}
              </span>
            </div>

            {/* Similarity Score */}
            {issue.similarity_score !== undefined && (
              <div className="ims-card__score">
                <Percent size={12} />
                {formatScore(issue.similarity_score)}
              </div>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  );
};

export default IMSCardView;
