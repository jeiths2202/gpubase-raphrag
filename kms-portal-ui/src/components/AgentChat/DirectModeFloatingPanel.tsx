/**
 * DirectModeFloatingPanel Component
 *
 * Floating panel for displaying Direct mode search results.
 * Features:
 * - Draggable (move by dragging header)
 * - Resizable (resize from edges/corners)
 * - Multiple panels support
 * - Minimize/Maximize support
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  X,
  Minus,
  Maximize2,
  GripHorizontal,
  Search,
  MessageSquare,
} from 'lucide-react';
import { MessageContent } from './MessageContent';
import { SearchResultCards } from './ExpandableSearchResultCard';
import type { ExpandableSearchResult, SourceReliability } from './types';

export interface FloatingPanelData {
  id: string;
  title: string;
  query: string;
  content: string;
  searchResults?: ExpandableSearchResult[];
  sourceReliability?: SourceReliability;
  timestamp: Date;
  isMinimized: boolean;
  position: { x: number; y: number };
  size: { width: number; height: number };
  zIndex: number;
}

interface DirectModeFloatingPanelProps {
  panel: FloatingPanelData;
  onClose: (id: string) => void;
  onMinimize: (id: string) => void;
  onRestore: (id: string) => void;
  onBringToFront: (id: string) => void;
  onUpdatePosition: (id: string, position: { x: number; y: number }) => void;
  onUpdateSize: (id: string, size: { width: number; height: number }) => void;
  t: (key: string) => string;
}

const MIN_WIDTH = 320;
const MIN_HEIGHT = 200;

export const DirectModeFloatingPanel: React.FC<DirectModeFloatingPanelProps> = ({
  panel,
  onClose,
  onMinimize,
  onRestore,
  onBringToFront,
  onUpdatePosition,
  onUpdateSize,
  t,
}) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [resizeDirection, setResizeDirection] = useState<string>('');
  const dragStartRef = useRef({ x: 0, y: 0, panelX: 0, panelY: 0 });
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0, panelX: 0, panelY: 0 });

  // Handle drag start
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.floating-panel-controls')) return;

    e.preventDefault();
    setIsDragging(true);
    onBringToFront(panel.id);

    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panelX: panel.position.x,
      panelY: panel.position.y,
    };
  }, [panel.id, panel.position, onBringToFront]);

  // Handle resize start
  const handleResizeStart = useCallback((e: React.MouseEvent, direction: string) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    setResizeDirection(direction);
    onBringToFront(panel.id);

    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: panel.size.width,
      height: panel.size.height,
      panelX: panel.position.x,
      panelY: panel.position.y,
    };
  }, [panel.id, panel.size, panel.position, onBringToFront]);

  // Handle mouse move for dragging and resizing
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const deltaX = e.clientX - dragStartRef.current.x;
        const deltaY = e.clientY - dragStartRef.current.y;

        const newX = Math.max(0, Math.min(window.innerWidth - 100, dragStartRef.current.panelX + deltaX));
        const newY = Math.max(0, Math.min(window.innerHeight - 50, dragStartRef.current.panelY + deltaY));

        onUpdatePosition(panel.id, { x: newX, y: newY });
      }

      if (isResizing) {
        const deltaX = e.clientX - resizeStartRef.current.x;
        const deltaY = e.clientY - resizeStartRef.current.y;

        let newWidth = resizeStartRef.current.width;
        let newHeight = resizeStartRef.current.height;
        let newX = resizeStartRef.current.panelX;
        let newY = resizeStartRef.current.panelY;

        // Handle different resize directions
        if (resizeDirection.includes('e')) {
          newWidth = Math.max(MIN_WIDTH, resizeStartRef.current.width + deltaX);
        }
        if (resizeDirection.includes('w')) {
          const widthDelta = Math.min(deltaX, resizeStartRef.current.width - MIN_WIDTH);
          newWidth = resizeStartRef.current.width - widthDelta;
          newX = resizeStartRef.current.panelX + widthDelta;
        }
        if (resizeDirection.includes('s')) {
          newHeight = Math.max(MIN_HEIGHT, resizeStartRef.current.height + deltaY);
        }
        if (resizeDirection.includes('n')) {
          const heightDelta = Math.min(deltaY, resizeStartRef.current.height - MIN_HEIGHT);
          newHeight = resizeStartRef.current.height - heightDelta;
          newY = resizeStartRef.current.panelY + heightDelta;
        }

        onUpdateSize(panel.id, { width: newWidth, height: newHeight });
        if (resizeDirection.includes('w') || resizeDirection.includes('n')) {
          onUpdatePosition(panel.id, { x: newX, y: newY });
        }
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      setIsResizing(false);
      setResizeDirection('');
    };

    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, isResizing, resizeDirection, panel.id, onUpdatePosition, onUpdateSize]);

  // Handle panel click to bring to front
  const handlePanelClick = useCallback(() => {
    onBringToFront(panel.id);
  }, [panel.id, onBringToFront]);

  if (panel.isMinimized) {
    return (
      <div
        className="floating-panel-minimized"
        style={{ zIndex: panel.zIndex }}
        onClick={() => onRestore(panel.id)}
      >
        <MessageSquare size={14} />
        <span className="floating-panel-minimized-title">
          {panel.title.length > 20 ? panel.title.slice(0, 20) + '...' : panel.title}
        </span>
        <Maximize2 size={14} />
      </div>
    );
  }

  return (
    <div
      ref={panelRef}
      className={`floating-panel ${isDragging ? 'dragging' : ''} ${isResizing ? 'resizing' : ''}`}
      style={{
        left: panel.position.x,
        top: panel.position.y,
        width: panel.size.width,
        height: panel.size.height,
        zIndex: panel.zIndex,
      }}
      onClick={handlePanelClick}
    >
      {/* Resize handles */}
      <div className="resize-handle resize-n" onMouseDown={(e) => handleResizeStart(e, 'n')} />
      <div className="resize-handle resize-s" onMouseDown={(e) => handleResizeStart(e, 's')} />
      <div className="resize-handle resize-e" onMouseDown={(e) => handleResizeStart(e, 'e')} />
      <div className="resize-handle resize-w" onMouseDown={(e) => handleResizeStart(e, 'w')} />
      <div className="resize-handle resize-ne" onMouseDown={(e) => handleResizeStart(e, 'ne')} />
      <div className="resize-handle resize-nw" onMouseDown={(e) => handleResizeStart(e, 'nw')} />
      <div className="resize-handle resize-se" onMouseDown={(e) => handleResizeStart(e, 'se')} />
      <div className="resize-handle resize-sw" onMouseDown={(e) => handleResizeStart(e, 'sw')} />

      {/* Header (draggable area) */}
      <div className="floating-panel-header" onMouseDown={handleDragStart}>
        <div className="floating-panel-drag-handle">
          <GripHorizontal size={14} />
        </div>
        <div className="floating-panel-title">
          <Search size={14} />
          <span>{panel.title}</span>
        </div>
        <div className="floating-panel-controls">
          <button
            className="floating-panel-control minimize"
            onClick={() => onMinimize(panel.id)}
            title={t('common.minimize') || 'Minimize'}
          >
            <Minus size={14} />
          </button>
          <button
            className="floating-panel-control close"
            onClick={() => onClose(panel.id)}
            title={t('common.close') || 'Close'}
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="floating-panel-content">
        {/* Query display */}
        <div className="floating-panel-query">
          <span className="floating-panel-query-label">{t('common.query') || 'Query'}:</span>
          <span className="floating-panel-query-text">{panel.query}</span>
        </div>

        {/* Search Results Cards (if available) */}
        {panel.searchResults && panel.searchResults.length > 0 && (
          <SearchResultCards
            results={panel.searchResults}
            title={t('common.agent.searchResults') || 'Search Results'}
            reliability={panel.sourceReliability}
          />
        )}

        {/* Formatted content (markdown) */}
        {panel.content && (
          <div className="floating-panel-markdown">
            <MessageContent content={panel.content} />
          </div>
        )}
      </div>

      {/* Footer with timestamp */}
      <div className="floating-panel-footer">
        <span className="floating-panel-timestamp">
          {panel.timestamp.toLocaleTimeString()}
        </span>
      </div>
    </div>
  );
};

export default DirectModeFloatingPanel;
