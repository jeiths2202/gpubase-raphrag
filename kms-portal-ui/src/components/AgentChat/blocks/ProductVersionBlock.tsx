/**
 * ProductVersionBlock Component
 * Displays multi-product search results with collapsible platform sections
 *
 * Features:
 * - Platform badges (MVS, MSP, XSP, VOS3)
 * - Collapsible sections per platform
 * - Version tags
 * - "Platform differences" warning badge
 */
import React, { useState } from 'react';
import { ChevronDown, ChevronRight, FileText, AlertTriangle } from 'lucide-react';
import type { AnswerBlock, ProductVariantData } from './types';
import './ProductVersionBlock.css';

interface ProductVersionBlockProps {
  block: AnswerBlock;
}

/**
 * Get platform badge color class
 */
const getPlatformClass = (platform: string): string => {
  const normalized = platform.toUpperCase();
  switch (normalized) {
    case 'MVS':
      return 'platform-mvs';
    case 'MSP':
      return 'platform-msp';
    case 'XSP':
      return 'platform-xsp';
    case 'VOS3':
      return 'platform-vos3';
    default:
      return 'platform-common';
  }
};

/**
 * Format page numbers for display
 */
const formatPageNumbers = (pages?: number[]): string => {
  if (!pages || pages.length === 0) return '';
  if (pages.length === 1) return `p.${pages[0]}`;
  return `p.${pages[0]}-${pages[pages.length - 1]}`;
};

export const ProductVersionBlock: React.FC<ProductVersionBlockProps> = ({ block }) => {
  // Default to MVS expanded, or first platform if MVS not present
  const availablePlatforms = block.available_platforms || [];
  const defaultExpanded = availablePlatforms.includes('MVS') ? 'MVS' : (availablePlatforms[0] || '');
  const [expandedPlatforms, setExpandedPlatforms] = useState<Set<string>>(
    new Set(defaultExpanded ? [defaultExpanded] : [])
  );

  const variants = block.variants || [];
  const hasDifferences = block.has_differences || false;
  const name = block.name || 'Unknown';
  const docType = block.doc_type || 'commands';

  const toggleExpand = (platform: string) => {
    setExpandedPlatforms(prev => {
      const newSet = new Set(prev);
      if (newSet.has(platform)) {
        newSet.delete(platform);
      } else {
        newSet.add(platform);
      }
      return newSet;
    });
  };

  const expandAll = () => {
    setExpandedPlatforms(new Set(variants.map(v => v.platform)));
  };

  const collapseAll = () => {
    setExpandedPlatforms(new Set());
  };

  // Get doc type label
  const getDocTypeLabel = (type: string): string => {
    switch (type) {
      case 'commands':
        return 'COMMAND';
      case 'error-codes':
        return 'ERROR CODE';
      case 'glossary':
        return 'TERM';
      case 'apis':
        return 'API';
      default:
        return type.toUpperCase();
    }
  };

  if (variants.length === 0) {
    return null;
  }

  return (
    <div className="product-version-block">
      {/* Header with name, badges, and controls */}
      <div className="pv-header">
        <div className="pv-header-left">
          <span className="pv-doc-type">[{getDocTypeLabel(docType)}]</span>
          <span className="pv-name">{name}</span>
        </div>

        <div className="pv-header-right">
          {/* Platform badges */}
          <div className="pv-badges">
            {availablePlatforms.map(platform => (
              <span
                key={platform}
                className={`platform-badge ${getPlatformClass(platform)}`}
              >
                {platform}
              </span>
            ))}
          </div>

          {/* Warning badge for differences */}
          {hasDifferences && (
            <span className="warning-badge">
              <AlertTriangle size={12} />
              <span>Platform differences</span>
            </span>
          )}

          {/* Expand/Collapse controls */}
          {variants.length > 1 && (
            <div className="pv-controls">
              <button
                className="pv-control-btn"
                onClick={expandAll}
                title="Expand all"
              >
                Expand
              </button>
              <span className="pv-control-sep">/</span>
              <button
                className="pv-control-btn"
                onClick={collapseAll}
                title="Collapse all"
              >
                Collapse
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Collapsible platform sections */}
      <div className="pv-sections">
        {variants.map((variant: ProductVariantData) => {
          const isExpanded = expandedPlatforms.has(variant.platform);
          const platform = variant.platform;

          return (
            <div key={platform} className="pv-section">
              <button
                className={`pv-section-header ${isExpanded ? 'expanded' : ''}`}
                onClick={() => toggleExpand(platform)}
              >
                <span className="pv-section-toggle">
                  {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                </span>
                <span className={`platform-badge small ${getPlatformClass(platform)}`}>
                  {platform}
                </span>
                {variant.product_version && (
                  <span className="version-tag">v{variant.product_version}</span>
                )}
                {variant.document_version && (
                  <span className="doc-version-tag">{variant.document_version}</span>
                )}
              </button>

              {isExpanded && (
                <div className="pv-section-content">
                  {/* Description */}
                  {variant.description && (
                    <div className="pv-field">
                      <span className="pv-field-label">Description:</span>
                      <p className="pv-field-value">{variant.description}</p>
                    </div>
                  )}

                  {/* Syntax (for commands) */}
                  {variant.syntax && (
                    <div className="pv-field">
                      <span className="pv-field-label">Syntax:</span>
                      <code className="pv-syntax">{variant.syntax}</code>
                    </div>
                  )}

                  {/* Solution (for error codes) */}
                  {variant.solution && (
                    <div className="pv-field">
                      <span className="pv-field-label">Solution:</span>
                      <p className="pv-field-value">{variant.solution}</p>
                    </div>
                  )}

                  {/* Source reference */}
                  {(variant.source_pdf || (variant.page_numbers && variant.page_numbers.length > 0)) && (
                    <div className="pv-source">
                      <FileText size={12} />
                      <span>
                        {variant.source_pdf || 'Source'}
                        {variant.page_numbers && variant.page_numbers.length > 0 && (
                          <> ({formatPageNumbers(variant.page_numbers)})</>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ProductVersionBlock;
