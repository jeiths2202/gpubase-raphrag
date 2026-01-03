// WebSourcesTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ThemeColors, WebSource } from '../types';
import { TranslateFunction } from '../../../i18n/types';
import { defaultThemeColors, defaultCardStyle, defaultTabStyle, defaultInputStyle } from '../utils/styleDefaults';

interface WebSourcesTabProps {
  // State
  webSources: WebSource[];
  showAddUrlModal: boolean;
  newUrls: string;
  webSourceTags: string[];
  addingUrls: boolean;

  // State setters
  setShowAddUrlModal: (show: boolean) => void;
  setNewUrls: (urls: string) => void;
  setWebSourceTags: (tags: string[]) => void;

  // Functions
  addWebSources: () => void;
  refreshWebSource: (id: string) => void;
  deleteWebSource: (id: string) => void;

  // Styles (optional - CSS classes used by default)
  themeColors?: ThemeColors;
  cardStyle?: React.CSSProperties;
  tabStyle?: (isActive: boolean) => React.CSSProperties;
  inputStyle?: React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const WebSourcesTab: React.FC<WebSourcesTabProps> = ({
  webSources,
  showAddUrlModal,
  newUrls,
  webSourceTags,
  addingUrls,
  setShowAddUrlModal,
  setNewUrls,
  setWebSourceTags,
  addWebSources,
  refreshWebSource,
  deleteWebSource,
  themeColors,
  cardStyle,
  tabStyle,
  inputStyle,
  t
}) => {
  // Use defaults when style props are not provided
  const actualThemeColors = themeColors || defaultThemeColors;
  const actualCardStyle = cardStyle || defaultCardStyle;
  const actualTabStyle = tabStyle || defaultTabStyle;
  const actualInputStyle = inputStyle || defaultInputStyle;

  return (
    <motion.div
      key="web-sources"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1 }}
    >
      <div style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <div>
            <h2 style={{ margin: 0 }}>🌐 Web Sources</h2>
            <p style={{ color: actualThemeColors.textSecondary, margin: '8px 0 0' }}>
              {t('knowledge.webSources.subtitle' as keyof import('../../../i18n/types').TranslationKeys)}
            </p>
          </div>
          <button
            onClick={() => setShowAddUrlModal(true)}
            style={{ ...actualTabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            ➕ Add URL
          </button>
        </div>

        {/* Web Sources Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
          {webSources.map(ws => (
            <div
              key={ws.id}
              style={{
                ...actualCardStyle,
                border: `1px solid ${actualThemeColors.cardBorder}`,
                display: 'flex',
                flexDirection: 'column',
                gap: '12px'
              }}
            >
              <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                <div style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '8px',
                  background: ws.status === 'ready' ? 'rgba(46, 204, 113, 0.2)' :
                             ws.status === 'error' ? 'rgba(231, 76, 60, 0.2)' :
                             'rgba(74, 144, 217, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '24px',
                  flexShrink: 0
                }}>
                  {ws.status === 'ready' ? '✅' :
                   ws.status === 'error' ? '❌' :
                   ws.status === 'pending' ? '⏳' : '🔄'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {ws.display_name || ws.metadata?.title || ws.domain}
                  </div>
                  <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary, marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    🔗 {ws.url}
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
                    <span style={{
                      fontSize: '10px',
                      padding: '2px 6px',
                      background: ws.status === 'ready' ? 'rgba(46, 204, 113, 0.3)' :
                                 ws.status === 'error' ? 'rgba(231, 76, 60, 0.3)' :
                                 'rgba(241, 196, 15, 0.3)',
                      color: ws.status === 'ready' ? '#2ECC71' :
                            ws.status === 'error' ? '#E74C3C' : '#F1C40F',
                      borderRadius: '4px'
                    }}>
                      {ws.status.toUpperCase()}
                    </span>
                    {ws.stats?.chunk_count > 0 && (
                      <span style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        background: 'rgba(155, 89, 182, 0.3)',
                        color: '#9B59B6',
                        borderRadius: '4px'
                      }}>
                        {ws.stats.chunk_count} chunks
                      </span>
                    )}
                    {ws.stats?.word_count > 0 && (
                      <span style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        background: 'rgba(52, 152, 219, 0.3)',
                        color: '#3498DB',
                        borderRadius: '4px'
                      }}>
                        {ws.stats.word_count.toLocaleString()} words
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {ws.error_message && (
                <div style={{ fontSize: '12px', color: '#E74C3C', background: 'rgba(231,76,60,0.1)', padding: '8px', borderRadius: '4px' }}>
                  {ws.error_message}
                </div>
              )}
              <div style={{ display: 'flex', gap: '8px', borderTop: `1px solid ${actualThemeColors.cardBorder}`, paddingTop: '12px' }}>
                <button
                  onClick={() => refreshWebSource(ws.id)}
                  style={{ ...actualTabStyle(false), flex: 1, fontSize: '12px' }}
                >
                  🔄 Refresh
                </button>
                <button
                  onClick={() => window.open(ws.url, '_blank')}
                  style={{ ...actualTabStyle(false), flex: 1, fontSize: '12px' }}
                >
                  🔗 Open
                </button>
                <button
                  onClick={() => deleteWebSource(ws.id)}
                  style={{ ...actualTabStyle(false), flex: 1, fontSize: '12px', color: '#E74C3C' }}
                >
                  🗑️ Delete
                </button>
              </div>
            </div>
          ))}
        </div>

        {webSources.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px', color: actualThemeColors.textSecondary }}>
            <div style={{ fontSize: '48px', marginBottom: '16px' }}>🌐</div>
            <p>No web sources added yet.</p>
            <p style={{ fontSize: '14px', marginTop: '8px' }}>Add web URLs to index their content for RAG queries.</p>
            <button
              onClick={() => setShowAddUrlModal(true)}
              style={{ ...actualTabStyle(true), marginTop: '16px' }}
            >
              Add your first URL
            </button>
          </div>
        )}
      </div>

      {/* Add URL Modal */}
      <AnimatePresence>
        {showAddUrlModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => setShowAddUrlModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              style={{ ...actualCardStyle, width: '500px', maxWidth: '90%' }}
              onClick={e => e.stopPropagation()}
            >
              <h3 style={{ margin: '0 0 16px' }}>🌐 Add Web URLs</h3>
              <p style={{ color: actualThemeColors.textSecondary, fontSize: '14px', marginBottom: '16px' }}>
                Enter one or more URLs (one per line) to fetch and index their content.
              </p>

              <textarea
                placeholder="https://example.com/article&#10;https://docs.example.com/guide"
                value={newUrls}
                onChange={e => setNewUrls(e.target.value)}
                style={{
                  ...actualInputStyle,
                  width: '100%',
                  minHeight: '120px',
                  resize: 'vertical',
                  fontFamily: 'monospace'
                }}
              />

              <div style={{ marginTop: '16px' }}>
                <label style={{ color: actualThemeColors.textSecondary, fontSize: '12px' }}>
                  Tags (optional, comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="docs, tutorial, api"
                  value={webSourceTags.join(', ')}
                  onChange={e => setWebSourceTags(e.target.value.split(',').map(t => t.trim()).filter(t => t))}
                  style={{ ...actualInputStyle, width: '100%', marginTop: '4px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                <button
                  onClick={() => setShowAddUrlModal(false)}
                  style={{ ...actualTabStyle(false), flex: 1 }}
                >
                  Cancel
                </button>
                <button
                  onClick={addWebSources}
                  disabled={!newUrls.trim() || addingUrls}
                  style={{
                    ...actualTabStyle(true),
                    flex: 1,
                    opacity: !newUrls.trim() || addingUrls ? 0.5 : 1,
                    cursor: !newUrls.trim() || addingUrls ? 'not-allowed' : 'pointer'
                  }}
                >
                  {addingUrls ? 'Adding...' : 'Add URLs'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default WebSourcesTab;
