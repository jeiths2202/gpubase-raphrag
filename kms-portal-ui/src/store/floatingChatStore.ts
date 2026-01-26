/**
 * Floating Chat Windows Store
 *
 * Manages multiple floating chat windows.
 * Features:
 * - Create/close windows
 * - Minimize/restore windows
 * - Update position and size
 * - Z-index management for stacking
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AgentType } from '../api/agent.api';

export interface FloatingWindowData {
  id: string;
  title: string;
  agentType: AgentType;
  conversationId: string | null;
  isMinimized: boolean;
  position: { x: number; y: number };
  size: { width: number; height: number };
  zIndex: number;
}

interface FloatingChatState {
  // State
  windows: FloatingWindowData[];
  nextZIndex: number;
  activeWindowId: string | null;

  // Actions
  createWindow: (agentType: AgentType, title?: string) => string;
  closeWindow: (id: string) => void;
  closeAllWindows: () => void;
  minimizeWindow: (id: string) => void;
  restoreWindow: (id: string) => void;
  bringToFront: (id: string) => void;
  updatePosition: (id: string, position: { x: number; y: number }) => void;
  updateSize: (id: string, size: { width: number; height: number }) => void;
  updateTitle: (id: string, title: string) => void;
  updateConversationId: (id: string, conversationId: string | null) => void;
  setActiveWindow: (id: string | null) => void;
  getActiveWindow: () => FloatingWindowData | null;
}

// Calculate initial position for new window (cascade effect)
const calculateInitialPosition = (existingCount: number): { x: number; y: number } => {
  const baseX = 100;
  const baseY = 80;
  const offset = 30;

  return {
    x: baseX + (existingCount % 8) * offset,
    y: baseY + (existingCount % 8) * offset,
  };
};

// Default window size
const DEFAULT_SIZE = { width: 800, height: 600 };

export const useFloatingChatStore = create<FloatingChatState>()(
  persist(
    (set, get) => ({
      // Initial state
      windows: [],
      nextZIndex: 1000,
      activeWindowId: null,

      createWindow: (agentType, title) => {
        const id = `chat-window-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { windows, nextZIndex } = get();

        const newWindow: FloatingWindowData = {
          id,
          title: title || 'AI Chat',
          agentType,
          conversationId: null,
          isMinimized: false,
          position: calculateInitialPosition(windows.length),
          size: DEFAULT_SIZE,
          zIndex: nextZIndex,
        };

        set({
          windows: [...windows, newWindow],
          nextZIndex: nextZIndex + 1,
          activeWindowId: id,
        });

        return id;
      },

      closeWindow: (id) => {
        const { windows, activeWindowId } = get();
        const newWindows = windows.filter((w) => w.id !== id);

        set({
          windows: newWindows,
          activeWindowId: activeWindowId === id
            ? (newWindows.length > 0 ? newWindows[newWindows.length - 1].id : null)
            : activeWindowId,
        });
      },

      closeAllWindows: () => {
        set({ windows: [], activeWindowId: null });
      },

      minimizeWindow: (id) => {
        const { windows, activeWindowId } = get();
        const otherWindows = windows.filter(w => w.id !== id && !w.isMinimized);

        set({
          windows: windows.map((w) =>
            w.id === id ? { ...w, isMinimized: true } : w
          ),
          activeWindowId: activeWindowId === id
            ? (otherWindows.length > 0 ? otherWindows[otherWindows.length - 1].id : null)
            : activeWindowId,
        });
      },

      restoreWindow: (id) => {
        const { nextZIndex } = get();
        set((state) => ({
          windows: state.windows.map((w) =>
            w.id === id ? { ...w, isMinimized: false, zIndex: nextZIndex } : w
          ),
          nextZIndex: nextZIndex + 1,
          activeWindowId: id,
        }));
      },

      bringToFront: (id) => {
        const { nextZIndex, windows } = get();
        const window = windows.find((w) => w.id === id);

        if (window && window.zIndex < nextZIndex - 1) {
          set({
            windows: windows.map((w) =>
              w.id === id ? { ...w, zIndex: nextZIndex } : w
            ),
            nextZIndex: nextZIndex + 1,
            activeWindowId: id,
          });
        } else {
          set({ activeWindowId: id });
        }
      },

      updatePosition: (id, position) => {
        set((state) => ({
          windows: state.windows.map((w) =>
            w.id === id ? { ...w, position } : w
          ),
        }));
      },

      updateSize: (id, size) => {
        set((state) => ({
          windows: state.windows.map((w) =>
            w.id === id ? { ...w, size } : w
          ),
        }));
      },

      updateTitle: (id, title) => {
        set((state) => ({
          windows: state.windows.map((w) =>
            w.id === id ? { ...w, title } : w
          ),
        }));
      },

      updateConversationId: (id, conversationId) => {
        set((state) => ({
          windows: state.windows.map((w) =>
            w.id === id ? { ...w, conversationId } : w
          ),
        }));
      },

      setActiveWindow: (id) => {
        set({ activeWindowId: id });
      },

      getActiveWindow: () => {
        const { windows, activeWindowId } = get();
        return windows.find((w) => w.id === activeWindowId) || null;
      },
    }),
    {
      name: 'kms-floating-chat',
      partialize: (state) => ({
        // Only persist window layout, not content
        windows: state.windows.map(w => ({
          ...w,
          // Reset conversation on reload
          conversationId: null,
        })),
      }),
    }
  )
);
