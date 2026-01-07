/**
 * FAQ Page - Frequently Asked Questions
 *
 * Features:
 * - Top 5 most viewed questions
 * - View count tracking with localStorage
 * - Expandable accordion-style Q&A
 * - Search functionality
 * - Category filtering
 * - Full i18n support
 */

import React, { useState, useEffect, useMemo } from 'react';
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
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './FAQPage.css';

// Types
interface FAQItemData {
  id: string;
  translationKey: string;
  category: string;
  createdAt: string;
  helpful: number;
  notHelpful: number;
}

interface FAQViewCount {
  [id: string]: number;
}

// FAQ item configuration (only metadata, content comes from i18n)
const FAQ_ITEMS: FAQItemData[] = [
  {
    id: 'faq-001',
    translationKey: 'faq001',
    category: 'ofasm',
    createdAt: '2024-01-15',
    helpful: 45,
    notHelpful: 3,
  },
  {
    id: 'faq-002',
    translationKey: 'faq002',
    category: 'ofcobol',
    createdAt: '2024-01-20',
    helpful: 52,
    notHelpful: 2,
  },
  {
    id: 'faq-003',
    translationKey: 'faq003',
    category: 'openframe',
    createdAt: '2024-02-01',
    helpful: 78,
    notHelpful: 5,
  },
  {
    id: 'faq-004',
    translationKey: 'faq004',
    category: 'openframe',
    createdAt: '2024-02-10',
    helpful: 63,
    notHelpful: 4,
  },
  {
    id: 'faq-005',
    translationKey: 'faq005',
    category: 'ofasm',
    createdAt: '2024-02-15',
    helpful: 89,
    notHelpful: 2,
  },
  {
    id: 'faq-006',
    translationKey: 'faq006',
    category: 'ofcobol',
    createdAt: '2024-02-20',
    helpful: 71,
    notHelpful: 3,
  },
  {
    id: 'faq-007',
    translationKey: 'faq007',
    category: 'openframe',
    createdAt: '2024-02-25',
    helpful: 95,
    notHelpful: 1,
  },
];

// Category definitions
const FAQ_CATEGORIES = [
  { id: 'all', labelKey: 'faq.categories.all' },
  { id: 'openframe', labelKey: 'faq.categories.openframe' },
  { id: 'ofcobol', labelKey: 'faq.categories.ofcobol' },
  { id: 'ofasm', labelKey: 'faq.categories.ofasm' },
];

// localStorage key for view counts
const VIEW_COUNT_KEY = 'faq_view_counts';

export const FAQPage: React.FC = () => {
  const { t } = useTranslation();

  // State
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [viewCounts, setViewCounts] = useState<FAQViewCount>({});
  const [feedbackGiven, setFeedbackGiven] = useState<Set<string>>(new Set());

  // Load view counts from localStorage
  useEffect(() => {
    const stored = localStorage.getItem(VIEW_COUNT_KEY);
    if (stored) {
      setViewCounts(JSON.parse(stored));
    } else {
      // Initialize with mock helpful counts as initial view counts
      const initial: FAQViewCount = {};
      FAQ_ITEMS.forEach(faq => {
        initial[faq.id] = faq.helpful + Math.floor(Math.random() * 50);
      });
      setViewCounts(initial);
      localStorage.setItem(VIEW_COUNT_KEY, JSON.stringify(initial));
    }
  }, []);

  // Get view count for an FAQ
  const getViewCount = (id: string): number => {
    return viewCounts[id] || 0;
  };

  // Increment view count
  const incrementViewCount = (id: string) => {
    setViewCounts(prev => {
      const updated = { ...prev, [id]: (prev[id] || 0) + 1 };
      localStorage.setItem(VIEW_COUNT_KEY, JSON.stringify(updated));
      return updated;
    });
  };

  // Handle expand/collapse
  const handleToggle = (id: string) => {
    if (expandedId !== id) {
      incrementViewCount(id);
      setExpandedId(id);
    } else {
      setExpandedId(null);
    }
  };

  // Get translated question for an FAQ item
  const getQuestion = (translationKey: string): string => {
    return t(`faq.items.${translationKey}.question`);
  };

  // Get translated answer for an FAQ item
  const getAnswer = (translationKey: string): string => {
    return t(`faq.items.${translationKey}.answer`);
  };

  // Get translated tags for an FAQ item
  const getTags = (translationKey: string): string[] => {
    const tagsStr = t(`faq.items.${translationKey}.tags`);
    // Tags are stored as JSON array in translation
    try {
      if (tagsStr.startsWith('[')) {
        return JSON.parse(tagsStr);
      }
      return tagsStr.split(',').map(s => s.trim());
    } catch {
      return [];
    }
  };

  // Filter FAQs based on search and category
  const filteredFAQs = useMemo(() => {
    return FAQ_ITEMS.filter(faq => {
      const matchesCategory = activeCategory === 'all' || faq.category === activeCategory;
      const question = getQuestion(faq.translationKey);
      const answer = getAnswer(faq.translationKey);
      const tags = getTags(faq.translationKey);
      const matchesSearch = !searchQuery ||
        question.toLowerCase().includes(searchQuery.toLowerCase()) ||
        answer.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tags.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));
      return matchesCategory && matchesSearch;
    });
  }, [searchQuery, activeCategory, t]);

  // Get Top 5 most viewed FAQs
  const top5FAQs = useMemo(() => {
    return [...FAQ_ITEMS]
      .sort((a, b) => getViewCount(b.id) - getViewCount(a.id))
      .slice(0, 5);
  }, [viewCounts]);

  // Handle feedback
  const handleFeedback = (id: string, isHelpful: boolean) => {
    if (feedbackGiven.has(id)) return;
    setFeedbackGiven(prev => new Set([...prev, id]));
    // In a real app, this would send to the backend
    console.log(`Feedback for ${id}: ${isHelpful ? 'helpful' : 'not helpful'}`);
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

      {/* Top 5 Section */}
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
              onClick={() => handleToggle(faq.id)}
            >
              <span className="faq-top5__rank">{index + 1}</span>
              <span className="faq-top5__question">{getQuestion(faq.translationKey)}</span>
              <span className="faq-top5__views">
                <Eye size={14} />
                {getViewCount(faq.id)}
              </span>
            </button>
          ))}
        </div>
      </section>

      {/* Main Content */}
      <div className="faq-content">
        {/* Category Filter */}
        <nav className="faq-categories">
          {FAQ_CATEGORIES.map(category => (
            <button
              key={category.id}
              className={`faq-categories__item ${activeCategory === category.id ? 'active' : ''}`}
              onClick={() => setActiveCategory(category.id)}
            >
              {t(category.labelKey)}
            </button>
          ))}
        </nav>

        {/* Results count */}
        <div className="faq-results-info">
          <span>
            {filteredFAQs.length} {t('faq.questionsFound')}
            {searchQuery && ` "${searchQuery}"`}
          </span>
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
              const question = getQuestion(faq.translationKey);
              const answer = getAnswer(faq.translationKey);
              const tags = getTags(faq.translationKey);

              return (
                <div
                  key={faq.id}
                  className={`faq-item ${expandedId === faq.id ? 'expanded' : ''}`}
                >
                  <button
                    className="faq-item__header"
                    onClick={() => handleToggle(faq.id)}
                    aria-expanded={expandedId === faq.id}
                  >
                    <div className="faq-item__question">
                      <HelpCircle size={20} className="faq-item__icon" />
                      <span>{question}</span>
                    </div>
                    <div className="faq-item__meta">
                      <span className="faq-item__views">
                        <Eye size={14} />
                        {getViewCount(faq.id)}
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
                            onClick={() => handleFeedback(faq.id, true)}
                            disabled={feedbackGiven.has(faq.id)}
                          >
                            <ThumbsUp size={16} />
                            {t('faq.yes')}
                          </button>
                          <button
                            className={`faq-feedback-btn ${feedbackGiven.has(faq.id) ? 'disabled' : ''}`}
                            onClick={() => handleFeedback(faq.id, false)}
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
    </div>
  );
};

export default FAQPage;
