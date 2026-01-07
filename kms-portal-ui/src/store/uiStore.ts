/**
 * UI Store
 *
 * Zustand store for UI state management
 * Handles sidebar states, theme, and layout preferences
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// Theme type
export type Theme = 'light' | 'dark' | 'system';

// UI state interface
interface UIState {
  // Sidebar states
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  leftSidebarWidth: number;
  rightSidebarWidth: number;

  // Theme
  theme: Theme;
  resolvedTheme: 'light' | 'dark';

  // Mobile
  isMobile: boolean;
  mobileMenuOpen: boolean;

  // Actions
  toggleLeftSidebar: () => void;
  toggleRightSidebar: () => void;
  setLeftSidebarOpen: (open: boolean) => void;
  setRightSidebarOpen: (open: boolean) => void;
  setLeftSidebarWidth: (width: number) => void;
  setRightSidebarWidth: (width: number) => void;
  setTheme: (theme: Theme) => void;
  setIsMobile: (isMobile: boolean) => void;
  toggleMobileMenu: () => void;
  closeMobileMenu: () => void;
}

// Get system theme preference
function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Resolve theme (handles 'system' option)
function resolveTheme(theme: Theme): 'light' | 'dark' {
  if (theme === 'system') {
    return getSystemTheme();
  }
  return theme;
}

// Apply theme to document
function applyTheme(theme: 'light' | 'dark') {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  root.setAttribute('data-theme', theme);

  // Also set class for Tailwind-style dark mode if needed
  if (theme === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
}

// Create UI store with persistence
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      leftSidebarOpen: true,
      rightSidebarOpen: true, // AI Sidebar default expanded (per user preference)
      leftSidebarWidth: 260,
      rightSidebarWidth: 380,
      theme: 'system',
      resolvedTheme: getSystemTheme(),
      isMobile: false,
      mobileMenuOpen: false,

      // Toggle left sidebar
      toggleLeftSidebar: () => {
        set((state) => ({ leftSidebarOpen: !state.leftSidebarOpen }));
      },

      // Toggle right sidebar (AI Sidebar)
      toggleRightSidebar: () => {
        set((state) => ({ rightSidebarOpen: !state.rightSidebarOpen }));
      },

      // Set left sidebar open state
      setLeftSidebarOpen: (open: boolean) => {
        set({ leftSidebarOpen: open });
      },

      // Set right sidebar open state
      setRightSidebarOpen: (open: boolean) => {
        set({ rightSidebarOpen: open });
      },

      // Set left sidebar width
      setLeftSidebarWidth: (width: number) => {
        set({ leftSidebarWidth: Math.max(200, Math.min(400, width)) });
      },

      // Set right sidebar width
      setRightSidebarWidth: (width: number) => {
        set({ rightSidebarWidth: Math.max(300, Math.min(500, width)) });
      },

      // Set theme
      setTheme: (theme: Theme) => {
        const resolved = resolveTheme(theme);
        applyTheme(resolved);
        set({ theme, resolvedTheme: resolved });
      },

      // Set mobile state
      setIsMobile: (isMobile: boolean) => {
        set({ isMobile });
        // Close sidebars on mobile
        if (isMobile) {
          set({ leftSidebarOpen: false, rightSidebarOpen: false });
        }
      },

      // Toggle mobile menu
      toggleMobileMenu: () => {
        set((state) => ({ mobileMenuOpen: !state.mobileMenuOpen }));
      },

      // Close mobile menu
      closeMobileMenu: () => {
        set({ mobileMenuOpen: false });
      },
    }),
    {
      name: 'kms-portal-ui',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        leftSidebarOpen: state.leftSidebarOpen,
        rightSidebarOpen: state.rightSidebarOpen,
        leftSidebarWidth: state.leftSidebarWidth,
        rightSidebarWidth: state.rightSidebarWidth,
        theme: state.theme,
      }),
      onRehydrateStorage: () => (state) => {
        // Apply theme after rehydration
        if (state) {
          const resolved = resolveTheme(state.theme);
          applyTheme(resolved);
          state.resolvedTheme = resolved;
        }
      },
    }
  )
);

// Listen for system theme changes
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const state = useUIStore.getState();
    if (state.theme === 'system') {
      const resolved = e.matches ? 'dark' : 'light';
      applyTheme(resolved);
      useUIStore.setState({ resolvedTheme: resolved });
    }
  });
}

// Selector hooks
export const useLeftSidebarOpen = () => useUIStore((state) => state.leftSidebarOpen);
export const useRightSidebarOpen = () => useUIStore((state) => state.rightSidebarOpen);
export const useTheme = () => useUIStore((state) => state.theme);
export const useResolvedTheme = () => useUIStore((state) => state.resolvedTheme);
export const useIsMobile = () => useUIStore((state) => state.isMobile);
