/**
 * Knowledge Base Page
 *
 * Zendesk Help Center style knowledge base with categories, search, and article cards
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Search,
  BookOpen,
  FileText,
  HelpCircle,
  FileCode,
  Shield,
  Eye,
  Clock,
  Grid,
  List,
  ChevronLeft,
  ChevronRight,
  X,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './KnowledgeBasePage.css';

// Types
interface Article {
  id: string;
  title: string;
  summary: string;
  category: string;
  tags: string[];
  author: string;
  createdAt: string;
  updatedAt: string;
  views: number;
  helpful: number;
  notHelpful: number;
}

interface Category {
  id: string;
  name: string;
  count: number;
}

interface Suggestion {
  id: string;
  title: string;
  category: string;
}

interface ArticlesResponse {
  items: Article[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// Category icons mapping
const categoryIcons: Record<string, React.ReactNode> = {
  all: <BookOpen size={18} />,
  documents: <FileText size={18} />,
  faqs: <HelpCircle size={18} />,
  guides: <FileCode size={18} />,
  policies: <Shield size={18} />,
};

export const KnowledgeBasePage: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // State
  const [articles, setArticles] = useState<Article[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  // UI State
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [activeCategory, setActiveCategory] = useState(searchParams.get('category') || 'all');
  const [currentPage, setCurrentPage] = useState(Number(searchParams.get('page')) || 1);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Refs
  const searchInputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  // Fetch categories
  useEffect(() => {
    const fetchCategories = async () => {
      try {
        const response = await fetch('/api/v1/knowledge/categories');
        const data = await response.json();
        setCategories(data);
      } catch (error) {
        console.error('Failed to fetch categories:', error);
      }
    };
    fetchCategories();
  }, []);

  // Fetch articles
  const fetchArticles = useCallback(async () => {
    setIsLoading(true);
    try {
      const params = new URLSearchParams();
      if (activeCategory !== 'all') params.append('category', activeCategory);
      if (searchQuery) params.append('search', searchQuery);
      params.append('page', currentPage.toString());
      params.append('limit', '9');

      const response = await fetch(`/api/v1/knowledge/articles?${params}`);
      const data: ArticlesResponse = await response.json();

      setArticles(data.items);
      setTotalPages(data.totalPages);
      setTotal(data.total);
    } catch (error) {
      console.error('Failed to fetch articles:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeCategory, searchQuery, currentPage]);

  useEffect(() => {
    fetchArticles();
  }, [fetchArticles]);

  // Update URL params
  useEffect(() => {
    const params = new URLSearchParams();
    if (activeCategory !== 'all') params.set('category', activeCategory);
    if (searchQuery) params.set('search', searchQuery);
    if (currentPage > 1) params.set('page', currentPage.toString());
    setSearchParams(params, { replace: true });
  }, [activeCategory, searchQuery, currentPage, setSearchParams]);

  // Fetch search suggestions
  const fetchSuggestions = useCallback(async (query: string) => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }
    try {
      const response = await fetch(`/api/v1/knowledge/suggestions?q=${encodeURIComponent(query)}`);
      const data = await response.json();
      setSuggestions(data);
    } catch (error) {
      console.error('Failed to fetch suggestions:', error);
    }
  }, []);

  // Debounced search suggestions
  useEffect(() => {
    const timer = setTimeout(() => {
      if (showSuggestions) {
        fetchSuggestions(searchQuery);
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [searchQuery, showSuggestions, fetchSuggestions]);

  // Handle search submit
  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    setShowSuggestions(false);
    fetchArticles();
  };

  // Handle category change
  const handleCategoryChange = (categoryId: string) => {
    setActiveCategory(categoryId);
    setCurrentPage(1);
  };

  // Handle suggestion click
  const handleSuggestionClick = (suggestion: Suggestion) => {
    setSearchQuery(suggestion.title);
    setShowSuggestions(false);
    setCurrentPage(1);
  };

  // Clear search
  const handleClearSearch = () => {
    setSearchQuery('');
    setCurrentPage(1);
    searchInputRef.current?.focus();
  };

  // Close suggestions on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  // Render loading skeletons
  const renderSkeletons = () => (
    <div className={`kb-articles-${viewMode}`}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="kb-article-card kb-article-card--skeleton">
          <div className="skeleton skeleton-title" />
          <div className="skeleton skeleton-text" />
          <div className="skeleton skeleton-text skeleton-text--short" />
          <div className="kb-article-card__meta">
            <div className="skeleton skeleton-meta" />
            <div className="skeleton skeleton-meta" />
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="kb-page">
      {/* Header Section */}
      <header className="kb-header">
        <div className="kb-header__content">
          <h1 className="kb-header__title">{t('knowledge.title')}</h1>
          <p className="kb-header__subtitle">
            Find answers to your questions and learn how to use the platform
          </p>
        </div>

        {/* Search Bar */}
        <form className="kb-search" onSubmit={handleSearch}>
          <div className="kb-search__container" ref={suggestionsRef}>
            <Search className="kb-search__icon" size={20} />
            <input
              ref={searchInputRef}
              type="text"
              className="kb-search__input"
              placeholder={t('knowledge.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setShowSuggestions(true)}
            />
            {searchQuery && (
              <button
                type="button"
                className="kb-search__clear"
                onClick={handleClearSearch}
                aria-label="Clear search"
              >
                <X size={18} />
              </button>
            )}

            {/* Suggestions Dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="kb-suggestions">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion.id}
                    type="button"
                    className="kb-suggestions__item"
                    onClick={() => handleSuggestionClick(suggestion)}
                  >
                    <Search size={14} className="kb-suggestions__icon" />
                    <span className="kb-suggestions__title">{suggestion.title}</span>
                    <span className="kb-suggestions__category">
                      {t(`knowledge.categories.${suggestion.category}`)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="submit" className="btn btn-primary kb-search__button">
            {t('knowledge.askQuestion')}
          </button>
        </form>
      </header>

      {/* Main Content */}
      <div className="kb-content">
        {/* Category Tabs */}
        <nav className="kb-categories">
          <div className="kb-categories__list">
            {categories.map((category) => (
              <button
                key={category.id}
                className={`kb-categories__item ${activeCategory === category.id ? 'kb-categories__item--active' : ''}`}
                onClick={() => handleCategoryChange(category.id)}
              >
                {categoryIcons[category.id] || <FileText size={18} />}
                <span className="kb-categories__name">
                  {t(`knowledge.categories.${category.id}`)}
                </span>
                <span className="kb-categories__count">{category.count}</span>
              </button>
            ))}
          </div>

          {/* View Toggle */}
          <div className="kb-view-toggle">
            <button
              className={`kb-view-toggle__btn ${viewMode === 'grid' ? 'kb-view-toggle__btn--active' : ''}`}
              onClick={() => setViewMode('grid')}
              aria-label="Grid view"
            >
              <Grid size={18} />
            </button>
            <button
              className={`kb-view-toggle__btn ${viewMode === 'list' ? 'kb-view-toggle__btn--active' : ''}`}
              onClick={() => setViewMode('list')}
              aria-label="List view"
            >
              <List size={18} />
            </button>
          </div>
        </nav>

        {/* Results Info */}
        <div className="kb-results-info">
          <span className="kb-results-info__count">
            {total} {total === 1 ? 'article' : 'articles'} found
            {searchQuery && ` for "${searchQuery}"`}
          </span>
        </div>

        {/* Articles Grid/List */}
        {isLoading ? (
          renderSkeletons()
        ) : articles.length === 0 ? (
          <div className="kb-empty">
            <BookOpen size={48} className="kb-empty__icon" />
            <h3 className="kb-empty__title">{t('knowledge.noResults')}</h3>
            <p className="kb-empty__description">
              Try adjusting your search or browse different categories
            </p>
            {searchQuery && (
              <button className="btn btn-secondary" onClick={handleClearSearch}>
                Clear search
              </button>
            )}
          </div>
        ) : (
          <div className={`kb-articles-${viewMode}`}>
            {articles.map((article) => (
              <Link
                key={article.id}
                to={`/knowledge/${article.id}`}
                className={`kb-article-card kb-article-card--${viewMode}`}
              >
                <div className="kb-article-card__category">
                  {categoryIcons[article.category] || <FileText size={14} />}
                  <span>{t(`knowledge.categories.${article.category}`)}</span>
                </div>
                <h3 className="kb-article-card__title">{article.title}</h3>
                <p className="kb-article-card__summary">{article.summary}</p>
                <div className="kb-article-card__meta">
                  <span className="kb-article-card__views">
                    <Eye size={14} />
                    {article.views} {t('knowledge.article.views')}
                  </span>
                  <span className="kb-article-card__date">
                    <Clock size={14} />
                    {formatDate(article.updatedAt)}
                  </span>
                </div>
                {article.tags.length > 0 && (
                  <div className="kb-article-card__tags">
                    {article.tags.slice(0, 3).map((tag) => (
                      <span key={tag} className="kb-article-card__tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <nav className="kb-pagination">
            <button
              className="kb-pagination__btn"
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={18} />
              Previous
            </button>

            <div className="kb-pagination__pages">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                <button
                  key={page}
                  className={`kb-pagination__page ${currentPage === page ? 'kb-pagination__page--active' : ''}`}
                  onClick={() => setCurrentPage(page)}
                >
                  {page}
                </button>
              ))}
            </div>

            <button
              className="kb-pagination__btn"
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
              <ChevronRight size={18} />
            </button>
          </nav>
        )}
      </div>
    </div>
  );
};

export default KnowledgeBasePage;
