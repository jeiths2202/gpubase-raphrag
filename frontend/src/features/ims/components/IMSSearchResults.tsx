/**
 * IMS Search Results Component
 * Displays results in selected view mode
 */

import React from 'react';
import type { IMSIssue, ViewMode } from '../store/imsStore';
import type { TranslateFunction } from '../../../i18n/types';

interface Props {
  results: IMSIssue[];
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  t: TranslateFunction;
}

export const IMSSearchResults: React.FC<Props> = ({ results, viewMode, onViewModeChange, t }) => {
  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      overflow: 'hidden'
    }}>
      {/* View Mode Selector */}
      <div style={{ display: 'flex', gap: '8px' }}>
        {(['table', 'cards', 'graph'] as ViewMode[]).map((mode) => (
          <button
            key={mode}
            onClick={() => onViewModeChange(mode)}
            style={{
              padding: '8px 16px',
              background: viewMode === mode ? 'var(--accent)' : 'transparent',
              border: `1px solid ${viewMode === mode ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: '6px',
              color: viewMode === mode ? 'white' : 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '14px',
              textTransform: 'capitalize'
            }}
          >
            {mode}
          </button>
        ))}
      </div>

      {/* Results Display */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        background: 'var(--card-bg)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '20px'
      }}>
        {viewMode === 'table' && (
          <div>
            <h3>Table View (TODO: Implement)</h3>
            <p>{results.length} results found</p>
          </div>
        )}
        {viewMode === 'cards' && (
          <div>
            <h3>Cards View (TODO: Implement)</h3>
            <p>{results.length} results found</p>
          </div>
        )}
        {viewMode === 'graph' && (
          <div>
            <h3>Graph View (TODO: Implement)</h3>
            <p>{results.length} results found</p>
          </div>
        )}
      </div>
    </div>
  );
};
