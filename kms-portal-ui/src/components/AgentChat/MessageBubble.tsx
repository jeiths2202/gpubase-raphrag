/**
 * MessageBubble Component
 * Renders individual chat messages with support for user, assistant, and status messages.
 */

import React, { useState, useCallback, useEffect } from 'react';
import {
  Bot,
  User,
  Wrench,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  Search,
  FileText,
  AlertCircle,
  Database,
  Loader2,
  Image as ImageIcon,
  ChevronDown,
  ChevronRight,
  ThumbsUp,
  ThumbsDown,
  Upload,
  RefreshCw,
  X,
  ZoomIn,
  ZoomOut,
  Download,
} from 'lucide-react';
import { useTranslation } from '../../hooks/useTranslation';
import { MessageContent } from './MessageContent';
import { SearchResultCards } from './ExpandableSearchResultCard';
import { BlockRenderer } from './blocks';
import { AGENT_CONFIGS } from './constants';
import type { ChatMessage, ImageReference, AnswerBlock } from './types';
import type { AgentType } from '../../api/agent.api';
import type { SourceCitationInfo } from './blocks/types';

/**
 * Image Modal Component
 * Full-screen modal for viewing images with zoom functionality
 */
interface ImageModalProps {
  image: ImageReference;
  imageSrc: string;
  onClose: () => void;
}

const ImageModal: React.FC<ImageModalProps> = ({ image, imageSrc, onClose }) => {
  const [zoom, setZoom] = useState(1);
  const minZoom = 0.5;
  const maxZoom = 3;

  // Handle keyboard events
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === '+' || e.key === '=') setZoom(z => Math.min(z + 0.25, maxZoom));
      if (e.key === '-') setZoom(z => Math.max(z - 0.25, minZoom));
      if (e.key === '0') setZoom(1);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Handle backdrop click
  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  }, [onClose]);

  // Handle download
  const handleDownload = useCallback(() => {
    const link = document.createElement('a');
    link.href = imageSrc;
    link.download = `image-page-${image.pageNumber || 'unknown'}.png`;
    link.click();
  }, [imageSrc, image.pageNumber]);

  return (
    <div className="image-modal-overlay" onClick={handleBackdropClick}>
      <div className="image-modal-container">
        {/* Modal Header */}
        <div className="image-modal-header">
          <div className="image-modal-title">
            {image.figureReference && (
              <span className="image-modal-figure-ref">
                {image.figureReference.replace('fig_', 'Figure ').replace(/_/g, '.')}
              </span>
            )}
            {image.pageNumber && (
              <span className="image-modal-page">Page {image.pageNumber}</span>
            )}
          </div>
          <div className="image-modal-controls">
            <button
              className="image-modal-control"
              onClick={() => setZoom(z => Math.max(z - 0.25, minZoom))}
              title="Zoom out (-)"
              disabled={zoom <= minZoom}
            >
              <ZoomOut size={18} />
            </button>
            <span className="image-modal-zoom-level">{Math.round(zoom * 100)}%</span>
            <button
              className="image-modal-control"
              onClick={() => setZoom(z => Math.min(z + 0.25, maxZoom))}
              title="Zoom in (+)"
              disabled={zoom >= maxZoom}
            >
              <ZoomIn size={18} />
            </button>
            <button
              className="image-modal-control"
              onClick={handleDownload}
              title="Download"
            >
              <Download size={18} />
            </button>
            <button
              className="image-modal-control close"
              onClick={onClose}
              title="Close (Esc)"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Modal Body - Scrollable image container */}
        <div className="image-modal-body">
          <img
            src={imageSrc}
            alt={image.altText || image.figureCaption || image.description || 'Image'}
            style={{ transform: `scale(${zoom})`, transformOrigin: 'center center' }}
            className="image-modal-image"
          />
        </div>

        {/* Modal Footer - Caption/Description */}
        {(image.figureCaption || image.description) && (
          <div className="image-modal-footer">
            <p className="image-modal-caption">
              {image.figureCaption || image.description}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Collapsible Images Component
 * Shows thumbnails in collapsed state, full gallery when expanded
 * Includes click-to-zoom modal functionality
 */
interface CollapsibleImagesProps {
  images: ImageReference[];
  label: string;
}

const CollapsibleImages: React.FC<CollapsibleImagesProps> = ({ images, label }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedImage, setSelectedImage] = useState<{ image: ImageReference; src: string } | null>(null);

  // Generate image src from base64 data
  const getImageSrc = (image: ImageReference): string | null => {
    if (!image.imageBase64) return null;
    return image.imageBase64.startsWith('data:')
      ? image.imageBase64
      : `data:${image.mimeType || 'image/png'};base64,${image.imageBase64}`;
  };

  // Handle image click to open modal
  const handleImageClick = useCallback((image: ImageReference, src: string) => {
    setSelectedImage({ image, src });
  }, []);

  // Close modal
  const handleCloseModal = useCallback(() => {
    setSelectedImage(null);
  }, []);

  return (
    <div className="agent-message-images">
      {/* Collapsed header - clickable to expand */}
      <button
        className="agent-images-header"
        onClick={() => setIsExpanded(!isExpanded)}
        type="button"
      >
        <span className="agent-images-toggle">
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <ImageIcon size={12} />
        <span className="agent-images-label">{label}:</span>
        <span className="agent-images-count">{images.length}</span>

        {/* Mini thumbnails preview when collapsed */}
        {!isExpanded && (
          <div className="agent-images-thumbnails">
            {images.slice(0, 4).map((image, idx) => {
              const src = getImageSrc(image);
              return src ? (
                <img
                  key={idx}
                  src={src}
                  alt={`Thumbnail ${idx + 1}`}
                  className="agent-image-thumbnail"
                />
              ) : (
                <div key={idx} className="agent-image-thumbnail-placeholder">
                  <ImageIcon size={10} />
                </div>
              );
            })}
            {images.length > 4 && (
              <span className="agent-images-more">+{images.length - 4}</span>
            )}
          </div>
        )}
      </button>

      {/* Expanded gallery */}
      {isExpanded && (
        <div className="agent-images-gallery">
          {images.map((image, idx) => {
            const imageSrc = getImageSrc(image);
            return (
              <div
                key={idx}
                className="agent-image-item clickable"
                onClick={() => imageSrc && handleImageClick(image, imageSrc)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && imageSrc && handleImageClick(image, imageSrc)}
              >
                {imageSrc ? (
                  <>
                    <img
                      src={imageSrc}
                      alt={image.altText || image.figureCaption || image.description || `Image ${idx + 1}`}
                      className="agent-image-preview"
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        e.currentTarget.nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                    <div className="agent-image-placeholder hidden">
                      <ImageIcon size={24} />
                      <span>Failed to load</span>
                    </div>
                    <div className="agent-image-zoom-hint">
                      <ZoomIn size={16} />
                    </div>
                  </>
                ) : (
                  <div className="agent-image-placeholder">
                    <ImageIcon size={24} />
                  </div>
                )}
                <div className="agent-image-info">
                  {image.figureReference && (
                    <span className="agent-image-figure-ref">
                      {image.figureReference.replace('fig_', 'Figure ').replace(/_/g, '.')}
                    </span>
                  )}
                  <span className="agent-image-description">
                    {image.figureCaption || image.description?.substring(0, 100) || `Page ${image.pageNumber || 'N/A'}`}
                    {!image.figureCaption && image.description && image.description.length > 100 && '...'}
                  </span>
                  {image.similarity && (
                    <span className="agent-image-score">{Math.round(image.similarity * 100)}%</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Image Modal */}
      {selectedImage && (
        <ImageModal
          image={selectedImage.image}
          imageSrc={selectedImage.src}
          onClose={handleCloseModal}
        />
      )}
    </div>
  );
};

/** Feedback state for a message */
export type FeedbackType = 'thumbs_up' | 'thumbs_down' | null;

interface MessageBubbleProps {
  message: ChatMessage;
  onCopy: (content: string, messageId: string) => void;
  copiedMessageId: string | null;
  onCancel?: () => void;
  /** Callback for feedback (thumbs up/down) */
  onFeedback?: (messageId: string, type: 'thumbs_up' | 'thumbs_down') => void;
  /** Callback for registering as FAQ */
  onRegisterFAQ?: (question: string, answer: string, agentType?: AgentType) => void;
  /** Callback for regenerating response */
  onRegenerate?: (messageId: string) => void;
  /** Current feedback state per message */
  feedbackState?: Record<string, FeedbackType>;
  /** The user's original question (for FAQ registration) */
  userMessage?: string;
  /** User's role for permission checks */
  userRole?: 'user' | 'admin' | 'leader';
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  onCopy,
  copiedMessageId,
  onCancel,
  onFeedback,
  onRegisterFAQ,
  onRegenerate,
  feedbackState,
  userMessage,
  userRole,
}) => {
  const { t } = useTranslation();
  const isUser = message.role === 'user';
  const isStatus = message.role === 'status';
  const agentConfig = message.agentType ? AGENT_CONFIGS[message.agentType] : null;
  const AgentIcon = agentConfig?.icon || Bot;

  // Render status message differently
  if (isStatus) {
    // Translate status key using i18n
    const statusKey = message.content as 'crawling' | 'ready' | 'searching' | 'processing';
    const translatedMessage = t(`common.agent.status.${statusKey}`) || message.content;

    // Get appropriate icon based on status
    const getStatusIcon = () => {
      switch (statusKey) {
        case 'crawling':
        case 'processing':
          return <Loader2 size={18} className="spin" />;
        case 'searching':
          return <Search size={18} className="pulse" />;
        case 'ready':
          return <CheckCircle2 size={18} />;
        default:
          return <Database size={18} />;
      }
    };

    return (
      <div className={`agent-status-message ${message.statusType || ''} ${statusKey}`}>
        <div className="agent-status-icon">
          {getStatusIcon()}
        </div>
        <div className="agent-status-content">
          <span>{translatedMessage}</span>
          {(statusKey === 'crawling' || statusKey === 'processing' || statusKey === 'searching') && (
            <span className="agent-status-dots">
              <span className="dot">.</span>
              <span className="dot">.</span>
              <span className="dot">.</span>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={`agent-message ${message.role} ${message.isStreaming ? 'streaming' : ''}`}>
      {/* Avatar */}
      <div className="agent-message-avatar">
        {isUser ? <User size={18} /> : <AgentIcon size={18} />}
      </div>

      {/* Content */}
      <div className="agent-message-content">
        {/* Agent type badge */}
        {!isUser && agentConfig && (
          <div className="agent-message-badge">
            <AgentIcon size={12} />
            <span>{agentConfig.label}</span>
          </div>
        )}

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="agent-tool-calls">
            {message.toolCalls.map((tool, idx) => (
              <div key={idx} className={`agent-tool-call ${tool.status}`}>
                <div className="agent-tool-call-header">
                  <Wrench size={14} />
                  <span className="agent-tool-call-name">{tool.name}</span>
                  {tool.status === 'pending' && <Loader2 size={14} className="spin" />}
                  {tool.status === 'success' && <CheckCircle2 size={14} />}
                  {tool.status === 'error' && <XCircle size={14} />}
                </div>
                {tool.input && Object.keys(tool.input).length > 0 && (
                  <div className="agent-tool-call-input">
                    {/* If query was corrected, show corrected version with indicator */}
                    {tool.queryCorrected ? (
                      <code>
                        {JSON.stringify(
                          {
                            ...tool.input,
                            query: tool.correctedQuery,
                            _corrected: `LLM sent "${tool.originalLlmQuery}" → fixed to original`
                          },
                          null,
                          2
                        )}
                      </code>
                    ) : (
                      <code>{JSON.stringify(tool.input, null, 2)}</code>
                    )}
                  </div>
                )}
                {tool.output && (
                  <div className="agent-tool-call-output">
                    <span>{tool.output.substring(0, 200)}{tool.output.length > 200 ? '...' : ''}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Message text */}
        <div className="agent-message-text">
          {message.error ? (
            <div className="agent-message-error">
              <AlertCircle size={16} />
              <span>{message.content}</span>
            </div>
          ) : message.structuredBlocks && message.structuredBlocks.length > 0 ? (
            /* ChatGPT-style structured answer blocks */
            <BlockRenderer
              blocks={message.structuredBlocks as AnswerBlock[]}
              isStreaming={message.isStreaming}
              onSourceClick={(source: SourceCitationInfo) => {
                console.log('[MessageBubble] Source clicked:', source);
                // TODO: Implement source preview/navigation
              }}
            />
          ) : (
            /* Fallback to markdown rendering */
            <MessageContent content={message.content} />
          )}
          {message.isStreaming && !message.structuredBlocks && <span className="agent-typing-cursor" />}
        </div>

        {/* Expandable Search Results - Individual cards with text, images, tables */}
        {message.searchResults && message.searchResults.length > 0 && (
          <SearchResultCards
            results={message.searchResults}
            title={t('common.agent.searchResults') || '검색 결과'}
            reliability={message.sourceReliability}
          />
        )}

        {/* Sources - Legacy display (shown only if no searchResults) */}
        {message.sources && message.sources.length > 0 && (!message.searchResults || message.searchResults.length === 0) && (
          <div className="agent-message-sources">
            <span className="agent-sources-label">Sources:</span>
            {message.sources.map((source, idx) => {
              // Handle score safely to prevent NaN display
              const scoreValue = typeof source.score === 'number' && !isNaN(source.score)
                ? Math.round(source.score * 100)
                : null;
              return (
                <div key={idx} className="agent-source-item">
                  <FileText size={12} />
                  <span>
                    {source.source}
                    {source.page_number && !source.source?.includes('p.') && (
                      <span className="agent-source-page"> (p.{source.page_number})</span>
                    )}
                  </span>
                  {scoreValue !== null && (
                    <span className="agent-source-score">{scoreValue}%</span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Images from Multimodal RAG or Figure References - Collapsible */}
        {message.images && message.images.length > 0 && (
          <CollapsibleImages
            images={message.images}
            label={message.images[0]?.figureReference ? 'Document Figures' : 'Related Images'}
          />
        )}

        {/* Actions */}
        {!isUser && !message.isStreaming && (
          <div className="agent-message-actions">
            {/* Copy button */}
            <button
              className={`agent-message-action ${copiedMessageId === message.id ? 'copied' : ''}`}
              onClick={() => onCopy(message.content, message.id)}
              title={t('common.copy') || 'Copy'}
            >
              {copiedMessageId === message.id ? <Check size={14} /> : <Copy size={14} />}
            </button>

            {/* Thumbs up button */}
            {onFeedback && (
              <button
                className={`agent-message-action ${feedbackState?.[message.id] === 'thumbs_up' ? 'active thumbs-up' : ''}`}
                onClick={() => onFeedback(message.id, 'thumbs_up')}
                title={
                  feedbackState?.[message.id] === 'thumbs_up'
                    ? t('common.agent.feedback.clickToCancel') || 'Click to cancel'
                    : t('common.agent.feedback.thumbsUp') || 'Helpful'
                }
              >
                <ThumbsUp size={14} />
              </button>
            )}

            {/* Thumbs down button */}
            {onFeedback && (
              <button
                className={`agent-message-action ${feedbackState?.[message.id] === 'thumbs_down' ? 'active thumbs-down' : ''}`}
                onClick={() => onFeedback(message.id, 'thumbs_down')}
                title={
                  feedbackState?.[message.id] === 'thumbs_down'
                    ? t('common.agent.feedback.clickToCancel') || 'Click to cancel'
                    : t('common.agent.feedback.thumbsDown') || 'Not helpful'
                }
              >
                <ThumbsDown size={14} />
              </button>
            )}

            {/* FAQ registration button (admin/leader only) */}
            {onRegisterFAQ && (userRole === 'admin' || userRole === 'leader') && (
              <button
                className="agent-message-action"
                onClick={() => onRegisterFAQ(userMessage || '', message.content, message.agentType)}
                title={t('common.agent.feedback.registerFAQ') || 'Register as FAQ'}
              >
                <Upload size={14} />
              </button>
            )}

            {/* Regenerate button */}
            {onRegenerate && (
              <button
                className="agent-message-action"
                onClick={() => onRegenerate(message.id)}
                title={t('common.agent.feedback.regenerate') || 'Regenerate'}
              >
                <RefreshCw size={14} />
              </button>
            )}
          </div>
        )}

        {/* Cancel button for streaming */}
        {message.isStreaming && onCancel && (
          <button className="agent-message-cancel" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;
