/**
 * IMS Progress Indicator Component
 * Real-time progress display for crawl jobs
 */

import React from 'react';
import type { IMSJob } from '../store/imsStore';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  job: IMSJob;
  t: TranslateFunction;
}

export const IMSProgressIndicator: React.FC<Props> = ({ job, t }) => {
  return (
    <div style={{
      padding: '20px',
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <span style={{ fontSize: '14px', fontWeight: 600 }}>{job.current_step}</span>
        <span style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>
          {job.progress_percentage}%
        </span>
      </div>
      <div style={{
        width: '100%',
        height: '8px',
        background: 'var(--input-bg)',
        borderRadius: '4px',
        overflow: 'hidden'
      }}>
        <div style={{
          width: `${job.progress_percentage}%`,
          height: '100%',
          background: 'var(--accent)',
          transition: 'width 0.3s ease'
        }} />
      </div>
      <div style={{
        display: 'flex',
        gap: '20px',
        marginTop: '12px',
        fontSize: '13px',
        color: 'var(--text-secondary)'
      }}>
        <span>Found: {job.issues_found}</span>
        <span>Crawled: {job.issues_crawled}</span>
        <span>Attachments: {job.attachments_processed}</span>
      </div>
    </div>
  );
};
