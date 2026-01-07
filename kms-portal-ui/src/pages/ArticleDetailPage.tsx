/**
 * Article Detail Page
 *
 * Displays full article content with markdown rendering, feedback, and related articles
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import {
  ArrowLeft,
  Eye,
  Clock,
  User,
  ThumbsUp,
  ThumbsDown,
  BookOpen,
  FileText,
  HelpCircle,
  FileCode,
  Shield,
  Check,
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './ArticleDetailPage.css';

// Types
interface Article {
  id: string;
  title: string;
  summary: string;
  content: string;
  category: string;
  tags: string[];
  author: string;
  createdAt: string;
  updatedAt: string;
  views: number;
  helpful: number;
  notHelpful: number;
}

interface RelatedArticle {
  id: string;
  title: string;
  category: string;
}

// Category icons mapping
const categoryIcons: Record<string, React.ReactNode> = {
  all: <BookOpen size={16} />,
  documents: <FileText size={16} />,
  faqs: <HelpCircle size={16} />,
  guides: <FileCode size={16} />,
  policies: <Shield size={16} />,
};

export const ArticleDetailPage: React.FC = () => {
  const { articleId } = useParams<{ articleId: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  // State
  const [article, setArticle] = useState<Article | null>(null);
  const [relatedArticles, setRelatedArticles] = useState<RelatedArticle[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedbackState, setFeedbackState] = useState<'none' | 'helpful' | 'not-helpful'>('none');
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  // Fetch article
  useEffect(() => {
    const fetchArticle = async () => {
      if (!articleId) return;

      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(`/api/v1/knowledge/articles/${articleId}`);
        if (!response.ok) {
          if (response.status === 404) {
            setError('Article not found');
          } else {
            setError('Failed to load article');
          }
          return;
        }
        const data = await response.json();
        setArticle(data);
      } catch (err) {
        console.error('Failed to fetch article:', err);
        setError('Failed to load article');
      } finally {
        setIsLoading(false);
      }
    };

    fetchArticle();
  }, [articleId]);

  // Fetch related articles (same category, excluding current)
  useEffect(() => {
    const fetchRelatedArticles = async () => {
      if (!article) return;

      try {
        const response = await fetch(
          `/api/v1/knowledge/articles?category=${article.category}&limit=4`
        );
        const data = await response.json();
        const related = data.items
          .filter((a: Article) => a.id !== article.id)
          .slice(0, 3)
          .map((a: Article) => ({
            id: a.id,
            title: a.title,
            category: a.category,
          }));
        setRelatedArticles(related);
      } catch (err) {
        console.error('Failed to fetch related articles:', err);
      }
    };

    fetchRelatedArticles();
  }, [article]);

  // Handle feedback
  const handleFeedback = useCallback(
    async (helpful: boolean) => {
      if (!articleId || feedbackSubmitted) return;

      const newState = helpful ? 'helpful' : 'not-helpful';
      setFeedbackState(newState);

      try {
        await fetch(`/api/v1/knowledge/articles/${articleId}/rate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ helpful }),
        });
        setFeedbackSubmitted(true);
      } catch (err) {
        console.error('Failed to submit feedback:', err);
      }
    },
    [articleId, feedbackSubmitted]
  );

  // Format date
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="article-page">
        <div className="article-loading">
          <div className="article-loading__skeleton article-loading__skeleton--title" />
          <div className="article-loading__skeleton article-loading__skeleton--meta" />
          <div className="article-loading__skeleton article-loading__skeleton--content" />
          <div className="article-loading__skeleton article-loading__skeleton--content" />
          <div className="article-loading__skeleton article-loading__skeleton--content-short" />
        </div>
      </div>
    );
  }

  // Error state
  if (error || !article) {
    return (
      <div className="article-page">
        <div className="article-error">
          <BookOpen size={48} className="article-error__icon" />
          <h2 className="article-error__title">{error || 'Article not found'}</h2>
          <p className="article-error__description">
            The article you are looking for may have been moved or deleted.
          </p>
          <Link to="/knowledge" className="btn btn-primary">
            <ArrowLeft size={18} />
            Back to Knowledge Base
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="article-page">
      {/* Navigation */}
      <nav className="article-breadcrumb">
        <button className="article-back-btn" onClick={() => navigate('/knowledge')}>
          <ArrowLeft size={18} />
          <span>Back to Knowledge Base</span>
        </button>
      </nav>

      <div className="article-layout">
        {/* Main Content */}
        <main className="article-main">
          {/* Article Header */}
          <header className="article-header">
            <div className="article-category">
              {categoryIcons[article.category] || <FileText size={16} />}
              <span>{t(`knowledge.categories.${article.category}`)}</span>
            </div>
            <h1 className="article-title">{article.title}</h1>
            <p className="article-summary">{article.summary}</p>
            <div className="article-meta">
              <span className="article-meta__item">
                <User size={14} />
                {article.author}
              </span>
              <span className="article-meta__item">
                <Clock size={14} />
                {t('knowledge.article.lastUpdated')}: {formatDate(article.updatedAt)}
              </span>
              <span className="article-meta__item">
                <Eye size={14} />
                {article.views.toLocaleString()} {t('knowledge.article.views')}
              </span>
            </div>
            {article.tags.length > 0 && (
              <div className="article-tags">
                {article.tags.map((tag) => (
                  <span key={tag} className="article-tag">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </header>

          {/* Article Content */}
          <article className="article-content">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeHighlight]}
              components={{
                h1: ({ children }) => <h1 className="article-h1">{children}</h1>,
                h2: ({ children }) => <h2 className="article-h2">{children}</h2>,
                h3: ({ children }) => <h3 className="article-h3">{children}</h3>,
                p: ({ children }) => <p className="article-p">{children}</p>,
                ul: ({ children }) => <ul className="article-ul">{children}</ul>,
                ol: ({ children }) => <ol className="article-ol">{children}</ol>,
                li: ({ children }) => <li className="article-li">{children}</li>,
                blockquote: ({ children }) => (
                  <blockquote className="article-blockquote">{children}</blockquote>
                ),
                code: ({ className, children, ...props }) => {
                  const match = /language-(\w+)/.exec(className || '');
                  const isInline = !match;
                  return isInline ? (
                    <code className="article-code-inline" {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className={`article-code-block ${className || ''}`} {...props}>
                      {children}
                    </code>
                  );
                },
                pre: ({ children }) => <pre className="article-pre">{children}</pre>,
                a: ({ href, children }) => (
                  <a href={href} className="article-link" target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
                strong: ({ children }) => <strong className="article-strong">{children}</strong>,
                table: ({ children }) => (
                  <div className="article-table-wrapper">
                    <table className="article-table">{children}</table>
                  </div>
                ),
              }}
            >
              {article.content}
            </ReactMarkdown>
          </article>

          {/* Feedback Section */}
          <section className="article-feedback">
            <div className="article-feedback__question">
              <span className="article-feedback__label">{t('knowledge.article.helpful')}</span>
              <div className="article-feedback__buttons">
                <button
                  className={`article-feedback__btn ${feedbackState === 'helpful' ? 'article-feedback__btn--active article-feedback__btn--helpful' : ''}`}
                  onClick={() => handleFeedback(true)}
                  disabled={feedbackSubmitted}
                >
                  {feedbackState === 'helpful' ? <Check size={18} /> : <ThumbsUp size={18} />}
                  <span>{t('knowledge.article.yes')}</span>
                  {!feedbackSubmitted && <span className="article-feedback__count">{article.helpful}</span>}
                </button>
                <button
                  className={`article-feedback__btn ${feedbackState === 'not-helpful' ? 'article-feedback__btn--active article-feedback__btn--not-helpful' : ''}`}
                  onClick={() => handleFeedback(false)}
                  disabled={feedbackSubmitted}
                >
                  {feedbackState === 'not-helpful' ? <Check size={18} /> : <ThumbsDown size={18} />}
                  <span>{t('knowledge.article.no')}</span>
                  {!feedbackSubmitted && <span className="article-feedback__count">{article.notHelpful}</span>}
                </button>
              </div>
            </div>
            {feedbackSubmitted && (
              <p className="article-feedback__thanks">Thank you for your feedback!</p>
            )}
          </section>
        </main>

        {/* Sidebar */}
        <aside className="article-sidebar">
          {/* Related Articles */}
          {relatedArticles.length > 0 && (
            <section className="article-related">
              <h3 className="article-related__title">{t('knowledge.article.relatedArticles')}</h3>
              <ul className="article-related__list">
                {relatedArticles.map((related) => (
                  <li key={related.id}>
                    <Link to={`/knowledge/${related.id}`} className="article-related__item">
                      {categoryIcons[related.category] || <FileText size={16} />}
                      <span className="article-related__item-title">{related.title}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Article Info */}
          <section className="article-info">
            <h3 className="article-info__title">Article Information</h3>
            <dl className="article-info__list">
              <div className="article-info__item">
                <dt>Created</dt>
                <dd>{formatDate(article.createdAt)}</dd>
              </div>
              <div className="article-info__item">
                <dt>Last Updated</dt>
                <dd>{formatDate(article.updatedAt)}</dd>
              </div>
              <div className="article-info__item">
                <dt>Author</dt>
                <dd>{article.author}</dd>
              </div>
              <div className="article-info__item">
                <dt>Views</dt>
                <dd>{article.views.toLocaleString()}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
};

export default ArticleDetailPage;
