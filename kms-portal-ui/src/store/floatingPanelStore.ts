/**
 * Floating Panel Store
 *
 * Manages multiple floating panels for Direct mode results.
 * Features:
 * - Create/close panels
 * - Minimize/restore panels
 * - Update position and size
 * - Z-index management for stacking
 */

import { create } from 'zustand';
import type { ExpandableSearchResult, SourceReliability } from '../components/AgentChat/types';

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

interface FloatingPanelState {
  // State
  panels: FloatingPanelData[];
  nextZIndex: number;

  // Actions
  createPanel: (data: Omit<FloatingPanelData, 'id' | 'isMinimized' | 'position' | 'size' | 'zIndex'>) => string;
  closePanel: (id: string) => void;
  closeAllPanels: () => void;
  minimizePanel: (id: string) => void;
  restorePanel: (id: string) => void;
  bringToFront: (id: string) => void;
  updatePosition: (id: string, position: { x: number; y: number }) => void;
  updateSize: (id: string, size: { width: number; height: number }) => void;
  updatePanelContent: (id: string, content: string) => void;
  updatePanelSearchResults: (id: string, searchResults: ExpandableSearchResult[], sourceReliability?: SourceReliability) => void;
}

// Calculate initial position for new panel (cascade effect)
const calculateInitialPosition = (existingCount: number): { x: number; y: number } => {
  const baseX = 100;
  const baseY = 100;
  const offset = 30;

  return {
    x: baseX + (existingCount % 5) * offset,
    y: baseY + (existingCount % 5) * offset,
  };
};

// Default panel size
const DEFAULT_SIZE = { width: 500, height: 400 };

export const useFloatingPanelStore = create<FloatingPanelState>()((set, get) => ({
  // Initial state
  panels: [],
  nextZIndex: 1000,

  createPanel: (data) => {
    const id = `panel-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const { panels, nextZIndex } = get();

    const newPanel: FloatingPanelData = {
      ...data,
      id,
      isMinimized: false,
      position: calculateInitialPosition(panels.length),
      size: DEFAULT_SIZE,
      zIndex: nextZIndex,
    };

    set({
      panels: [...panels, newPanel],
      nextZIndex: nextZIndex + 1,
    });

    return id;
  },

  closePanel: (id) => {
    set((state) => ({
      panels: state.panels.filter((p) => p.id !== id),
    }));
  },

  closeAllPanels: () => {
    set({ panels: [] });
  },

  minimizePanel: (id) => {
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, isMinimized: true } : p
      ),
    }));
  },

  restorePanel: (id) => {
    const { nextZIndex } = get();
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, isMinimized: false, zIndex: nextZIndex } : p
      ),
      nextZIndex: nextZIndex + 1,
    }));
  },

  bringToFront: (id) => {
    const { nextZIndex, panels } = get();
    const panel = panels.find((p) => p.id === id);

    // Only update if not already at front
    if (panel && panel.zIndex < nextZIndex - 1) {
      set({
        panels: panels.map((p) =>
          p.id === id ? { ...p, zIndex: nextZIndex } : p
        ),
        nextZIndex: nextZIndex + 1,
      });
    }
  },

  updatePosition: (id, position) => {
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, position } : p
      ),
    }));
  },

  updateSize: (id, size) => {
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, size } : p
      ),
    }));
  },

  updatePanelContent: (id, content) => {
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, content } : p
      ),
    }));
  },

  updatePanelSearchResults: (id, searchResults, sourceReliability) => {
    set((state) => ({
      panels: state.panels.map((p) =>
        p.id === id ? { ...p, searchResults, sourceReliability } : p
      ),
    }));
  },
}));
