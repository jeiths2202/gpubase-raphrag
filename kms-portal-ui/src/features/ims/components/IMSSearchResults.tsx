/**
 * IMS Search Results Component
 *
 * Container for displaying search results with view mode selection
 * and AI Assistant panel for chatting about searched issues
 */

import React, { useState, useCallback } from 'react';
import { Table, LayoutGrid, GitBranch, Sparkles } from 'lucide-react';
import { IMSTableView } from './IMSTableView';
import { IMSCardView } from './IMSCardView';
import { IMSGraphView } from './IMSGraphView';
import { TabProgressSnapshot } from './TabProgressSnapshot';
import { IMSAIAssistant } from './IMSAIAssistant';
import type { IMSSearchTab, ViewMode, IMSIssue } from '../types';

interface IMSSearchResultsProps {
  tab: IMSSearchTab;
  onViewModeChange: (mode: ViewMode) => void;
  onIssueClick?: (issue: IMSIssue) => void;
  t: (key: string) => string;
}

export const IMSSearchResults: React.FC<IMSSearchResultsProps> = ({
  tab,
  onViewModeChange,
  onIssueClick,
  t,
}) => {
  const { results, viewMode, completionStats } = tab;
  const [isAssistantOpen, setIsAssistantOpen] = useState(true);

  const handleOpenAssistant = useCallback(() => {
    setIsAssistantOpen(true);
  }, []);

  const handleCloseAssistant = useCallback(() => {
    setIsAssistantOpen(false);
  }, []);

  const viewModeButtons: { mode: ViewMode; icon: React.ReactNode; label: string }[] = [
    { mode: 'table', icon: <Table size={16} />, label: t('ims.results.table') },
    { mode: 'cards', icon: <LayoutGrid size={16} />, label: t('ims.results.cards') },
    { mode: 'graph', icon: <GitBranch size={16} />, label: t('ims.results.graph') },
  ];

  return (
    <div className="ims-results">
      {/* Header */}
      <div className="ims-results__header">
        <div className="ims-results__info">
          <span className="ims-results__count">
            {results.length} {t('ims.results.issues')}
          </span>
          <span className="ims-results__query">"{tab.query}"</span>
        </div>

        {/* View Mode Selector & AI Assistant Button */}
        <div className="ims-results__actions">
          <div className="ims-results__view-modes">
            {viewModeButtons.map(({ mode, icon, label }) => (
              <button
                key={mode}
                className={`ims-results__view-btn ${viewMode === mode ? 'active' : ''}`}
                onClick={() => onViewModeChange(mode)}
                title={label}
              >
                {icon}
                <span className="ims-results__view-label">{label}</span>
              </button>
            ))}
          </div>

          {/* AI Assistant Toggle Button */}
          {!isAssistantOpen && (
            <button
              className="ims-results__ai-btn"
              onClick={handleOpenAssistant}
              title={t('ims.chat.openAssistant')}
            >
              <Sparkles size={18} />
              <span>{t('ims.chat.title')}</span>
            </button>
          )}
        </div>
      </div>

      {/* Completion Stats */}
      {completionStats && (
        <TabProgressSnapshot stats={completionStats} t={t} />
      )}

      {/* Results View */}
      <div className="ims-results__content">
        {results.length === 0 ? (
          <div className="ims-results__empty">
            <p>{t('ims.results.noResults')}</p>
          </div>
        ) : (
          <>
            {viewMode === 'table' && (
              <IMSTableView issues={results} onIssueClick={onIssueClick} t={t} />
            )}
            {viewMode === 'cards' && (
              <IMSCardView issues={results} onIssueClick={onIssueClick} t={t} />
            )}
            {viewMode === 'graph' && (
              <IMSGraphView issues={results} onIssueClick={onIssueClick} t={t} />
            )}
          </>
        )}
      </div>

      {/* AI Assistant Panel */}
      <IMSAIAssistant
        issues={results}
        isOpen={isAssistantOpen}
        onClose={handleCloseAssistant}
        t={t}
      />
    </div>
  );
};

export default IMSSearchResults;
