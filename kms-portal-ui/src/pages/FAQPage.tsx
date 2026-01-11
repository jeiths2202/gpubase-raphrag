/**
 * FAQ Page - Frequently Asked Questions
 *
 * Features:
 * - Top 5 most viewed questions
 * - View count tracking (server-side + localStorage fallback)
 * - Expandable accordion-style Q&A
 * - Search functionality
 * - Category filtering
 * - Full i18n support
 * - Dynamic FAQ integration from popular AI queries
 */

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  HelpCircle,
  ChevronDown,
  Eye,
  TrendingUp,
  Tag,
  Clock,
  ThumbsUp,
  ThumbsDown,
  X,
  Sparkles,
  Loader2,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import { faqApi, type FAQItemAPI, type FAQCategory } from '../api';
import { usePreferencesStore } from '../store/preferencesStore';
import './FAQPage.css';

// Types
interface FAQItemData {
  id: string;
  translationKey?: string; // For static FAQs from i18n
  question?: string;       // For dynamic FAQs from API
  answer?: string;         // For dynamic FAQs from API
  category: string;
  createdAt: string;
  helpful: number;
  notHelpful: number;
  viewCount: number;
  tags: string[] | string; // Can be array or JSON string from API
  sourceType: 'static' | 'dynamic' | 'curated';
  isPinned: boolean;
}

interface FAQViewCount {
  [id: string]: number;
}

// Static FAQ item configuration (only metadata, content comes from i18n)
const STATIC_FAQ_ITEMS: Omit<FAQItemData, 'question' | 'answer'>[] = [
  {
    id: 'faq-001',
    translationKey: 'faq001',
    category: 'ofasm',
    createdAt: '2024-01-15',
    helpful: 45,
    notHelpful: 3,
    viewCount: 95,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-002',
    translationKey: 'faq002',
    category: 'ofcobol',
    createdAt: '2024-01-20',
    helpful: 52,
    notHelpful: 2,
    viewCount: 102,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-003',
    translationKey: 'faq003',
    category: 'openframe',
    createdAt: '2024-02-01',
    helpful: 78,
    notHelpful: 5,
    viewCount: 128,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-004',
    translationKey: 'faq004',
    category: 'openframe',
    createdAt: '2024-02-10',
    helpful: 63,
    notHelpful: 4,
    viewCount: 113,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-005',
    translationKey: 'faq005',
    category: 'ofasm',
    createdAt: '2024-02-15',
    helpful: 89,
    notHelpful: 2,
    viewCount: 139,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-006',
    translationKey: 'faq006',
    category: 'ofcobol',
    createdAt: '2024-02-20',
    helpful: 71,
    notHelpful: 3,
    viewCount: 121,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
  {
    id: 'faq-007',
    translationKey: 'faq007',
    category: 'openframe',
    createdAt: '2024-02-25',
    helpful: 95,
    notHelpful: 1,
    viewCount: 145,
    tags: [],
    sourceType: 'static',
    isPinned: false,
  },
];

// Default category definitions (fallback when API fails)
const DEFAULT_CATEGORIES = [
  { id: 'all', labelKey: 'faq.categories.all' },
  { id: 'openframe', labelKey: 'faq.categories.openframe' },
  { id: 'ofcobol', labelKey: 'faq.categories.ofcobol' },
  { id: 'ofasm', labelKey: 'faq.categories.ofasm' },
];

// localStorage key for view counts (fallback)
const VIEW_COUNT_KEY = 'faq_view_counts';

export const FAQPage: React.FC = () => {
  const { t } = useTranslation();
  const { language } = usePreferencesStore();

  // State
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [viewCounts, setViewCounts] = useState<FAQViewCount>({});
  const [feedbackGiven, setFeedbackGiven] = useState<Set<string>>(new Set());

  // Dynamic FAQ state
  const [dynamicFAQs, setDynamicFAQs] = useState<FAQItemData[]>([]);
  const [categories, setCategories] = useState<FAQCategory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Combine static and dynamic FAQs
  const allFAQs = useMemo<FAQItemData[]>(() => {
    // Convert static FAQs to full format
    const staticItems: FAQItemData[] = STATIC_FAQ_ITEMS.map(item => ({
      ...item,
      question: undefined,
      answer: undefined,
    }));

    // Merge: pinned first, then by view count
    return [...dynamicFAQs, ...staticItems].sort((a, b) => {
      if (a.isPinned && !b.isPinned) return -1;
      if (!a.isPinned && b.isPinned) return 1;
      return b.viewCount - a.viewCount;
    });
  }, [dynamicFAQs]);

  // Load dynamic FAQs from API
  const loadDynamicFAQs = useCallback(async () => {
    try {
      const response = await faqApi.getItems({
        language: language as 'en' | 'ko' | 'ja',
        include_dynamic: true,
        limit: 100,
      });

      if (response.status === 'success' && response.data.items) {
        const items: FAQItemData[] = response.data.items.map((item: FAQItemAPI) => ({
          id: item.id,
          question: item.question,
          answer: item.answer,
          category: item.category,
          createdAt: item.created_at || new Date().toISOString(),
          helpful: item.helpful_count,
          notHelpful: item.not_helpful_count,
          viewCount: item.view_count,
          tags: item.tags,
          sourceType: item.source_type,
          isPinned: item.is_pinned,
        }));
        setDynamicFAQs(items);
      }
    } catch (err) {
      console.warn('[FAQ] Failed to load dynamic FAQs:', err);
      // Continue with static FAQs only
    }
  }, [language]);

  // Load categories from API
  const loadCategories = useCallback(async () => {
    try {
      const response = await faqApi.getCategories();
      if (response.status === 'success' && response.data.categories) {
        setCategories(response.data.categories);
      }
    } catch (err) {
      console.warn('[FAQ] Failed to load categories:', err);
      // Use default categories
    }
  }, []);

  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      setError(null);

      try {
        await Promise.all([loadDynamicFAQs(), loadCategories()]);
      } catch (err) {
        setError('Failed to load FAQ data');
        console.error('[FAQ] Load error:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [loadDynamicFAQs, loadCategories]);

  // Load view counts from localStorage (fallback for static FAQs)
  useEffect(() => {
    const stored = localStorage.getItem(VIEW_COUNT_KEY);
    if (stored) {
      setViewCounts(JSON.parse(stored));
    } else {
      // Initialize with mock counts for static FAQs
      const initial: FAQViewCount = {};
      STATIC_FAQ_ITEMS.forEach(faq => {
        initial[faq.id] = faq.viewCount;
      });
      setViewCounts(initial);
      localStorage.setItem(VIEW_COUNT_KEY, JSON.stringify(initial));
    }
  }, []);

  // Get view count for an FAQ
  const getViewCount = (faq: FAQItemData): number => {
    // For dynamic FAQs, use server-provided count
    if (faq.sourceType !== 'static') {
      return faq.viewCount;
    }
    // For static FAQs, use localStorage
    return viewCounts[faq.id] || faq.viewCount || 0;
  };

  // Increment view count
  const incrementViewCount = async (faq: FAQItemData) => {
    // For dynamic FAQs, send to server
    if (faq.sourceType !== 'static') {
      try {
        await faqApi.recordView(faq.id);
        // Update local state
        setDynamicFAQs(prev =>
          prev.map(f => f.id === faq.id ? { ...f, viewCount: f.viewCount + 1 } : f)
        );
      } catch (err) {
        console.warn('[FAQ] Failed to record view:', err);
      }
      return;
    }

    // For static FAQs, use localStorage
    setViewCounts(prev => {
      const updated = { ...prev, [faq.id]: (prev[faq.id] || 0) + 1 };
      localStorage.setItem(VIEW_COUNT_KEY, JSON.stringify(updated));
      return updated;
    });
  };

  // Handle expand/collapse
  const handleToggle = (faq: FAQItemData) => {
    if (expandedId !== faq.id) {
      incrementViewCount(faq);
      setExpandedId(faq.id);
    } else {
      setExpandedId(null);
    }
  };

  // Get question text (from i18n for static, direct for dynamic)
  const getQuestion = (faq: FAQItemData): string => {
    if (faq.question) return faq.question;
    if (faq.translationKey) return t(`faq.items.${faq.translationKey}.question`);
    return '';
  };

  // Get answer text
  const getAnswer = (faq: FAQItemData): string => {
    if (faq.answer) return faq.answer;
    if (faq.translationKey) return t(`faq.items.${faq.translationKey}.answer`);
    return '';
  };

  // Get tags for an FAQ item
  const getTags = (faq: FAQItemData): string[] => {
    // Handle tags from dynamic FAQs (may be JSON string or array)
    if (faq.tags) {
      // If tags is a string (JSON), parse it
      if (typeof faq.tags === 'string') {
        try {
          const parsed = JSON.parse(faq.tags);
          if (Array.isArray(parsed) && parsed.length > 0) {
            return parsed;
          }
        } catch {
          // Not valid JSON, try comma-separated
          if (faq.tags.length > 0 && !faq.tags.startsWith('[')) {
            return faq.tags.split(',').map(s => s.trim()).filter(Boolean);
          }
        }
      } else if (Array.isArray(faq.tags) && faq.tags.length > 0) {
        return faq.tags;
      }
    }
    // Fallback to i18n for static FAQs
    if (faq.translationKey) {
      const tagsStr = t(`faq.items.${faq.translationKey}.tags`);
      try {
        if (tagsStr.startsWith('[')) {
          return JSON.parse(tagsStr);
        }
        return tagsStr.split(',').map(s => s.trim()).filter(Boolean);
      } catch {
        return [];
      }
    }
    return [];
  };

  // Filter FAQs based on search and category
  const filteredFAQs = useMemo(() => {
    return allFAQs.filter(faq => {
      const matchesCategory = activeCategory === 'all' || faq.category === activeCategory;
      const question = getQuestion(faq);
      const answer = getAnswer(faq);
      const tags = getTags(faq);
      const matchesSearch = !searchQuery ||
        question.toLowerCase().includes(searchQuery.toLowerCase()) ||
        answer.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchesCategory && matchesSearch;
    });
  }, [allFAQs, searchQuery, activeCategory, t]);

  // Get Top 5 most viewed FAQs
  const top5FAQs = useMemo(() => {
    return [...allFAQs]
      .sort((a, b) => getViewCount(b) - getViewCount(a))
      .slice(0, 5);
  }, [allFAQs, viewCounts]);

  // Handle feedback
  const handleFeedback = async (faq: FAQItemData, isHelpful: boolean) => {
    if (feedbackGiven.has(faq.id)) return;
    setFeedbackGiven(prev => new Set([...prev, faq.id]));

    // Send to server for dynamic FAQs
    if (faq.sourceType !== 'static') {
      try {
        await faqApi.recordFeedback(faq.id, isHelpful);
      } catch (err) {
        console.warn('[FAQ] Failed to record feedback:', err);
      }
    }
  };

  // Clear search
  const handleClearSearch = () => {
    setSearchQuery('');
  };

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Get category label
  const getCategoryLabel = (categoryId: string): string => {
    // Try API categories first
    const apiCategory = categories.find(c => c.id === categoryId);
    if (apiCategory) {
      const langKey = `name_${language}` as keyof FAQCategory;
      return (apiCategory[langKey] as string) || apiCategory.name;
    }
    // Fallback to i18n
    const defaultCat = DEFAULT_CATEGORIES.find(c => c.id === categoryId);
    if (defaultCat) {
      return t(defaultCat.labelKey);
    }
    return categoryId;
  };

  // Get available categories (merge API + default)
  const availableCategories = useMemo(() => {
    if (categories.length > 0) {
      return categories;
    }
    return DEFAULT_CATEGORIES.map(c => ({
      id: c.id,
      name: t(c.labelKey),
      name_ko: t(c.labelKey),
      name_ja: t(c.labelKey),
      count: 0,
    }));
  }, [categories, t]);

  return (
    <div className="faq-page">
      {/* Header */}
      <header className="faq-header">
        <div className="faq-header__content">
          <HelpCircle size={32} className="faq-header__icon" />
          <div>
            <h1 className="faq-header__title">{t('faq.title')}</h1>
            <p className="faq-header__subtitle">{t('faq.subtitle')}</p>
          </div>
        </div>

        {/* Search */}
        <div className="faq-search">
          <Search size={20} className="faq-search__icon" />
          <input
            type="text"
            className="faq-search__input"
            placeholder={t('faq.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              type="button"
              className="faq-search__clear"
              onClick={handleClearSearch}
              aria-label="Clear search"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </header>

      {/* Loading state */}
      {isLoading && (
        <div className="faq-loading">
          <Loader2 size={24} className="faq-loading__spinner" />
          <span>{t('faq.loading') || 'Loading...'}</span>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="faq-error">
          <span>{error}</span>
        </div>
      )}

      {/* Top 5 Section */}
      {!isLoading && (
        <section className="faq-top5">
          <div className="faq-top5__header">
            <TrendingUp size={20} className="faq-top5__icon" />
            <h2 className="faq-top5__title">{t('faq.top5Title')}</h2>
          </div>
          <div className="faq-top5__list">
            {top5FAQs.map((faq, index) => (
              <button
                key={faq.id}
                className={`faq-top5__item ${expandedId === faq.id ? 'active' : ''}`}
                onClick={() => handleToggle(faq)}
              >
                <span className="faq-top5__rank">{index + 1}</span>
                <span className="faq-top5__question">
                  {getQuestion(faq)}
                  {faq.sourceType === 'dynamic' && (
                    <Sparkles size={14} className="faq-top5__dynamic-badge" title="AI Generated" />
                  )}
                </span>
                <span className="faq-top5__views">
                  <Eye size={14} />
                  {getViewCount(faq)}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Main Content */}
      {!isLoading && (
        <div className="faq-content">
          {/* Category Filter */}
          <nav className="faq-categories">
            {availableCategories.map(category => (
              <button
                key={category.id}
                className={`faq-categories__item ${activeCategory === category.id ? 'active' : ''}`}
                onClick={() => setActiveCategory(category.id)}
              >
                {getCategoryLabel(category.id)}
                {category.count > 0 && (
                  <span className="faq-categories__count">{category.count}</span>
                )}
              </button>
            ))}
          </nav>

          {/* Results count */}
          <div className="faq-results-info">
            <span>
              {filteredFAQs.length} {t('faq.questionsFound')}
              {searchQuery && ` "${searchQuery}"`}
            </span>
            {dynamicFAQs.length > 0 && (
              <span className="faq-results-info__dynamic">
                <Sparkles size={14} />
                {dynamicFAQs.length} {t('faq.dynamicQuestions') || 'AI-generated'}
              </span>
            )}
          </div>

          {/* FAQ List */}
          <div className="faq-list">
            {filteredFAQs.length === 0 ? (
              <div className="faq-empty">
                <HelpCircle size={48} className="faq-empty__icon" />
                <h3>{t('faq.noResults')}</h3>
                <p>{t('faq.noResultsDescription')}</p>
                {searchQuery && (
                  <button className="btn btn-secondary" onClick={handleClearSearch}>
                    {t('faq.clearSearch')}
                  </button>
                )}
              </div>
            ) : (
              filteredFAQs.map(faq => {
                const question = getQuestion(faq);
                const answer = getAnswer(faq);
                const tags = getTags(faq);

                return (
                  <div
                    key={faq.id}
                    className={`faq-item ${expandedId === faq.id ? 'expanded' : ''} ${faq.sourceType === 'dynamic' ? 'faq-item--dynamic' : ''}`}
                  >
                    <button
                      className="faq-item__header"
                      onClick={() => handleToggle(faq)}
                      aria-expanded={expandedId === faq.id}
                    >
                      <div className="faq-item__question">
                        <HelpCircle size={20} className="faq-item__icon" />
                        <span>{question}</span>
                        {faq.sourceType === 'dynamic' && (
                          <Sparkles size={14} className="faq-item__dynamic-badge" title="AI Generated" />
                        )}
                      </div>
                      <div className="faq-item__meta">
                        <span className="faq-item__views">
                          <Eye size={14} />
                          {getViewCount(faq)}
                        </span>
                        <ChevronDown
                          size={20}
                          className={`faq-item__chevron ${expandedId === faq.id ? 'rotated' : ''}`}
                        />
                      </div>
                    </button>

                    {expandedId === faq.id && (
                      <div className="faq-item__content">
                        <div className="faq-item__answer">
                          <pre>{answer}</pre>
                        </div>

                        <div className="faq-item__footer">
                          <div className="faq-item__tags">
                            <Tag size={14} />
                            {tags.map(tag => (
                              <span key={tag} className="faq-item__tag">{tag}</span>
                            ))}
                          </div>

                          <div className="faq-item__date">
                            <Clock size={14} />
                            {formatDate(faq.createdAt)}
                          </div>
                        </div>

                        <div className="faq-item__feedback">
                          <span>{t('faq.wasHelpful')}</span>
                          <div className="faq-item__feedback-buttons">
                            <button
                              className={`faq-feedback-btn ${feedbackGiven.has(faq.id) ? 'disabled' : ''}`}
                              onClick={() => handleFeedback(faq, true)}
                              disabled={feedbackGiven.has(faq.id)}
                            >
                              <ThumbsUp size={16} />
                              {t('faq.yes')}
                            </button>
                            <button
                              className={`faq-feedback-btn ${feedbackGiven.has(faq.id) ? 'disabled' : ''}`}
                              onClick={() => handleFeedback(faq, false)}
                              disabled={feedbackGiven.has(faq.id)}
                            >
                              <ThumbsDown size={16} />
                              {t('faq.no')}
                            </button>
                          </div>
                          {feedbackGiven.has(faq.id) && (
                            <span className="faq-item__feedback-thanks">
                              {t('faq.thanksFeedback')}
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default FAQPage;
