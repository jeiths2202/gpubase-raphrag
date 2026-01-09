/**
 * IMS Search Bar Component
 *
 * Natural language search input with job creation and product selection
 */

import React, { useState } from 'react';
import { Search, Loader2, Settings2, ChevronDown, Check, Sparkles } from 'lucide-react';
import { createCrawlJob } from '../services/ims-api';
import { useIMSStore } from '../store/imsStore';
import { useAuthStore } from '../../../store/authStore';
import { IMS_PRODUCTS } from '../types';
import type { IMSJob } from '../types';

// Default selected products (all OpenFrame + ProSort + ProTrieve)
const DEFAULT_PRODUCT_CODES = IMS_PRODUCTS.map(p => p.code);

interface IMSSearchBarProps {
  onJobCreated: (job: IMSJob) => void;
  t: (key: string) => string;
}

export const IMSSearchBar: React.FC<IMSSearchBarProps> = ({ onJobCreated, t }) => {
  const { isSearching, setIsSearching, setSearchQuery, setCurrentJob } = useIMSStore();
  const { user } = useAuthStore();

  // Check if user has Pro access (based on role - admin/leader have pro features)
  const hasProAccess = user?.role === 'admin' || user?.role === 'leader';

  const [query, setQuery] = useState('');
  const [showOptions, setShowOptions] = useState(false);
  const [showProductDropdown, setShowProductDropdown] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<string[]>(DEFAULT_PRODUCT_CODES);
  const [options, setOptions] = useState({
    includeAttachments: true,
    includeRelated: true,
    enableDeepSearch: false,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || isSearching) return;

    setIsSearching(true);
    setSearchQuery(query);

    try {
      const job = await createCrawlJob({
        query: query.trim(),
        include_attachments: options.includeAttachments,
        include_related_issues: options.includeRelated,
        product_codes: selectedProducts.length > 0 ? selectedProducts : undefined,
      });

      // Check if job is cached - if so, fetch results directly without streaming
      if (job.is_cached && job.result_issue_ids && job.result_issue_ids.length > 0) {
        console.log('[IMS] Using cached results:', job.result_issue_ids.length, 'issues');
        // Fetch cached results directly
        const { fetchResults } = useIMSStore.getState();
        await fetchResults(query.trim(), {
          totalIssues: job.issues_found,
          successfulIssues: job.issues_crawled,
          duration: 0, // Cached = instant
          outcome: 'success',
          relatedIssues: 0,
          attachments: job.attachments_processed,
          resultIssueIds: job.result_issue_ids,
          progressSnapshot: {
            status: 'completed',
            progress: 100,
            currentStep: 'Cached results',
            timestamp: new Date().toISOString(),
            issuesFound: job.issues_found,
            issuesCrawled: job.issues_crawled,
            relatedCount: 0,
          },
        });
      } else {
        // New job - show progress tracker
        setCurrentJob(job);
        onJobCreated(job);
      }
    } catch (error) {
      console.error('[IMS] Failed to create crawl job:', error);
      setIsSearching(false);
    }
  };

  const handleOptionChange = (key: keyof typeof options, value: boolean | number) => {
    setOptions((prev) => ({ ...prev, [key]: value }));
  };

  const toggleProduct = (code: string) => {
    setSelectedProducts(prev =>
      prev.includes(code)
        ? prev.filter(c => c !== code)
        : [...prev, code]
    );
  };

  const selectAllProducts = () => {
    setSelectedProducts(DEFAULT_PRODUCT_CODES);
  };

  const clearAllProducts = () => {
    setSelectedProducts([]);
  };

  const selectOpenFrameOnly = () => {
    setSelectedProducts(IMS_PRODUCTS.filter(p => p.category === 'openframe').map(p => p.code));
  };

  const getSelectedProductsLabel = () => {
    if (selectedProducts.length === 0) return t('ims.search.noProducts');
    if (selectedProducts.length === DEFAULT_PRODUCT_CODES.length) return t('ims.search.allProducts');
    if (selectedProducts.length <= 3) {
      return IMS_PRODUCTS
        .filter(p => selectedProducts.includes(p.code))
        .map(p => p.name.replace('OpenFrame ', 'OF '))
        .join(', ');
    }
    return `${selectedProducts.length} ${t('ims.search.productsSelected')}`;
  };

  return (
    <div className="ims-search">
      <form className="ims-search__form" onSubmit={handleSubmit}>
        {/* Product Selection */}
        <div className="ims-search__product-selector">
          <button
            type="button"
            className="ims-search__product-btn"
            onClick={() => setShowProductDropdown(!showProductDropdown)}
            disabled={isSearching}
          >
            <span className="ims-search__product-label">{getSelectedProductsLabel()}</span>
            <ChevronDown size={16} className={showProductDropdown ? 'rotated' : ''} />
          </button>

          {showProductDropdown && (
            <div className="ims-search__product-dropdown">
              <div className="ims-search__product-actions">
                <button type="button" onClick={selectAllProducts}>{t('ims.search.selectAll')}</button>
                <button type="button" onClick={selectOpenFrameOnly}>OpenFrame</button>
                <button type="button" onClick={clearAllProducts}>{t('ims.search.clearAll')}</button>
              </div>
              <div className="ims-search__product-list">
                <div className="ims-search__product-category">
                  <span className="category-label">OpenFrame</span>
                  {IMS_PRODUCTS.filter(p => p.category === 'openframe').map(product => (
                    <label key={product.code} className="ims-search__product-item">
                      <input
                        type="checkbox"
                        checked={selectedProducts.includes(product.code)}
                        onChange={() => toggleProduct(product.code)}
                      />
                      <Check size={14} className="check-icon" />
                      <span>{product.name.replace('OpenFrame ', '')}</span>
                    </label>
                  ))}
                </div>
                <div className="ims-search__product-category">
                  <span className="category-label">{t('ims.search.otherProducts')}</span>
                  {IMS_PRODUCTS.filter(p => p.category === 'other').map(product => (
                    <label key={product.code} className="ims-search__product-item">
                      <input
                        type="checkbox"
                        checked={selectedProducts.includes(product.code)}
                        onChange={() => toggleProduct(product.code)}
                      />
                      <Check size={14} className="check-icon" />
                      <span>{product.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="ims-search__input-wrapper">
          <Search size={20} className="ims-search__icon" />
          <input
            type="text"
            className="ims-search__input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('ims.search.placeholder')}
            disabled={isSearching}
          />
          <button
            type="button"
            className={`ims-search__options-btn ${showOptions ? 'active' : ''}`}
            onClick={() => setShowOptions(!showOptions)}
            aria-label="Search options"
          >
            <Settings2 size={18} />
          </button>
        </div>

        <button
          type="submit"
          className="btn btn-primary ims-search__btn"
          disabled={!query.trim() || isSearching || selectedProducts.length === 0}
        >
          {isSearching ? (
            <>
              <Loader2 size={18} className="spin" />
              {t('ims.search.searching')}
            </>
          ) : (
            <>
              <Search size={18} />
              {t('ims.search.button')}
            </>
          )}
        </button>
      </form>

      {/* Search Options */}
      {showOptions && (
        <div className="ims-search__options">
          <div className="ims-search__option">
            <label className="ims-checkbox">
              <input
                type="checkbox"
                checked={options.includeAttachments}
                onChange={(e) => handleOptionChange('includeAttachments', e.target.checked)}
              />
              <span>{t('ims.search.includeAttachments')}</span>
            </label>
          </div>
          <div className="ims-search__option">
            <label className="ims-checkbox">
              <input
                type="checkbox"
                checked={options.includeRelated}
                onChange={(e) => handleOptionChange('includeRelated', e.target.checked)}
              />
              <span>{t('ims.search.includeRelated')}</span>
            </label>
          </div>
          <div className="ims-search__option">
            <label className={`ims-checkbox ims-checkbox--pro ${!hasProAccess ? 'disabled' : ''}`}>
              <input
                type="checkbox"
                checked={options.enableDeepSearch}
                onChange={(e) => hasProAccess && handleOptionChange('enableDeepSearch', e.target.checked)}
                disabled={!hasProAccess}
              />
              <Sparkles size={14} className="ims-checkbox__icon" />
              <span>{t('ims.search.deepSearch')}</span>
              <span className="ims-pro-badge">Pro</span>
            </label>
          </div>
        </div>
      )}
    </div>
  );
};

export default IMSSearchBar;
