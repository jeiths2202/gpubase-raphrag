// KnowledgeArticlesTab Component
// Extracted from KnowledgeApp.tsx - NO LOGIC CHANGES

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type {
  ThemeColors,
  KnowledgeArticle,
  KnowledgeStatus,
  KnowledgeCategory,
  SupportedLanguage,
  TopContributor,
  CategoryOption
} from '../types';
import { TranslateFunction } from '../../../i18n/types';
import { defaultThemeColors, defaultCardStyle, defaultTabStyle } from '../utils/styleDefaults';

interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  role: string;
  provider: 'email' | 'google' | 'sso';
}

interface KnowledgeArticlesTabProps {
  // State
  knowledgeArticles: KnowledgeArticle[];
  selectedArticle: KnowledgeArticle | null;
  pendingReviews: KnowledgeArticle[];
  topContributors: TopContributor[];
  categories: CategoryOption[];
  showCreateArticle: boolean;
  articleLanguage: SupportedLanguage;
  reviewComment: string;
  newArticle: { title: string; content: string; summary: string; category: KnowledgeCategory; tags: string[] };
  savingArticle: boolean;

  // State setters
  setSelectedArticle: (article: KnowledgeArticle | null) => void;
  setShowCreateArticle: (show: boolean) => void;
  setArticleLanguage: (lang: SupportedLanguage) => void;
  setReviewComment: (comment: string) => void;
  setNewArticle: React.Dispatch<React.SetStateAction<{ title: string; content: string; summary: string; category: KnowledgeCategory; tags: string[] }>>;

  // Functions
  getStatusColor: (status: KnowledgeStatus) => string;
  getStatusLabel: (status: KnowledgeStatus) => string;
  recommendArticle: (articleId: string) => void;
  reviewArticle: (articleId: string, action: 'approve' | 'reject' | 'request_changes') => Promise<void>;
  createKnowledgeArticle: () => void;

  // Styles (optional - CSS classes used by default)
  themeColors?: ThemeColors;
  cardStyle?: React.CSSProperties;
  tabStyle?: (isActive: boolean) => React.CSSProperties;

  // User context
  user: User | null;

  // i18n
  t: TranslateFunction;
}

export const KnowledgeArticlesTab: React.FC<KnowledgeArticlesTabProps> = ({
  knowledgeArticles,
  selectedArticle,
  pendingReviews,
  topContributors,
  categories,
  showCreateArticle,
  articleLanguage,
  reviewComment,
  newArticle,
  savingArticle,
  setSelectedArticle,
  setShowCreateArticle,
  setArticleLanguage,
  setReviewComment,
  setNewArticle,
  getStatusColor,
  getStatusLabel,
  recommendArticle,
  reviewArticle,
  createKnowledgeArticle,
  themeColors,
  cardStyle,
  tabStyle,
  user,
  t
}) => {
  // Use defaults when style props are not provided
  const actualThemeColors = themeColors || defaultThemeColors;
  const actualCardStyle = cardStyle || defaultCardStyle;
  const actualTabStyle = tabStyle || defaultTabStyle;

  return (
    <motion.div
      key="knowledge-articles"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      {/* Header */}
      <div style={actualCardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h2 style={{ margin: 0 }}>{t('knowledge.knowledgeBase.title' as keyof import('../../../i18n/types').TranslationKeys)}</h2>
            <p style={{ color: actualThemeColors.textSecondary, margin: '8px 0 0' }}>
              {t('knowledge.knowledgeBase.subtitle' as keyof import('../../../i18n/types').TranslationKeys)}
            </p>
          </div>
          <button
            onClick={() => setShowCreateArticle(true)}
            style={{ ...actualTabStyle(true), display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            {t('knowledge.knowledgeBase.newKnowledge' as keyof import('../../../i18n/types').TranslationKeys)}
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div style={{ display: 'flex', gap: '16px', flex: 1 }}>
        {/* Articles List */}
        <div style={{ ...cardStyle, flex: 1 }}>
          <h3 style={{ margin: '0 0 16px' }}>{t('knowledge.knowledgeBase.publishedKnowledge' as keyof import('../../../i18n/types').TranslationKeys)}</h3>

          {knowledgeArticles.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: actualThemeColors.textSecondary }}>
              <div style={{ fontSize: '48px', marginBottom: '16px' }}>📚</div>
              <p>{t('knowledge.knowledgeBase.noArticles' as keyof import('../../../i18n/types').TranslationKeys)}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {knowledgeArticles.map(article => (
                <div
                  key={article.id}
                  onClick={() => setSelectedArticle(article)}
                  style={{
                    padding: '16px',
                    background: selectedArticle?.id === article.id ? 'rgba(74,144,217,0.2)' : 'rgba(255,255,255,0.05)',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    border: selectedArticle?.id === article.id ? `2px solid ${actualThemeColors.accent}` : '1px solid transparent'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '16px' }}>{article.title}</div>
                      <div style={{ fontSize: '12px', color: actualThemeColors.textSecondary, marginTop: '4px' }}>
                        {article.author_name} | {article.category} | {new Date(article.created_at).toLocaleDateString()}
                      </div>
                      {article.summary && (
                        <div style={{ fontSize: '13px', color: actualThemeColors.textSecondary, marginTop: '8px' }}>
                          {article.summary}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                      <span style={{
                        padding: '4px 8px',
                        background: `${getStatusColor(article.status)}30`,
                        color: getStatusColor(article.status),
                        borderRadius: '4px',
                        fontSize: '11px'
                      }}>
                        {getStatusLabel(article.status)}
                      </span>
                      <div style={{ display: 'flex', gap: '12px', fontSize: '12px', color: actualThemeColors.textSecondary }}>
                        <span>👁️ {article.view_count}</span>
                        <span>👍 {article.recommendation_count}</span>
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '6px', marginTop: '8px', flexWrap: 'wrap' }}>
                    {article.tags.map((tag, i) => (
                      <span key={i} style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        background: 'rgba(74,144,217,0.2)',
                        borderRadius: '4px'
                      }}>
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div style={{ width: '300px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Pending Reviews (for reviewers only) */}
          {(user?.role === 'senior' || user?.role === 'leader' || user?.role === 'admin') && pendingReviews.length > 0 && (
            <div style={actualCardStyle}>
              <h3 style={{ margin: '0 0 12px', color: '#F39C12' }}>Pending Reviews ({pendingReviews.length})</h3>
              {pendingReviews.map(article => (
                <div
                  key={article.id}
                  onClick={() => setSelectedArticle(article)}
                  style={{
                    padding: '10px',
                    background: 'rgba(243,156,18,0.1)',
                    borderRadius: '6px',
                    marginBottom: '8px',
                    cursor: 'pointer'
                  }}
                >
                  <div style={{ fontWeight: 500, fontSize: '13px' }}>{article.title}</div>
                  <div style={{ fontSize: '11px', color: actualThemeColors.textSecondary }}>
                    by {article.author_name}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Top Contributors */}
          <div style={actualCardStyle}>
            <h3 style={{ margin: '0 0 12px' }}>{t('knowledge.knowledgeBase.topContributors' as keyof import('../../../i18n/types').TranslationKeys)}</h3>
            {topContributors.length === 0 ? (
              <div style={{ color: actualThemeColors.textSecondary, fontSize: '13px' }}>
                {t('knowledge.knowledgeBase.noContributors' as keyof import('../../../i18n/types').TranslationKeys)}
              </div>
            ) : (
              topContributors.map((contributor, idx) => (
                <div
                  key={contributor.user_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 0',
                    borderBottom: idx < topContributors.length - 1 ? `1px solid ${actualThemeColors.cardBorder}` : 'none'
                  }}
                >
                  <div style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    background: idx < 3 ? ['#FFD700', '#C0C0C0', '#CD7F32'][idx] : actualThemeColors.cardBg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '12px',
                    fontWeight: 600
                  }}>
                    {contributor.rank}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 500, fontSize: '13px' }}>{contributor.username}</div>
                    <div style={{ fontSize: '11px', color: actualThemeColors.textSecondary }}>
                      {contributor.article_count} {t('knowledge.knowledgeBase.articles' as keyof import('../../../i18n/types').TranslationKeys)} | {contributor.total_recommendations} {t('knowledge.knowledgeBase.recommendations' as keyof import('../../../i18n/types').TranslationKeys)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Categories */}
          <div style={actualCardStyle}>
            <h3 style={{ margin: '0 0 12px' }}>{t('knowledge.knowledgeBase.categories' as keyof import('../../../i18n/types').TranslationKeys)}</h3>
            {categories.map(cat => (
              <div
                key={cat.value}
                style={{
                  padding: '8px',
                  borderRadius: '6px',
                  marginBottom: '4px',
                  cursor: 'pointer',
                  background: 'rgba(255,255,255,0.05)'
                }}
              >
                {t(`knowledge.knowledgeBase.categoryNames.${cat.value}` as keyof import('../../../i18n/types').TranslationKeys)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Article Detail Modal */}
      <AnimatePresence>
        {selectedArticle && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => setSelectedArticle(null)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                ...cardStyle,
                width: '800px',
                maxWidth: '90vw',
                maxHeight: '90vh',
                overflow: 'auto'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
                <div>
                  <span style={{
                    padding: '4px 8px',
                    background: `${getStatusColor(selectedArticle.status)}30`,
                    color: getStatusColor(selectedArticle.status),
                    borderRadius: '4px',
                    fontSize: '11px',
                    marginBottom: '8px',
                    display: 'inline-block'
                  }}>
                    {getStatusLabel(selectedArticle.status)}
                  </span>
                  <h2 style={{ margin: '8px 0 0' }}>{selectedArticle.title}</h2>
                  <div style={{ fontSize: '13px', color: actualThemeColors.textSecondary, marginTop: '8px' }}>
                    {selectedArticle.author_name} {selectedArticle.author_department && `(${selectedArticle.author_department})`} | {new Date(selectedArticle.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => setSelectedArticle(null)}
                  style={{ background: 'transparent', border: 'none', color: actualThemeColors.text, fontSize: '24px', cursor: 'pointer' }}
                >
                  ×
                </button>
              </div>

              {/* Language Selector for Article */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                {(['ko', 'ja', 'en'] as SupportedLanguage[]).map(lang => (
                  <button
                    key={lang}
                    onClick={() => setArticleLanguage(lang)}
                    style={{
                      padding: '6px 12px',
                      border: 'none',
                      borderRadius: '4px',
                      background: articleLanguage === lang ? actualThemeColors.accent : 'rgba(255,255,255,0.1)',
                      color: articleLanguage === lang ? '#fff' : actualThemeColors.text,
                      cursor: 'pointer',
                      fontSize: '12px'
                    }}
                  >
                    {lang === 'ko' ? '한국어' : lang === 'ja' ? '日本語' : 'English'}
                  </button>
                ))}
              </div>

              {/* Article Content */}
              <div style={{
                padding: '20px',
                background: 'rgba(0,0,0,0.2)',
                borderRadius: '8px',
                marginBottom: '16px'
              }}>
                {selectedArticle.translations[articleLanguage] ? (
                  <div dangerouslySetInnerHTML={{ __html: selectedArticle.translations[articleLanguage].content }} />
                ) : (
                  <div dangerouslySetInnerHTML={{ __html: selectedArticle.content }} />
                )}
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  onClick={() => recommendArticle(selectedArticle.id)}
                  style={{
                    padding: '10px 20px',
                    background: 'rgba(46,204,113,0.2)',
                    border: 'none',
                    borderRadius: '6px',
                    color: '#2ECC71',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px'
                  }}
                >
                  👍 Recommend ({selectedArticle.recommendation_count})
                </button>

                <div style={{ marginLeft: 'auto', fontSize: '13px', color: actualThemeColors.textSecondary }}>
                  Views: {selectedArticle.view_count}
                </div>

                {/* Review Actions (for reviewers) */}
                {selectedArticle.status === 'in_review' && selectedArticle.reviewer_id === user?.id && (
                  <div style={{ display: 'flex', gap: '8px', marginLeft: '16px' }}>
                    <input
                      type="text"
                      value={reviewComment}
                      onChange={(e) => setReviewComment(e.target.value)}
                      placeholder="Review comment..."
                      style={{
                        padding: '8px 12px',
                        background: 'rgba(255,255,255,0.1)',
                        border: `1px solid ${actualThemeColors.cardBorder}`,
                        borderRadius: '6px',
                        color: actualThemeColors.text,
                        width: '200px'
                      }}
                    />
                    <button
                      onClick={() => reviewArticle(selectedArticle.id, 'approve')}
                      style={{ padding: '8px 16px', background: '#2ECC71', border: 'none', borderRadius: '6px', color: '#fff', cursor: 'pointer' }}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => reviewArticle(selectedArticle.id, 'reject')}
                      style={{ padding: '8px 16px', background: '#E74C3C', border: 'none', borderRadius: '6px', color: '#fff', cursor: 'pointer' }}
                    >
                      Reject
                    </button>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Create Article Modal */}
      <AnimatePresence>
        {showCreateArticle && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0,0,0,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 1000
            }}
            onClick={() => !savingArticle && setShowCreateArticle(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              style={{
                ...cardStyle,
                width: '700px',
                maxWidth: '90vw',
                maxHeight: '90vh',
                overflow: 'auto'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0 }}>Create New Knowledge</h2>
                <button
                  onClick={() => !savingArticle && setShowCreateArticle(false)}
                  disabled={savingArticle}
                  style={{ background: 'transparent', border: 'none', color: actualThemeColors.text, fontSize: '24px', cursor: 'pointer' }}
                >
                  ×
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Title *</label>
                  <input
                    type="text"
                    value={newArticle.title}
                    onChange={(e) => setNewArticle(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="Enter knowledge title..."
                    style={{
                      width: '100%',
                      padding: '12px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${actualThemeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: actualThemeColors.text,
                      fontSize: '16px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Category *</label>
                  <select
                    value={newArticle.category}
                    onChange={(e) => setNewArticle(prev => ({ ...prev, category: e.target.value as KnowledgeCategory }))}
                    style={{
                      width: '100%',
                      padding: '12px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${actualThemeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: actualThemeColors.text,
                      fontSize: '14px'
                    }}
                  >
                    {categories.map(cat => (
                      <option key={cat.value} value={cat.value}>{cat.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Summary</label>
                  <input
                    type="text"
                    value={newArticle.summary}
                    onChange={(e) => setNewArticle(prev => ({ ...prev, summary: e.target.value }))}
                    placeholder="Brief summary of the knowledge..."
                    style={{
                      width: '100%',
                      padding: '12px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${actualThemeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: actualThemeColors.text,
                      fontSize: '14px'
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px' }}>Content * (HTML/Markdown)</label>
                  <textarea
                    value={newArticle.content}
                    onChange={(e) => setNewArticle(prev => ({ ...prev, content: e.target.value }))}
                    placeholder="Write your knowledge content here..."
                    style={{
                      width: '100%',
                      height: '300px',
                      padding: '12px',
                      background: 'rgba(255,255,255,0.1)',
                      border: `1px solid ${actualThemeColors.cardBorder}`,
                      borderRadius: '8px',
                      color: actualThemeColors.text,
                      fontSize: '14px',
                      resize: 'vertical'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button
                    onClick={createKnowledgeArticle}
                    disabled={savingArticle || !newArticle.title.trim() || !newArticle.content.trim()}
                    style={{
                      padding: '12px 24px',
                      background: actualThemeColors.accent,
                      border: 'none',
                      borderRadius: '8px',
                      color: '#fff',
                      cursor: savingArticle ? 'not-allowed' : 'pointer',
                      opacity: savingArticle || !newArticle.title.trim() || !newArticle.content.trim() ? 0.5 : 1
                    }}
                  >
                    {savingArticle ? 'Saving...' : 'Create Draft'}
                  </button>
                  <button
                    onClick={() => setShowCreateArticle(false)}
                    disabled={savingArticle}
                    style={{
                      padding: '12px 24px',
                      background: 'rgba(255,255,255,0.1)',
                      border: 'none',
                      borderRadius: '8px',
                      color: actualThemeColors.text,
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default KnowledgeArticlesTab;
