/**
 * SkeletonBlock Component
 * Loading skeleton for blocks during streaming
 */
import React from 'react';
import type { BaseBlockProps, BlockType } from './types';

interface SkeletonBlockProps extends BaseBlockProps {
  type?: BlockType;
}

export const SkeletonBlock: React.FC<SkeletonBlockProps> = ({ type, className }) => {
  // Render different skeleton shapes based on expected block type
  const renderSkeleton = () => {
    switch (type) {
      case 'heading':
        return (
          <div className="skeleton-heading">
            <div className="skeleton-line" style={{ width: '60%', height: '24px' }} />
          </div>
        );
      case 'list':
        return (
          <div className="skeleton-list">
            <div className="skeleton-line" style={{ width: '80%' }} />
            <div className="skeleton-line" style={{ width: '70%' }} />
            <div className="skeleton-line" style={{ width: '75%' }} />
          </div>
        );
      case 'code':
        return (
          <div className="skeleton-code">
            <div className="skeleton-line" style={{ width: '90%' }} />
            <div className="skeleton-line" style={{ width: '70%' }} />
            <div className="skeleton-line" style={{ width: '85%' }} />
            <div className="skeleton-line" style={{ width: '60%' }} />
          </div>
        );
      case 'table':
        return (
          <div className="skeleton-table">
            <div className="skeleton-row">
              <div className="skeleton-cell" />
              <div className="skeleton-cell" />
              <div className="skeleton-cell" />
            </div>
            <div className="skeleton-row">
              <div className="skeleton-cell" />
              <div className="skeleton-cell" />
              <div className="skeleton-cell" />
            </div>
          </div>
        );
      case 'source_citation':
        return (
          <div className="skeleton-citation">
            <div className="skeleton-line" style={{ width: '40%', height: '16px' }} />
          </div>
        );
      default:
        // Default text skeleton
        return (
          <div className="skeleton-text">
            <div className="skeleton-line" style={{ width: '100%' }} />
            <div className="skeleton-line" style={{ width: '95%' }} />
            <div className="skeleton-line" style={{ width: '80%' }} />
          </div>
        );
    }
  };

  return (
    <div className={`answer-block answer-block-skeleton ${type ? `skeleton-${type}` : ''} ${className || ''}`}>
      {renderSkeleton()}
    </div>
  );
};

export default SkeletonBlock;
