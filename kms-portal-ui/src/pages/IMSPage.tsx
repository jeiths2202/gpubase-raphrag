/**
 * IMS Knowledge Service Page
 *
 * Main page for IMS crawler with tab-based UI
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X, CheckCircle, Clock, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from '../hooks/useTranslation';
import { useAuthStore } from '../store/authStore';
import {
  IMSCredentialsSetup,
  IMSSearchBar,
  IMSSearchResults,
  IMSProgressTracker,
  useIMSStore,
} from '../features/ims';
import type { IMSJob, CompletionStats, ViewMode, IMSIssue } from '../features/ims';
import './IMSPage.css';

const SEARCH_TAB_ID = 'search';

// IMS Issue View URL template
const IMS_ISSUE_VIEW_URL = 'https://ims.tmaxsoft.com/tody/ims/issue/issueView.do';

/**
 * Open IMS issue detail page in a popup window
 */
const openIssuePopup = (imsId: string): void => {
  const url = `${IMS_ISSUE_VIEW_URL}?issueId=${imsId}&menuCode=issue_search`;
  const popupWidth = 1200;
  const popupHeight = 800;
  const left = (window.screen.width - popupWidth) / 2;
  const top = (window.screen.height - popupHeight) / 2;

  window.open(
    url,
    `ims_issue_${imsId}`,
    `width=${popupWidth},height=${popupHeight},left=${left},top=${top},resizable=yes,scrollbars=yes,status=yes`
  );
};

export const IMSPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { logout } = useAuthStore();

  // Store state
  const {
    hasCredentials,
    credentialsValidated,
    isSearching,
    currentJob,
    searchTabs,
    activeTabId,
    checkCredentials,
    setIsSearching,
    fetchResults,
    setActiveTab,
    removeSearchTab,
    updateTabViewMode,
    resetSearch,
  } = useIMSStore();

  // Local state
  const [showCredentialsModal, setShowCredentialsModal] = useState(false);

  // Refs to prevent infinite loops
  const initialCredentialsCheckRef = useRef(false);
  const completionHandledRef = useRef(false);
  const previousTabCountRef = useRef(searchTabs.length);

  // Check credentials on mount (once only)
  useEffect(() => {
    if (initialCredentialsCheckRef.current) return;
    initialCredentialsCheckRef.current = true;

    checkCredentials().then(() => {
      const state = useIMSStore.getState();
      if (!state.hasCredentials || !state.credentialsValidated) {
        setShowCredentialsModal(true);
      }
    });
  }, [checkCredentials]);

  // Auto-close credentials modal when search starts
  useEffect(() => {
    if (isSearching && showCredentialsModal) {
      setShowCredentialsModal(false);
    }
  }, [isSearching, showCredentialsModal]);

  // Auto-switch to new result tab
  useEffect(() => {
    if (searchTabs.length > previousTabCountRef.current) {
      // New tab added, switch to it
      const newTab = searchTabs[searchTabs.length - 1];
      setActiveTab(newTab.id);
    }
    previousTabCountRef.current = searchTabs.length;
  }, [searchTabs, setActiveTab]);

  // Reset completion flag when new job starts
  useEffect(() => {
    if (currentJob) {
      completionHandledRef.current = false;
    }
  }, [currentJob]);

  // Handle job creation
  const handleJobCreated = useCallback((job: IMSJob) => {
    // Job is now being tracked, progress will be shown
    console.log('[IMS] Job created:', job.id);
  }, []);

  // Handle job completion
  const handleJobComplete = useCallback(
    (stats: CompletionStats) => {
      if (completionHandledRef.current) return;
      completionHandledRef.current = true;

      const query = useIMSStore.getState().searchQuery;
      fetchResults(query, stats);
    },
    [fetchResults]
  );

  // Handle job error
  const handleJobError = useCallback(
    (error: string) => {
      console.error('[IMS] Job error:', error);
      setIsSearching(false);
      resetSearch();
    },
    [setIsSearching, resetSearch]
  );

  // Handle view results from progress tracker
  const handleViewResults = useCallback(() => {
    // Results tab should already be active after completion
    // This is just a fallback
    if (searchTabs.length > 0) {
      setActiveTab(searchTabs[searchTabs.length - 1].id);
    }
  }, [searchTabs, setActiveTab]);

  // Handle tab close
  const handleCloseTab = useCallback(
    (e: React.MouseEvent, tabId: string) => {
      e.stopPropagation();
      removeSearchTab(tabId);
    },
    [removeSearchTab]
  );

  // Handle view mode change
  const handleViewModeChange = useCallback(
    (mode: ViewMode) => {
      if (activeTabId && activeTabId !== SEARCH_TAB_ID) {
        updateTabViewMode(activeTabId, mode);
      }
    },
    [activeTabId, updateTabViewMode]
  );

  // Handle logout
  const handleLogout = useCallback(async () => {
    await logout();
    navigate('/login');
  }, [logout, navigate]);

  // Handle issue click - open IMS issue in popup
  const handleIssueClick = useCallback((issue: IMSIssue) => {
    openIssuePopup(issue.ims_id);
  }, []);

  // Get active tab data
  const activeTab = searchTabs.find((tab) => tab.id === activeTabId);
  const isSearchTabActive = activeTabId === SEARCH_TAB_ID || !activeTabId;

  // Format duration for tab badge
  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    return `${Math.floor(seconds / 60)}m`;
  };

  return (
    <div className="ims-page">
      {/* Credentials Modal */}
      <IMSCredentialsSetup
        isOpen={showCredentialsModal}
        onClose={() => setShowCredentialsModal(false)}
        t={t}
      />

      {/* Header */}
      <header className="ims-page__header">
        <div className="ims-page__header-content">
          <h1 className="ims-page__title">{t('ims.title')}</h1>
          <p className="ims-page__subtitle">{t('ims.subtitle')}</p>
        </div>

        <div className="ims-page__header-actions">
          {/* Credentials status */}
          {hasCredentials && credentialsValidated && (
            <div className="ims-page__credentials-status">
              <CheckCircle size={14} />
              <span>{t('ims.credentials.connected')}</span>
            </div>
          )}

          {/* Logout button */}
          <button
            className="ims-page__logout-btn"
            onClick={handleLogout}
            title={t('auth.logout')}
          >
            <LogOut size={18} />
            <span>{t('auth.logout')}</span>
          </button>
        </div>
      </header>

      {/* Tab Navigation */}
      <nav className="ims-tabs">
        {/* Search Tab */}
        <button
          className={`ims-tab ${isSearchTabActive ? 'active' : ''}`}
          onClick={() => setActiveTab(SEARCH_TAB_ID)}
        >
          <Search size={16} />
          <span>{t('ims.tabs.search')}</span>
        </button>

        {/* Result Tabs */}
        {searchTabs.map((tab) => (
          <div
            key={tab.id}
            role="tab"
            tabIndex={0}
            className={`ims-tab ims-tab--result ${activeTabId === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(e) => e.key === 'Enter' && setActiveTab(tab.id)}
          >
            <span className="ims-tab__query" title={tab.query}>
              {tab.query.length > 20 ? tab.query.substring(0, 20) + '...' : tab.query}
            </span>
            {/* Show actual results count instead of crawled count */}
            <span className="ims-tab__badge">
              {tab.results.length}
            </span>
            {tab.completionStats && (
              <span className="ims-tab__duration">
                <Clock size={12} />
                {formatDuration(tab.completionStats.duration)}
              </span>
            )}
            <button
              className="ims-tab__close"
              onClick={(e) => handleCloseTab(e, tab.id)}
              aria-label="Close tab"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </nav>

      {/* Main Content */}
      <main className="ims-page__content">
        {/* Search Tab Content */}
        {isSearchTabActive && (
          <div className="ims-page__search-content">
            {/* Search Bar */}
            <IMSSearchBar onJobCreated={handleJobCreated} t={t} />

            {/* Progress Tracker */}
            {isSearching && currentJob && (
              <IMSProgressTracker
                jobId={currentJob.id}
                onComplete={handleJobComplete}
                onError={handleJobError}
                onViewResults={handleViewResults}
                t={t}
              />
            )}

            {/* Empty State */}
            {!isSearching && searchTabs.length === 0 && (
              <div className="ims-page__empty">
                <Search size={64} className="ims-page__empty-icon" />
                <h2>{t('ims.empty.title')}</h2>
                <p>{t('ims.empty.description')}</p>
              </div>
            )}
          </div>
        )}

        {/* Result Tab Content */}
        {!isSearchTabActive && activeTab && (
          <IMSSearchResults
            tab={activeTab}
            onViewModeChange={handleViewModeChange}
            onIssueClick={handleIssueClick}
            t={t}
          />
        )}
      </main>
    </div>
  );
};

export default IMSPage;
