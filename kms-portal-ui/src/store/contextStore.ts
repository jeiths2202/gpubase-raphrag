/**
 * Context Store
 *
 * Zustand store for managing UI context that is shared with the AI assistant.
 * Aggregates context from:
 * - Current page/route
 * - Selected item (FAQ, document, IMS issue, etc.)
 * - User preferences (language, theme)
 * - User permissions (admin/user)
 *
 * This store does NOT persist to localStorage - context is ephemeral and
 * resets on page refresh.
 */

import { create } from 'zustand';
import {
  UIContext,
  PageType,
  SelectedItem,
  PageMetadata,
  PAGE_TITLES,
  getPageTypeFromPath,
  truncateContent,
  MAX_CONTENT_LENGTH,
} from '../types/uiContext';
import { useAuthStore } from './authStore';
import { usePreferencesStore } from './preferencesStore';

// =============================================================================
// Types
// =============================================================================

interface ContextState {
  // Current UI state
  currentPage: PageType;
  pageTitle: string;
  pageMetadata: PageMetadata | null;
  selectedItem: SelectedItem | null;
  visibleComponents: Set<string>;

  // Actions
  setCurrentPage: (path: string, metadata?: PageMetadata) => void;
  setSelectedItem: (item: SelectedItem | null) => void;
  updateSelectedItemContent: (content: string) => void;
  setPageMetadata: (metadata: PageMetadata) => void;
  addVisibleComponent: (component: string) => void;
  removeVisibleComponent: (component: string) => void;
  setVisibleComponents: (components: string[]) => void;
  clearSelectedItem: () => void;
  clearContext: () => void;

  // Get aggregated context for AI requests
  getUIContext: () => UIContext;
}

// =============================================================================
// Store Creation
// =============================================================================

export const useContextStore = create<ContextState>((set, get) => ({
  // Initial state
  currentPage: 'unknown',
  pageTitle: 'Unknown',
  pageMetadata: null,
  selectedItem: null,
  visibleComponents: new Set<string>(),

  // =====================================================================
  // Set current page from pathname
  // =====================================================================
  setCurrentPage: (path: string, metadata?: PageMetadata) => {
    const pageType = getPageTypeFromPath(path);
    set({
      currentPage: pageType,
      pageTitle: PAGE_TITLES[pageType] || 'Unknown',
      pageMetadata: metadata || null,
      // Clear selected item when navigating to a new page
      selectedItem: null,
    });
  },

  // =====================================================================
  // Set selected item (FAQ, document, etc.)
  // =====================================================================
  setSelectedItem: (item: SelectedItem | null) => {
    if (item && item.content) {
      // Truncate content to prevent excessive payload size
      item = {
        ...item,
        content: truncateContent(item.content, MAX_CONTENT_LENGTH),
      };
    }
    set({ selectedItem: item });
  },

  // =====================================================================
  // Update content of selected item (for lazy loading)
  // =====================================================================
  updateSelectedItemContent: (content: string) => {
    const { selectedItem } = get();
    if (selectedItem) {
      set({
        selectedItem: {
          ...selectedItem,
          content: truncateContent(content, MAX_CONTENT_LENGTH),
        },
      });
    }
  },

  // =====================================================================
  // Set page-specific metadata
  // =====================================================================
  setPageMetadata: (metadata: PageMetadata) => {
    set((state) => ({
      pageMetadata: { ...state.pageMetadata, ...metadata },
    }));
  },

  // =====================================================================
  // Manage visible components
  // =====================================================================
  addVisibleComponent: (component: string) => {
    set((state) => {
      const updated = new Set(state.visibleComponents);
      updated.add(component);
      return { visibleComponents: updated };
    });
  },

  removeVisibleComponent: (component: string) => {
    set((state) => {
      const updated = new Set(state.visibleComponents);
      updated.delete(component);
      return { visibleComponents: updated };
    });
  },

  setVisibleComponents: (components: string[]) => {
    set({ visibleComponents: new Set(components) });
  },

  // =====================================================================
  // Clear selected item
  // =====================================================================
  clearSelectedItem: () => {
    set({ selectedItem: null });
  },

  // =====================================================================
  // Clear all context (on logout or navigation)
  // =====================================================================
  clearContext: () => {
    set({
      currentPage: 'unknown',
      pageTitle: 'Unknown',
      pageMetadata: null,
      selectedItem: null,
      visibleComponents: new Set<string>(),
    });
  },

  // =====================================================================
  // Get aggregated UI context for AI requests
  // =====================================================================
  getUIContext: (): UIContext => {
    const state = get();

    // Get user info from auth store
    const authState = useAuthStore.getState();
    const user = authState.user;
    const userRole = user?.role === 'admin' ? 'admin' : 'user';

    // Get preferences from preferences store
    const prefsState = usePreferencesStore.getState();
    const language = prefsState.language || 'ko';
    const theme = prefsState.resolvedTheme || 'dark';

    return {
      current_page: state.currentPage,
      page_title: state.pageTitle,
      page_metadata: state.pageMetadata || undefined,
      selected_item: state.selectedItem || undefined,
      visible_components: Array.from(state.visibleComponents),
      language,
      theme,
      user_permission_scope: userRole,
      captured_at: new Date().toISOString(),
    };
  },
}));

// =============================================================================
// Selector Hooks
// =============================================================================

/** Get current page */
export const useCurrentPage = () => useContextStore((state) => state.currentPage);

/** Get selected item */
export const useSelectedItem = () => useContextStore((state) => state.selectedItem);

/** Get page metadata */
export const usePageMetadata = () => useContextStore((state) => state.pageMetadata);

/** Check if an item is selected */
export const useHasSelectedItem = () =>
  useContextStore((state) => state.selectedItem !== null);

/** Get UI context for AI */
export const useUIContext = () => useContextStore((state) => state.getUIContext());
