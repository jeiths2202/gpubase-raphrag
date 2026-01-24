/**
 * ImageBlock Component
 * Renders images with optional caption and zoom functionality
 */
import React, { useState } from 'react';
import { Image as ImageIcon, ZoomIn, X } from 'lucide-react';
import type { AnswerBlock, BaseBlockProps } from './types';

interface ImageBlockProps extends BaseBlockProps {
  block: AnswerBlock;
}

export const ImageBlock: React.FC<ImageBlockProps> = ({ block, className }) => {
  const [isZoomed, setIsZoomed] = useState(false);
  const [imageError, setImageError] = useState(false);

  if (!block.url) return null;

  const handleZoom = () => {
    setIsZoomed(true);
  };

  const handleCloseZoom = () => {
    setIsZoomed(false);
  };

  return (
    <>
      <figure className={`answer-block answer-block-image ${className || ''}`}>
        {imageError ? (
          <div className="image-placeholder">
            <ImageIcon size={32} />
            <span>Image unavailable</span>
          </div>
        ) : (
          <div className="image-container">
            <img
              src={block.url}
              alt={block.caption || 'Image'}
              onError={() => setImageError(true)}
              loading="lazy"
            />
            <button
              className="image-zoom-btn"
              onClick={handleZoom}
              title="Zoom image"
              type="button"
            >
              <ZoomIn size={16} />
            </button>
          </div>
        )}
        {block.caption && (
          <figcaption>{block.caption}</figcaption>
        )}
      </figure>

      {/* Zoom modal */}
      {isZoomed && (
        <div className="image-zoom-modal" onClick={handleCloseZoom}>
          <button
            className="zoom-close-btn"
            onClick={handleCloseZoom}
            type="button"
          >
            <X size={24} />
          </button>
          <img
            src={block.url}
            alt={block.caption || 'Image'}
            onClick={(e) => e.stopPropagation()}
          />
          {block.caption && (
            <p className="zoom-caption">{block.caption}</p>
          )}
        </div>
      )}
    </>
  );
};

export default ImageBlock;
