/**
 * usePageContext Hook
 *
 * Custom hook for pages to register their context with the context store.
 * Provides a declarative API for context capture.
 *
 * Usage:
 * ```tsx
 * const { setSelectedItem } = usePageContext({
 *   visibleComponents: ['search', 'filters', 'list']
 * });
 *
 * // When user selects an item
 * setSelectedItem({
 *   type: 'faq_item',
 *   id: faq.id,
 *   title: faq.question,
 *   content: faq.answer
 * });
 * ```
 */

import { useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { useContextStore } from '../store/contextStore';
import type { SelectedItem, PageMetadata } from '../types/uiContext';

// =============================================================================
// Types
// =============================================================================

export interface UsePageContextOptions {
  /** Components visible on this page */
  visibleComponents?: string[];
  /** Additional page metadata */
  metadata?: PageMetadata;
  /** Whether to clear selected item on unmount */
  clearOnUnmount?: boolean;
}

export interface UsePageContextReturn {
  /** Set the currently selected item */
  setSelectedItem: (item: SelectedItem | null) => void;
  /** Update content of selected item */
  updateContent: (content: string) => void;
  /** Clear the selected item */
  clearSelectedItem: () => void;
  /** Update page metadata */
  setPageMetadata: (metadata: PageMetadata) => void;
  /** Add a visible component */
  addComponent: (component: string) => void;
  /** Remove a visible component */
  removeComponent: (component: string) => void;
  /** Current page type */
  currentPage: string;
  /** Currently selected item */
  selectedItem: SelectedItem | null;
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function usePageContext(options: UsePageContextOptions = {}): UsePageContextReturn {
  const { visibleComponents = [], metadata, clearOnUnmount = true } = options;

  const location = useLocation();

  const {
    currentPage,
    selectedItem,
    setCurrentPage,
    setSelectedItem: storeSetSelectedItem,
    updateSelectedItemContent,
    clearSelectedItem: storeClearSelectedItem,
    setPageMetadata: storeSetPageMetadata,
    addVisibleComponent,
    removeVisibleComponent,
    setVisibleComponents,
  } = useContextStore();

  // Register page on mount and pathname change
  useEffect(() => {
    setCurrentPage(location.pathname, metadata);

    // Set visible components
    if (visibleComponents.length > 0) {
      setVisibleComponents(visibleComponents);
    }

    // Cleanup on unmount
    return () => {
      if (clearOnUnmount) {
        storeClearSelectedItem();
      }
    };
  }, [location.pathname]);

  // Update metadata when it changes
  useEffect(() => {
    if (metadata) {
      storeSetPageMetadata(metadata);
    }
  }, [metadata]);

  // Memoized callbacks
  const setSelectedItem = useCallback(
    (item: SelectedItem | null) => {
      storeSetSelectedItem(item);
    },
    [storeSetSelectedItem]
  );

  const updateContent = useCallback(
    (content: string) => {
      updateSelectedItemContent(content);
    },
    [updateSelectedItemContent]
  );

  const clearSelectedItem = useCallback(() => {
    storeClearSelectedItem();
  }, [storeClearSelectedItem]);

  const setPageMetadata = useCallback(
    (meta: PageMetadata) => {
      storeSetPageMetadata(meta);
    },
    [storeSetPageMetadata]
  );

  const addComponent = useCallback(
    (component: string) => {
      addVisibleComponent(component);
    },
    [addVisibleComponent]
  );

  const removeComponent = useCallback(
    (component: string) => {
      removeVisibleComponent(component);
    },
    [removeVisibleComponent]
  );

  return {
    setSelectedItem,
    updateContent,
    clearSelectedItem,
    setPageMetadata,
    addComponent,
    removeComponent,
    currentPage,
    selectedItem,
  };
}

// =============================================================================
// Convenience Hook for Simple Pages
// =============================================================================

/**
 * Simple hook for pages that only need to register their location
 * without managing selected items.
 */
export function useSimplePageContext(visibleComponents?: string[]): void {
  const location = useLocation();
  const { setCurrentPage, setVisibleComponents } = useContextStore();

  useEffect(() => {
    setCurrentPage(location.pathname);
    if (visibleComponents) {
      setVisibleComponents(visibleComponents);
    }
  }, [location.pathname]);
}

export default usePageContext;
