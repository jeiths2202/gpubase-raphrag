/**
 * useFloatingPanel - Drag/resize hook for floating AI panel.
 * Persists position and size in localStorage.
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface Position {
  x: number;
  y: number;
}

interface Size {
  width: number;
  height: number;
}

const POS_KEY = 'mod-ai-position';
const SIZE_KEY = 'mod-ai-size';

const DEFAULT_SIZE: Size = { width: 420, height: 580 };
const MIN_SIZE: Size = { width: 340, height: 400 };

function getDefaultPosition(): Position {
  return {
    x: window.innerWidth - DEFAULT_SIZE.width - 24,
    y: window.innerHeight - DEFAULT_SIZE.height - 80,
  };
}

function loadFromStorage<T>(key: string, fallback: () => T): T {
  try {
    const stored = localStorage.getItem(key);
    if (stored) return JSON.parse(stored);
  } catch { /* ignore */ }
  return fallback();
}

function clampPosition(pos: Position, size: Size): Position {
  return {
    x: Math.max(0, Math.min(pos.x, window.innerWidth - size.width)),
    y: Math.max(0, Math.min(pos.y, window.innerHeight - size.height)),
  };
}

export function useFloatingPanel() {
  const [position, setPosition] = useState<Position>(() =>
    loadFromStorage(POS_KEY, getDefaultPosition)
  );
  const [size, setSize] = useState<Size>(() =>
    loadFromStorage(SIZE_KEY, () => DEFAULT_SIZE)
  );

  const isDragging = useRef(false);
  const isResizing = useRef(false);
  const dragOffset = useRef<Position>({ x: 0, y: 0 });

  // Save to localStorage on change
  useEffect(() => {
    localStorage.setItem(POS_KEY, JSON.stringify(position));
  }, [position]);

  useEffect(() => {
    localStorage.setItem(SIZE_KEY, JSON.stringify(size));
  }, [size]);

  // Drag handlers
  const onDragStart = useCallback(
    (e: React.MouseEvent) => {
      // Only respond to left click on the header drag handle
      if (e.button !== 0) return;
      e.preventDefault();
      isDragging.current = true;
      dragOffset.current = {
        x: e.clientX - position.x,
        y: e.clientY - position.y,
      };

      const onMove = (ev: MouseEvent) => {
        if (!isDragging.current) return;
        const newPos = clampPosition(
          { x: ev.clientX - dragOffset.current.x, y: ev.clientY - dragOffset.current.y },
          size
        );
        setPosition(newPos);
      };

      const onUp = () => {
        isDragging.current = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [position, size]
  );

  // Resize handlers (bottom-right corner)
  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      isResizing.current = true;

      const startX = e.clientX;
      const startY = e.clientY;
      const startSize = { ...size };

      const onMove = (ev: MouseEvent) => {
        if (!isResizing.current) return;
        const newWidth = Math.max(MIN_SIZE.width, startSize.width + (ev.clientX - startX));
        const newHeight = Math.max(MIN_SIZE.height, startSize.height + (ev.clientY - startY));
        setSize({ width: newWidth, height: newHeight });
      };

      const onUp = () => {
        isResizing.current = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },
    [size]
  );

  return {
    position,
    size,
    onDragStart,
    onResizeStart,
  };
}
