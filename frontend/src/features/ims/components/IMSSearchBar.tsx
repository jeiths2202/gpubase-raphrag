/**
 * IMS Search Bar Component
 * Natural language search input with advanced options
 */

import React, { useState } from 'react';
import { useIMSStore } from '../store/imsStore';
import { imsApiService } from '../services/ims-api';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  t: TranslateFunction;
}

export const IMSSearchBar: React.FC<Props> = ({ t }) => {
  const { setIsSearching, setSearchQuery, setCurrentJob, setJobProgress } = useIMSStore();
  const [query, setQuery] = useState('');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setSearchQuery(query);

    try {
      const job = await imsApiService.createCrawlJob({
        query,
        include_attachments: true,
        include_related_issues: false,
        max_issues: 100
      });
      setCurrentJob(job);

      // Start SSE stream to monitor progress
      const streamUrl = `/api/v1/ims-jobs/${job.id}/stream`;
      const eventSource = new EventSource(streamUrl, { withCredentials: true });

      eventSource.onmessage = (event) => {
        try {
          const progress = JSON.parse(event.data);
          console.log('Job progress:', progress);

          // Update job progress in store
          setJobProgress(progress);

          // Close connection on completion or failure
          if (progress.event === 'job_completed' || progress.event === 'job_failed') {
            eventSource.close();
            setIsSearching(false);
          }
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
        }
      };

      eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        eventSource.close();
        setIsSearching(false);
      };

    } catch (error) {
      console.error('Search failed:', error);
      setIsSearching(false);
    }
  };

  return (
    <form onSubmit={handleSearch} style={{
      display: 'flex',
      gap: '12px',
      padding: '20px',
      background: 'var(--card-bg)',
      border: '1px solid var(--border)',
      borderRadius: '12px'
    }}>
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search IMS issues (e.g., 'Show me critical bugs from last week')"
        style={{
          flex: 1,
          padding: '12px',
          background: 'var(--input-bg)',
          border: '1px solid var(--border)',
          borderRadius: '8px',
          color: 'var(--text-primary)',
          fontSize: '14px'
        }}
      />
      <button
        type="submit"
        disabled={!query.trim()}
        style={{
          padding: '12px 24px',
          background: query.trim() ? 'var(--accent)' : 'var(--card-bg)',
          border: 'none',
          borderRadius: '8px',
          color: 'white',
          fontWeight: 600,
          cursor: query.trim() ? 'pointer' : 'not-allowed',
          opacity: query.trim() ? 1 : 0.6,
          fontSize: '14px'
        }}
      >
        🔍 Search
      </button>
    </form>
  );
};
