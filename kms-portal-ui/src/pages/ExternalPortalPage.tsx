/**
 * External Portal Page
 *
 * Public-facing portal for external users
 * Different layout without AI sidebar
 */

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Book,
  HelpCircle,
  FileText,
  MessageSquare,
  ArrowRight,
  Star,
  Clock,
  ChevronRight,
  ExternalLink,
  Globe
} from 'lucide-react';
import { useTranslation } from '../hooks/useTranslation';
import './ExternalPortalPage.css';

// Mock popular articles
const popularArticles = [
  {
    id: 'pop-1',
    title: 'Getting Started with KMS Portal',
    category: 'guides',
    views: 12453,
    rating: 4.8
  },
  {
    id: 'pop-2',
    title: 'How to Search the Knowledge Base',
    category: 'guides',
    views: 8721,
    rating: 4.6
  },
  {
    id: 'pop-3',
    title: 'Frequently Asked Questions',
    category: 'faqs',
    views: 15234,
    rating: 4.9
  },
  {
    id: 'pop-4',
    title: 'Document Upload Guidelines',
    category: 'policies',
    views: 6543,
    rating: 4.5
  }
];

// Mock recent articles
const recentArticles = [
  {
    id: 'rec-1',
    title: 'New AI Features in Version 2.0',
    category: 'announcements',
    date: '2025-01-06'
  },
  {
    id: 'rec-2',
    title: 'System Maintenance Schedule',
    category: 'announcements',
    date: '2025-01-05'
  },
  {
    id: 'rec-3',
    title: 'Best Practices for Knowledge Sharing',
    category: 'guides',
    date: '2025-01-04'
  }
];

// Categories
const categories = [
  { id: 'guides', icon: Book, label: 'Guides', count: 124 },
  { id: 'faqs', icon: HelpCircle, label: 'FAQs', count: 89 },
  { id: 'policies', icon: FileText, label: 'Policies', count: 45 },
  { id: 'support', icon: MessageSquare, label: 'Support', count: 67 }
];

export const ExternalPortalPage: React.FC = () => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    // Navigate to search results
    console.log('Search:', searchQuery);
  };

  return (
    <div className="external-portal">
      {/* Header */}
      <header className="external-header">
        <div className="external-header-content">
          <Link to="/portal" className="external-logo">
            <div className="external-logo-icon">K</div>
            <span className="external-logo-text">{t('portal.title')}</span>
          </Link>
          <nav className="external-nav">
            <Link to="/portal" className="external-nav-link active">
              {t('portal.home')}
            </Link>
            <Link to="/portal/knowledge" className="external-nav-link">
              {t('portal.knowledgeBase')}
            </Link>
            <Link to="/portal/contact" className="external-nav-link">
              {t('portal.contact')}
            </Link>
          </nav>
          <div className="external-header-actions">
            <button className="btn btn-ghost btn-sm">
              <Globe size={16} />
              EN
            </button>
            <Link to="/login" className="btn btn-primary btn-sm">
              {t('portal.signIn')}
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="external-hero">
        <div className="external-hero-background">
          <div className="external-hero-gradient" />
          <div className="external-hero-pattern" />
        </div>
        <div className="external-hero-content">
          <h1 className="external-hero-title">{t('portal.heroTitle')}</h1>
          <p className="external-hero-subtitle">{t('portal.heroSubtitle')}</p>

          <form className="external-search-form" onSubmit={handleSearch}>
            <div className="external-search-bar">
              <Search className="external-search-icon" />
              <input
                type="text"
                className="external-search-input"
                placeholder={t('portal.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <button type="submit" className="btn btn-primary">
                {t('common.search')}
              </button>
            </div>
          </form>

          <div className="external-quick-links">
            <span>{t('portal.quickLinks')}:</span>
            <button className="external-quick-link">Getting Started</button>
            <button className="external-quick-link">FAQ</button>
            <button className="external-quick-link">Contact Support</button>
          </div>
        </div>
      </section>

      {/* Categories Section */}
      <section className="external-section">
        <div className="external-section-content">
          <h2 className="external-section-title">{t('portal.browseCategories')}</h2>
          <div className="external-categories">
            {categories.map(category => (
              <Link
                key={category.id}
                to={`/portal/category/${category.id}`}
                className="external-category-card"
              >
                <div className="external-category-icon">
                  <category.icon size={24} />
                </div>
                <div className="external-category-content">
                  <h3 className="external-category-title">{category.label}</h3>
                  <span className="external-category-count">
                    {category.count} {t('portal.articles')}
                  </span>
                </div>
                <ChevronRight className="external-category-arrow" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Popular Articles */}
      <section className="external-section external-section-alt">
        <div className="external-section-content">
          <div className="external-section-header">
            <h2 className="external-section-title">{t('portal.popularArticles')}</h2>
            <Link to="/portal/popular" className="external-view-all">
              {t('common.viewAll')} <ArrowRight size={16} />
            </Link>
          </div>
          <div className="external-articles-grid">
            {popularArticles.map(article => (
              <Link
                key={article.id}
                to={`/portal/article/${article.id}`}
                className="external-article-card"
              >
                <div className="external-article-content">
                  <span className="external-article-category">{article.category}</span>
                  <h3 className="external-article-title">{article.title}</h3>
                  <div className="external-article-meta">
                    <span className="external-article-views">
                      <Star size={14} />
                      {article.rating}
                    </span>
                    <span className="external-article-views">
                      {article.views.toLocaleString()} {t('portal.views')}
                    </span>
                  </div>
                </div>
                <ExternalLink className="external-article-link" size={18} />
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Recent Updates */}
      <section className="external-section">
        <div className="external-section-content">
          <div className="external-section-header">
            <h2 className="external-section-title">{t('portal.recentUpdates')}</h2>
            <Link to="/portal/recent" className="external-view-all">
              {t('common.viewAll')} <ArrowRight size={16} />
            </Link>
          </div>
          <div className="external-recent-list">
            {recentArticles.map(article => (
              <Link
                key={article.id}
                to={`/portal/article/${article.id}`}
                className="external-recent-item"
              >
                <div className="external-recent-dot" />
                <div className="external-recent-content">
                  <h3 className="external-recent-title">{article.title}</h3>
                  <div className="external-recent-meta">
                    <span className="external-recent-category">{article.category}</span>
                    <span className="external-recent-date">
                      <Clock size={14} />
                      {new Date(article.date).toLocaleDateString()}
                    </span>
                  </div>
                </div>
                <ChevronRight className="external-recent-arrow" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="external-cta">
        <div className="external-cta-content">
          <h2 className="external-cta-title">{t('portal.ctaTitle')}</h2>
          <p className="external-cta-description">{t('portal.ctaDescription')}</p>
          <div className="external-cta-actions">
            <Link to="/login" className="btn btn-primary btn-lg">
              {t('portal.getStarted')}
            </Link>
            <Link to="/portal/contact" className="btn btn-secondary btn-lg">
              {t('portal.contactUs')}
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="external-footer">
        <div className="external-footer-content">
          <div className="external-footer-grid">
            <div className="external-footer-section">
              <div className="external-footer-logo">
                <div className="external-logo-icon">K</div>
                <span className="external-logo-text">KMS Portal</span>
              </div>
              <p className="external-footer-description">
                {t('portal.footerDescription')}
              </p>
            </div>

            <div className="external-footer-section">
              <h4 className="external-footer-title">{t('portal.footerLinks')}</h4>
              <ul className="external-footer-links">
                <li><Link to="/portal">{t('portal.home')}</Link></li>
                <li><Link to="/portal/knowledge">{t('portal.knowledgeBase')}</Link></li>
                <li><Link to="/portal/support">{t('portal.support')}</Link></li>
                <li><Link to="/portal/contact">{t('portal.contact')}</Link></li>
              </ul>
            </div>

            <div className="external-footer-section">
              <h4 className="external-footer-title">{t('portal.legal')}</h4>
              <ul className="external-footer-links">
                <li><Link to="/portal/privacy">{t('portal.privacy')}</Link></li>
                <li><Link to="/portal/terms">{t('portal.terms')}</Link></li>
                <li><Link to="/portal/accessibility">{t('portal.accessibility')}</Link></li>
              </ul>
            </div>
          </div>

          <div className="external-footer-bottom">
            <p>&copy; {new Date().getFullYear()} KMS Portal. {t('portal.allRightsReserved')}</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default ExternalPortalPage;
