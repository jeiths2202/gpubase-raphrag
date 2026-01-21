/**
 * FloatingChatWindow Component
 *
 * A draggable and resizable container for the chat panel.
 * Features:
 * - Drag by header to move
 * - Resize from edges/corners
 * - Minimize to taskbar
 * - Multiple windows support
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import {
  X,
  Minus,
  GripHorizontal,
  MessageSquare,
  Maximize2,
  Plus,
  Monitor,
} from 'lucide-react';

export interface FloatingWindowData {
  id: string;
  title: string;
  isMinimized: boolean;
  position: { x: number; y: number };
  size: { width: number; height: number };
  zIndex: number;
}

interface FloatingChatWindowProps {
  windowData: FloatingWindowData;
  onClose: (id: string) => void;
  onMinimize: (id: string) => void;
  onBringToFront: (id: string) => void;
  onUpdatePosition: (id: string, position: { x: number; y: number }) => void;
  onUpdateSize: (id: string, size: { width: number; height: number }) => void;
  onUpdateTitle: (id: string, title: string) => void;
  onNewWindow?: () => void;
  onExitFloating?: () => void;
  children: React.ReactNode;
}

const MIN_WIDTH = 400;
const MIN_HEIGHT = 300;

export const FloatingChatWindow: React.FC<FloatingChatWindowProps> = ({
  windowData,
  onClose,
  onMinimize,
  onBringToFront,
  onUpdatePosition,
  onUpdateSize,
  onNewWindow,
  onExitFloating,
  children,
}) => {
  const windowRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isResizing, setIsResizing] = useState(false);
  const [resizeDirection, setResizeDirection] = useState<string>('');
  const dragStartRef = useRef({ x: 0, y: 0, windowX: 0, windowY: 0 });
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0, windowX: 0, windowY: 0 });

  // Handle drag start
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.floating-window-controls')) return;

    e.preventDefault();
    setIsDragging(true);
    onBringToFront(windowData.id);

    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      windowX: windowData.position.x,
      windowY: windowData.position.y,
    };
  }, [windowData.id, windowData.position, onBringToFront]);

  // Handle resize start
  const handleResizeStart = useCallback((e: React.MouseEvent, direction: string) => {
    e.preventDefault();
    e.stopPropagation();
    setIsResizing(true);
    setResizeDirection(direction);
    onBringToFront(windowData.id);

    resizeStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      width: windowData.size.width,
      height: windowData.size.height,
      windowX: windowData.position.x,
      windowY: windowData.position.y,
    };
  }, [windowData.id, windowData.size, windowData.position, onBringToFront]);

  // Handle mouse move for dragging and resizing
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        const deltaX = e.clientX - dragStartRef.current.x;
        const deltaY = e.clientY - dragStartRef.current.y;

        const newX = Math.max(0, Math.min(window.innerWidth - 100, dragStartRef.current.windowX + deltaX));
        const newY = Math.max(0, Math.min(window.innerHeight - 50, dragStartRef.current.windowY + deltaY));

        onUpdatePosition(windowData.id, { x: newX, y: newY });
      }

      if (isResizing) {
        const deltaX = e.clientX - resizeStartRef.current.x;
        const deltaY = e.clientY - resizeStartRef.current.y;

        let newWidth = resizeStartRef.current.width;
        let newHeight = resizeStartRef.current.height;
        let newX = resizeStartRef.current.windowX;
        let newY = resizeStartRef.current.windowY;

        if (resizeDirection.includes('e')) {
          newWidth = Math.max(MIN_WIDTH, resizeStartRef.current.width + deltaX);
        }
        if (resizeDirection.includes('w')) {
          const widthDelta = Math.min(deltaX, resizeStartRef.current.width - MIN_WIDTH);
          newWidth = resizeStartRef.current.width - widthDelta;
          newX = resizeStartRef.current.windowX + widthDelta;
        }
        if (resizeDirection.includes('s')) {
          newHeight = Math.max(MIN_HEIGHT, resizeStartRef.current.height + deltaY);
        }
        if (resizeDirection.includes('n')) {
          const heightDelta = Math.min(deltaY, resizeStartRef.current.height - MIN_HEIGHT);
          newHeight = resizeStartRef.current.height - heightDelta;
          newY = resizeStartRef.current.windowY + heightDelta;
        }

        onUpdateSize(windowData.id, { width: newWidth, height: newHeight });
        if (resizeDirection.includes('w') || resizeDirection.includes('n')) {
          onUpdatePosition(windowData.id, { x: newX, y: newY });
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
  }, [isDragging, isResizing, resizeDirection, windowData.id, onUpdatePosition, onUpdateSize]);

  // Handle window click to bring to front
  const handleWindowClick = useCallback(() => {
    onBringToFront(windowData.id);
  }, [windowData.id, onBringToFront]);

  if (windowData.isMinimized) {
    return null; // Minimized windows are rendered in the taskbar
  }

  return (
    <div
      ref={windowRef}
      className={`floating-chat-window ${isDragging ? 'dragging' : ''} ${isResizing ? 'resizing' : ''}`}
      style={{
        left: windowData.position.x,
        top: windowData.position.y,
        width: windowData.size.width,
        height: windowData.size.height,
        zIndex: windowData.zIndex,
      }}
      onClick={handleWindowClick}
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

      {/* Window header (draggable) */}
      <div className="floating-window-header" onMouseDown={handleDragStart}>
        <div className="floating-window-drag-handle">
          <GripHorizontal size={14} />
        </div>
        <div className="floating-window-title">
          <MessageSquare size={14} />
          <span>{windowData.title}</span>
        </div>
        <div className="floating-window-controls">
          {onNewWindow && (
            <button
              className="floating-window-control new-window"
              onClick={(e) => {
                e.stopPropagation();
                console.log('[FloatingChatWindow] New window button clicked');
                onNewWindow();
              }}
              title="New Window"
            >
              <Plus size={14} />
            </button>
          )}
          {onExitFloating && (
            <button
              className="floating-window-control exit-floating"
              onClick={(e) => {
                e.stopPropagation();
                console.log('[FloatingChatWindow] Exit floating button clicked');
                onExitFloating();
              }}
              title="Exit Floating Mode"
            >
              <Monitor size={14} />
            </button>
          )}
          <button
            className="floating-window-control minimize"
            onClick={(e) => {
              e.stopPropagation();
              onMinimize(windowData.id);
            }}
            title="Minimize"
          >
            <Minus size={14} />
          </button>
          <button
            className="floating-window-control close"
            onClick={(e) => {
              e.stopPropagation();
              onClose(windowData.id);
            }}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Window content */}
      <div className="floating-window-content">
        {children}
      </div>
    </div>
  );
};

// Minimized window button for taskbar
export const MinimizedWindowButton: React.FC<{
  windowData: FloatingWindowData;
  onRestore: (id: string) => void;
}> = ({ windowData, onRestore }) => {
  return (
    <button
      className="minimized-window-btn"
      onClick={() => onRestore(windowData.id)}
      title={windowData.title}
    >
      <MessageSquare size={14} />
      <span>{windowData.title.length > 20 ? windowData.title.slice(0, 20) + '...' : windowData.title}</span>
      <Maximize2 size={12} />
    </button>
  );
};

export default FloatingChatWindow;
