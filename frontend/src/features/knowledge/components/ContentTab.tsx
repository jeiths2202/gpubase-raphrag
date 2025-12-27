// ContentTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion } from 'framer-motion';
import type { ThemeColors, ContentItem } from '../types';
import { TranslateFunction } from '../../../i18n/types';

interface ContentTabProps {
  // State
  selectedDocuments: string[];
  contents: ContentItem[];
  generatingContent: boolean;
  selectedContent: ContentItem | null;
  contentData: any;

  // State setters
  setSelectedContent: (content: ContentItem | null) => void;

  // Functions
  generateContent: (contentType: string) => void;
  loadContentDetail: (contentId: string) => void;

  // Styles
  themeColors: ThemeColors;
  cardStyle: React.CSSProperties;

  // i18n
  t: TranslateFunction;
}

export const ContentTab: React.FC<ContentTabProps> = ({
  selectedDocuments,
  contents,
  generatingContent,
  selectedContent,
  contentData,
  setSelectedContent,
  generateContent,
  loadContentDetail,
  themeColors,
  cardStyle,
  t
}) => {
  return (
    <motion.div
      key="content"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1 }}
    >
      <div style={cardStyle}>
        <h2>AI Content Generation</h2>
        <p style={{ color: themeColors.textSecondary }}>
          {t('knowledge.content.subtitle' as keyof import('../../../i18n/types').TranslationKeys, { count: selectedDocuments.length })}
        </p>

        {/* Content Type Buttons */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '12px', marginTop: '20px' }}>
          {[
            { type: 'summary', labelKey: 'summary', icon: '📝' },
            { type: 'faq', labelKey: 'faq', icon: '❓' },
            { type: 'study_guide', labelKey: 'studyGuide', icon: '📚' },
            { type: 'briefing', labelKey: 'briefing', icon: '📋' },
            { type: 'timeline', labelKey: 'timeline', icon: '📅' },
            { type: 'toc', labelKey: 'toc', icon: '📑' },
            { type: 'key_topics', labelKey: 'keyTopics', icon: '🎯' }
          ].map(ct => (
            <button
              key={ct.type}
              onClick={() => generateContent(ct.type)}
              disabled={generatingContent || selectedDocuments.length === 0}
              style={{
                ...cardStyle,
                cursor: generatingContent ? 'not-allowed' : 'pointer',
                textAlign: 'center',
                opacity: generatingContent || selectedDocuments.length === 0 ? 0.5 : 1
              }}
            >
              <div style={{ fontSize: '32px' }}>{ct.icon}</div>
              <div style={{ marginTop: '8px', fontWeight: 600 }}>{t(`knowledge.content.types.${ct.labelKey}` as keyof import('../../../i18n/types').TranslationKeys)}</div>
            </button>
          ))}
        </div>

        {generatingContent && (
          <div style={{ textAlign: 'center', marginTop: '20px', color: themeColors.accent }}>
            {t('knowledge.content.generating' as keyof import('../../../i18n/types').TranslationKeys)}
          </div>
        )}
      </div>

      {/* Generated Contents List */}
      <div style={{ ...cardStyle, marginTop: '20px' }}>
        <h3>Generated Contents</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '12px', marginTop: '16px' }}>
          {contents.map(content => (
            <div
              key={content.id}
              onClick={() => {
                setSelectedContent(content);
                loadContentDetail(content.id);
              }}
              style={{
                ...cardStyle,
                cursor: 'pointer',
                border: selectedContent?.id === content.id
                  ? `2px solid ${themeColors.accent}`
                  : `1px solid ${themeColors.cardBorder}`
              }}
            >
              <div style={{ fontWeight: 600 }}>{content.title}</div>
              <div style={{ fontSize: '12px', color: themeColors.textSecondary }}>
                {content.content_type} | {content.status}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Content Detail */}
      {contentData && (
        <div style={{ ...cardStyle, marginTop: '20px' }}>
          <h3>{contentData.title}</h3>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>
            {JSON.stringify(contentData, null, 2)}
          </pre>
        </div>
      )}
    </motion.div>
  );
};

export default ContentTab;
