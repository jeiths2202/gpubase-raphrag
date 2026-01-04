/**
 * IMS Crawler Page - Main page for IMS Knowledge Service
 *
 * Features:
 * - Credentials setup and validation
 * - Natural language search with real-time progress
 * - Multiple view modes (Table, Cards, Graph)
 * - SSE streaming for crawl job progress
 */

import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useIMSStore } from '../store/imsStore';
import { IMSCredentialsSetup } from '../components/IMSCredentialsSetup';
import { IMSSearchBar } from '../components/IMSSearchBar';
import { IMSSearchResults } from '../components/IMSSearchResults';
import { IMSProgressIndicator } from '../components/IMSProgressIndicator';
import type { TranslateFunction } from '../../../i18n/types';

interface IMSCrawlerPageProps {
  t: TranslateFunction;
}

export const IMSCrawlerPage: React.FC<IMSCrawlerPageProps> = ({ t }) => {
  const {
    hasCredentials,
    credentialsValidated,
    isSearching,
    searchResults,
    currentJob,
    viewMode,
    setViewMode,
    checkCredentials
  } = useIMSStore();

  const [showCredentialsSetup, setShowCredentialsSetup] = useState(false);

  useEffect(() => {
    // Check if user has credentials on mount
    checkCredentials();
  }, [checkCredentials]);

  // Show credentials setup if no credentials or not validated
  useEffect(() => {
    if (!hasCredentials || !credentialsValidated) {
      setShowCredentialsSetup(true);
    }
  }, [hasCredentials, credentialsValidated]);

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
        overflow: 'auto'
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

      {/* Main Content - Only show if credentials are validated */}
      {hasCredentials && credentialsValidated && !showCredentialsSetup && (
        <>
          {/* Search Bar */}
          <IMSSearchBar t={t} />

          {/* Progress Indicator - Show during crawling */}
          {isSearching && currentJob && (
            <IMSProgressIndicator job={currentJob} t={t} />
          )}

          {/* Search Results */}
          {searchResults.length > 0 && (
            <IMSSearchResults
              results={searchResults}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              t={t}
            />
          )}

          {/* Empty State */}
          {!isSearching && searchResults.length === 0 && (
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
