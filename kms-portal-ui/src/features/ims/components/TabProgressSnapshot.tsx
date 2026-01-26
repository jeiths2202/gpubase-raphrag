/**
 * Tab Progress Snapshot Component
 *
 * Compact display of completion statistics for a result tab
 */

import React from 'react';
import { Search, FileText, Link2, Clock, CheckCircle, AlertTriangle, XCircle } from 'lucide-react';
import type { CompletionStats } from '../types';

interface TabProgressSnapshotProps {
  stats: CompletionStats;
  t: (key: string) => string;
}

export const TabProgressSnapshot: React.FC<TabProgressSnapshotProps> = ({ stats, t }) => {
  const formatDuration = (seconds: number): string => {
    if (seconds < 60) {
      return `${Math.round(seconds)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
  };

  const getOutcomeIcon = () => {
    switch (stats.outcome) {
      case 'success':
        return <CheckCircle size={16} className="ims-snapshot__outcome-icon success" />;
      case 'partial':
        return <AlertTriangle size={16} className="ims-snapshot__outcome-icon warning" />;
      case 'failed':
        return <XCircle size={16} className="ims-snapshot__outcome-icon error" />;
    }
  };

  const getOutcomeText = () => {
    switch (stats.outcome) {
      case 'success':
        return t('ims.snapshot.success');
      case 'partial':
        return t('ims.snapshot.partial');
      case 'failed':
        return t('ims.snapshot.failed');
    }
  };

  return (
    <div className="ims-snapshot">
      <div className="ims-snapshot__header">
        {getOutcomeIcon()}
        <span className="ims-snapshot__outcome">{getOutcomeText()}</span>
        <span className="ims-snapshot__duration">
          <Clock size={14} />
          {formatDuration(stats.duration)}
        </span>
      </div>

      <div className="ims-snapshot__stats">
        <div className="ims-snapshot__stat">
          <Search size={14} />
          <span className="ims-snapshot__stat-value">{stats.totalIssues}</span>
          <span className="ims-snapshot__stat-label">{t('ims.results.found')}</span>
        </div>
        <div className="ims-snapshot__stat">
          <FileText size={14} />
          <span className="ims-snapshot__stat-value">{stats.successfulIssues}</span>
          <span className="ims-snapshot__stat-label">{t('ims.results.crawled')}</span>
        </div>
        {stats.relatedIssues !== undefined && stats.relatedIssues > 0 && (
          <div className="ims-snapshot__stat">
            <Link2 size={14} />
            <span className="ims-snapshot__stat-value">{stats.relatedIssues}</span>
            <span className="ims-snapshot__stat-label">{t('ims.results.related')}</span>
          </div>
        )}
      </div>

      {stats.progressSnapshot && (
        <div className="ims-snapshot__timestamp">
          {new Date(stats.progressSnapshot.timestamp).toLocaleString()}
        </div>
      )}
    </div>
  );
};

export default TabProgressSnapshot;
