/**
 * IMS Crawler Page - Main page for IMS Knowledge Service
 *
 * Features:
 * - Credentials setup and validation
 * - Natural language search with real-time progress
 * - Multiple view modes (Table, Cards, Graph)
 * - SSE streaming for crawl job progress
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'framer-motion';
import { useIMSStore } from '../store/imsStore';
import { IMSCredentialsSetup } from '../components/IMSCredentialsSetup';
import { IMSSearchBar } from '../components/IMSSearchBar';
import { IMSSearchResults } from '../components/IMSSearchResults';
import { IMSEnhancedProgressTracker } from '../components/progress';
import { TabProgressSnapshot } from '../components/TabProgressSnapshot';
import type { TranslateFunction } from '../../../i18n/types';
import type { CompletionStats } from '../types/progress';

interface IMSCrawlerPageProps {
  t: TranslateFunction;
}

export const IMSCrawlerPage: React.FC<IMSCrawlerPageProps> = ({ t }) => {
  const {
    hasCredentials,
    credentialsValidated,
    isSearching,
    currentJob,
    setIsSearching,
    checkCredentials,
    fetchResults,
    searchQuery,
    searchTabs,
    activeTabId,
    setActiveTab,
    removeSearchTab,
    updateTabViewMode,
    getActiveTab
  } = useIMSStore();

  const [showCredentialsSetup, setShowCredentialsSetup] = useState(false);
  const [currentTabType, setCurrentTabType] = useState<'search' | 'results'>('search');
  const completionHandledRef = useRef(false);
  const hasSearchedRef = useRef(false); // Track if user has ever searched
  const initialCredentialsCheckRef = useRef(false); // Track initial credentials check

  /**
   * Handle job completion
   * CRITICAL FIX: Pass completion stats directly to fetchResults with error handling
   */
  const handleJobComplete = useCallback(async (stats: CompletionStats) => {
    // Prevent duplicate completion handling
    if (completionHandledRef.current) {
      return;
    }

    try {
      completionHandledRef.current = true;

      // Automatically fetch results when job completes successfully
      // Pass completion stats directly to create tab with all data
      if (stats.outcome === 'success' || stats.outcome === 'partial') {
        // Prepare completion stats for tab
        const completionStats = {
          totalIssues: stats.totalIssues,
          successfulIssues: stats.successfulIssues,
          duration: stats.duration,
          outcome: stats.outcome,
          relatedIssues: stats.relatedIssues,
          attachments: stats.attachments,
          failedIssues: stats.failedIssues,
          progressSnapshot: stats.progressSnapshot
        };

        await fetchResults(searchQuery, completionStats);
      }
    } catch (error) {
      console.error('Error in handleJobComplete:', error);
      completionHandledRef.current = false; // Reset on error
    }
  }, [fetchResults, searchQuery]);

  /**
   * Handle job errors
   */
  const handleJobError = useCallback((error: string) => {
    console.error('Crawl job error:', error);
    setIsSearching(false);
    completionHandledRef.current = false; // Reset on error
  }, [setIsSearching]);

  /**
   * Handle "View Results" button click
   */
  const handleViewResults = useCallback(async () => {
    await fetchResults(searchQuery);
  }, [fetchResults, searchQuery]);

  /**
   * Reset completion flag when starting new search
   * Also close credentials modal and mark as searched
   */
  useEffect(() => {
    if (currentJob) {
      console.log('🚀 Search started, job:', currentJob.id);
      completionHandledRef.current = false;
      hasSearchedRef.current = true; // User has started a search

      // Close credentials modal when search starts
      if (showCredentialsSetup) {
        console.log('🔓 Closing credentials modal - search in progress');
        setShowCredentialsSetup(false);
      }
    }
  }, [currentJob, showCredentialsSetup]);

  /**
   * Switch to results tab when new tab is added
   * CRITICAL: Only switch when tab count increases (new tab added)
   */
  const previousTabCountRef = useRef(0);
  useEffect(() => {
    const previousCount = previousTabCountRef.current;
    const currentCount = searchTabs.length;

    // Only act if tab count INCREASED (new tab added)
    if (currentCount > previousCount && currentCount > 0 && activeTabId) {
      // Close credentials modal if open
      if (showCredentialsSetup) {
        setShowCredentialsSetup(false);
      }

      // Switch to results tab
      setCurrentTabType('results');
    }

    // Update previous count
    previousTabCountRef.current = currentCount;
  }, [searchTabs.length, activeTabId, showCredentialsSetup]);

  useEffect(() => {
    // Check if user has credentials on mount
    checkCredentials();
  }, [checkCredentials]);

  // Show credentials setup if no credentials or not validated
  // CRITICAL: Only check ONCE on initial mount, never during updates
  useEffect(() => {
    // Skip if already checked
    if (initialCredentialsCheckRef.current) {
      return;
    }

    // Mark as checked
    initialCredentialsCheckRef.current = true;

    // Only show setup if no credentials and not currently active
    if ((!hasCredentials || !credentialsValidated) &&
        !isSearching &&
        searchTabs.length === 0) {
      setShowCredentialsSetup(true);
    }
  }, [hasCredentials, credentialsValidated, isSearching, searchTabs.length]);

  /**
   * Handle tab selection
   */
  const handleTabSelect = (tabType: 'search' | 'results', tabId?: string) => {
    setCurrentTabType(tabType);
    if (tabType === 'results' && tabId) {
      setActiveTab(tabId);
    }
  };

  /**
   * Handle tab close
   */
  const handleTabClose = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    removeSearchTab(tabId);
    if (searchTabs.length === 1) {
      // Last tab being closed, switch to search
      setCurrentTabType('search');
    }
  };

  /**
   * Get active tab data
   */
  const activeTab = getActiveTab();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        padding: '24px',
        gap: '20px',
        height: '100%',
        overflowY: 'auto',
        overflowX: 'hidden'
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 700 }}>
            IMS Knowledge Service
          </h1>
          <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)', fontSize: '14px' }}>
            Search and analyze IMS issues using natural language
          </p>
        </div>

        {hasCredentials && (
          <button
            onClick={() => setShowCredentialsSetup(true)}
            style={{
              padding: '8px 16px',
              background: 'transparent',
              border: '1px solid var(--border)',
              borderRadius: '6px',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            ⚙️ Manage Credentials
          </button>
        )}
      </div>

      {/* Credentials Setup Modal */}
      {showCredentialsSetup && (
        <IMSCredentialsSetup
          t={t}
          onClose={() => setShowCredentialsSetup(false)}
          onSuccess={() => {
            setShowCredentialsSetup(false);
            checkCredentials();
          }}
        />
      )}

      {/* Main Content - ALWAYS SHOW TABS */}
      {!showCredentialsSetup && (
        <>
          {/* Tab Bar */}
          <div
            data-testid="tab-bar"
            style={{
              display: 'flex',
              gap: '10px',
              borderBottom: '3px solid var(--accent)',
              marginBottom: '16px',
              paddingBottom: '12px',
              overflowX: 'auto',
              overflowY: 'hidden',
              position: 'sticky',
              top: 0,
              zIndex: 100,
              background: 'linear-gradient(to bottom, var(--bg-secondary) 0%, var(--card-bg) 100%)',
              paddingTop: '16px',
              paddingLeft: '16px',
              paddingRight: '16px',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.25), 0 2px 8px rgba(0, 0, 0, 0.15)',
              borderRadius: '0',
              borderTop: '2px solid var(--border)',
              minHeight: '70px',
              alignItems: 'center'
            }}
          >
            {/* Search Tab (always present) */}
            <button
              onClick={() => handleTabSelect('search')}
              style={{
                padding: '14px 24px',
                background: currentTabType === 'search'
                  ? 'linear-gradient(135deg, var(--accent) 0%, var(--accent-dark, #2563eb) 100%)'
                  : 'white',
                border: currentTabType === 'search'
                  ? '3px solid var(--accent)'
                  : '2px solid #d1d5db',
                borderRadius: '10px 10px 0 0',
                color: currentTabType === 'search' ? 'white' : '#111827',
                cursor: 'pointer',
                fontSize: '15px',
                fontWeight: currentTabType === 'search' ? 700 : 700,
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                boxShadow: currentTabType === 'search'
                  ? '0 6px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.2)'
                  : '0 2px 8px rgba(0, 0, 0, 0.1)',
                minHeight: '48px'
              }}
            >
              <span style={{ fontSize: '14px' }}>🔍</span>
              <span>Search</span>
            </button>

            {/* Result Tabs */}
            {searchTabs.map((tab) => {
              const isActive = currentTabType === 'results' && activeTabId === tab.id;
              const outcomeColor = tab.completionStats?.outcome === 'success' ? '#10b981'
                : tab.completionStats?.outcome === 'partial' ? '#f59e0b'
                : '#ef4444';

              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabSelect('results', tab.id)}
                  style={{
                    padding: '12px 18px',
                    background: isActive
                      ? 'linear-gradient(135deg, var(--accent) 0%, var(--accent-dark, #2563eb) 100%)'
                      : 'white',
                    border: isActive
                      ? '3px solid var(--accent)'
                      : '2px solid #d1d5db',
                    borderRadius: '10px 10px 0 0',
                    color: isActive ? 'white' : '#111827',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: isActive ? 700 : 700,
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    gap: '6px',
                    minWidth: '170px',
                    maxWidth: '230px',
                    minHeight: '48px',
                    position: 'relative',
                    boxShadow: isActive
                      ? '0 6px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.2)'
                      : '0 2px 8px rgba(0, 0, 0, 0.1)'
                  }}
                >
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    gap: '8px'
                  }}>
                    <span style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      flex: 1,
                      fontWeight: 500
                    }}>
                      {tab.query}
                    </span>
                    <span
                      onClick={(e) => handleTabClose(tab.id, e)}
                      style={{
                        fontSize: '16px',
                        opacity: 0.6,
                        transition: 'opacity 0.2s',
                        cursor: 'pointer',
                        lineHeight: 1,
                        color: isActive ? 'white' : 'var(--text-primary)'
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                      onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'}
                    >
                      ×
                    </span>
                  </div>

                  {tab.completionStats && (
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '10px',
                      opacity: isActive ? 0.9 : 0.7,
                      color: isActive ? 'white' : 'var(--text-secondary)'
                    }}>
                      <span>{tab.completionStats.successfulIssues}</span>
                      <span style={{
                        width: '4px',
                        height: '4px',
                        borderRadius: '50%',
                        background: outcomeColor
                      }}></span>
                      <span>{Math.round(tab.completionStats.duration)}s</span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Tab Content */}
          {currentTabType === 'search' ? (
            <>
              {/* Search Bar */}
              <IMSSearchBar />

              {/* Enhanced Progress Tracker - Show during crawling */}
              {isSearching && currentJob && (
                <IMSEnhancedProgressTracker
                  jobId={currentJob.id}
                  onComplete={handleJobComplete}
                  onError={handleJobError}
                  onViewResults={handleViewResults}
                />
              )}

              {/* Empty State */}
              {!isSearching && (
                <div style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '16px',
                  color: 'var(--text-secondary)'
                }}>
                  <div style={{ fontSize: '48px' }}>🔍</div>
                  <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
                    Search IMS Issues
                  </h3>
                  <p style={{ margin: 0, fontSize: '14px', textAlign: 'center', maxWidth: '400px' }}>
                    Enter a natural language query to search for IMS issues.
                    <br />
                    Example: "Show me critical bugs from last week"
                  </p>
                </div>
              )}
            </>
          ) : activeTab ? (
            /* Search Results Tab */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
              {/* Tab Summary Card */}
              {activeTab.completionStats && (
                <div style={{
                  background: 'var(--card-bg)',
                  border: '1px solid var(--border)',
                  borderRadius: '12px',
                  padding: '16px 20px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.05)'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                        Query
                      </span>
                      <span style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)' }}>
                        "{activeTab.query}"
                      </span>
                    </div>

                    <div style={{
                      width: '1px',
                      height: '40px',
                      background: 'var(--border)'
                    }}></div>

                    <div style={{ display: 'flex', gap: '20px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                          Total Issues
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: 'var(--accent)' }}>
                          {activeTab.completionStats.totalIssues}
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                          Crawled
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: '#10b981' }}>
                          {activeTab.completionStats.successfulIssues}
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                          Duration
                        </span>
                        <span style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>
                          {Math.round(activeTab.completionStats.duration)}s
                        </span>
                      </div>

                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 500 }}>
                          Status
                        </span>
                        <span style={{
                          fontSize: '14px',
                          fontWeight: 700,
                          color: activeTab.completionStats.outcome === 'success' ? '#10b981'
                            : activeTab.completionStats.outcome === 'partial' ? '#f59e0b'
                            : '#ef4444',
                          textTransform: 'uppercase'
                        }}>
                          {activeTab.completionStats.outcome === 'success' ? '✓ Success'
                            : activeTab.completionStats.outcome === 'partial' ? '⚠ Partial'
                            : '✗ Failed'}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div style={{
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}>
                    <span>🕒</span>
                    <span>{new Date(activeTab.timestamp).toLocaleString()}</span>
                  </div>
                </div>
              )}

              {/* Progress Snapshot */}
              {activeTab.completionStats?.progressSnapshot && (
                <TabProgressSnapshot progressSnapshot={activeTab.completionStats.progressSnapshot} />
              )}

              {/* Search Results */}
              <IMSSearchResults
                results={activeTab.results}
                viewMode={activeTab.viewMode}
                onViewModeChange={(mode) => updateTabViewMode(activeTab.id, mode)}
              />
            </div>
          ) : null}
        </>
      )}

      {/* Credentials Required State */}
      {(!hasCredentials || !credentialsValidated) && !showCredentialsSetup && (
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px'
        }}>
          <div style={{ fontSize: '48px' }}>🔐</div>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
            IMS Credentials Required
          </h3>
          <p style={{ margin: 0, fontSize: '14px', color: 'var(--text-secondary)', textAlign: 'center', maxWidth: '400px' }}>
            Please set up your IMS credentials to start searching issues.
          </p>
          <button
            onClick={() => setShowCredentialsSetup(true)}
            style={{
              padding: '12px 24px',
              background: 'var(--accent)',
              border: 'none',
              borderRadius: '8px',
              color: 'white',
              fontSize: '14px',
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Set Up Credentials
          </button>
        </div>
      )}
    </motion.div>
  );
};

export default IMSCrawlerPage;
