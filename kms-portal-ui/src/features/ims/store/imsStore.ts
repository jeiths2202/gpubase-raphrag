/**
 * IMS Knowledge Service Store
 *
 * Zustand state management for IMS feature
 */

import { create } from 'zustand';
import type {
  IMSJob,
  IMSSearchTab,
  ViewMode,
  CompletionStats,
  IMSIssue,
} from '../types';
import { getCredentials, searchIssues, getIssuesByIds } from '../services/ims-api';

interface IMSState {
  // Credentials
  hasCredentials: boolean;
  credentialsValidated: boolean;
  credentialsError?: string;

  // Search
  isSearching: boolean;
  searchQuery: string;
  currentJob?: IMSJob;

  // Tabs
  searchTabs: IMSSearchTab[];
  activeTabId: string | null;

  // Default view mode
  viewMode: ViewMode;
}

interface IMSActions {
  // Credentials
  checkCredentials: () => Promise<void>;
  setCredentialsStatus: (has: boolean, validated: boolean, error?: string) => void;

  // Search
  setIsSearching: (isSearching: boolean) => void;
  setSearchQuery: (query: string) => void;
  setCurrentJob: (job: IMSJob | undefined) => void;

  // Results & Tabs
  fetchResults: (query: string, completionStats?: CompletionStats) => Promise<void>;
  addSearchTab: (tab: IMSSearchTab) => void;
  setActiveTab: (id: string | null) => void;
  removeSearchTab: (id: string) => void;
  updateTabViewMode: (id: string, mode: ViewMode) => void;
  updateTabResults: (id: string, results: IMSIssue[]) => void;

  // Helpers
  getActiveTab: () => IMSSearchTab | undefined;
  resetSearch: () => void;
  setViewMode: (mode: ViewMode) => void;
}

const SEARCH_TAB_ID = 'search';

export const useIMSStore = create<IMSState & IMSActions>((set, get) => ({
  // Initial state
  hasCredentials: false,
  credentialsValidated: false,
  credentialsError: undefined,
  isSearching: false,
  searchQuery: '',
  currentJob: undefined,
  searchTabs: [],
  activeTabId: SEARCH_TAB_ID,
  viewMode: 'table',

  // Credentials actions
  checkCredentials: async () => {
    try {
      const response = await getCredentials();
      set({
        hasCredentials: true,
        credentialsValidated: response.is_validated,
        credentialsError: response.validation_error || undefined,
      });
    } catch (error) {
      // 404 means no credentials saved
      set({
        hasCredentials: false,
        credentialsValidated: false,
        credentialsError: undefined,
      });
    }
  },

  setCredentialsStatus: (has, validated, error) => {
    set({
      hasCredentials: has,
      credentialsValidated: validated,
      credentialsError: error,
    });
  },

  // Search actions
  setIsSearching: (isSearching) => set({ isSearching }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setCurrentJob: (job) => set({ currentJob: job }),

  // Results & Tabs actions
  fetchResults: async (query, completionStats) => {
    try {
      let results: IMSIssue[];

      // If we have resultIssueIds from the crawl job, fetch those specific issues
      // This ensures we display the ACTUAL crawled results, not database search results
      if (completionStats?.resultIssueIds && completionStats.resultIssueIds.length > 0) {
        console.log('[IMS] Fetching crawled issues by IDs:', completionStats.resultIssueIds.length);
        results = await getIssuesByIds(completionStats.resultIssueIds);
      } else {
        // Fallback to search API for backward compatibility
        console.log('[IMS] Fallback to search API (no resultIssueIds)');
        const response = await searchIssues({
          query,
          max_results: 100,
          search_strategy: 'hybrid',
        });
        results = response.results;
      }

      // Update completionStats with actual results count for consistency
      const updatedStats = completionStats ? {
        ...completionStats,
        totalIssues: results.length,
        successfulIssues: results.length,
      } : undefined;

      const newTab: IMSSearchTab = {
        id: `result-${Date.now()}`,
        query,
        timestamp: new Date().toISOString(),
        results,
        viewMode: get().viewMode,
        completionStats: updatedStats,
      };

      set((state) => ({
        searchTabs: [...state.searchTabs, newTab],
        activeTabId: newTab.id,
        isSearching: false,
        currentJob: undefined,
      }));
    } catch (error) {
      console.error('[IMS] Failed to fetch results:', error);
      set({ isSearching: false });
    }
  },

  addSearchTab: (tab) => {
    set((state) => ({
      searchTabs: [...state.searchTabs, tab],
    }));
  },

  setActiveTab: (id) => set({ activeTabId: id }),

  removeSearchTab: (id) => {
    set((state) => {
      const newTabs = state.searchTabs.filter((tab) => tab.id !== id);
      const newActiveId =
        state.activeTabId === id
          ? newTabs.length > 0
            ? newTabs[newTabs.length - 1].id
            : SEARCH_TAB_ID
          : state.activeTabId;

      return {
        searchTabs: newTabs,
        activeTabId: newActiveId,
      };
    });
  },

  updateTabViewMode: (id, mode) => {
    set((state) => ({
      searchTabs: state.searchTabs.map((tab) =>
        tab.id === id ? { ...tab, viewMode: mode } : tab
      ),
    }));
  },

  updateTabResults: (id, results) => {
    set((state) => ({
      searchTabs: state.searchTabs.map((tab) =>
        tab.id === id ? { ...tab, results } : tab
      ),
    }));
  },

  // Helpers
  getActiveTab: () => {
    const state = get();
    return state.searchTabs.find((tab) => tab.id === state.activeTabId);
  },

  resetSearch: () => {
    set({
      isSearching: false,
      searchQuery: '',
      currentJob: undefined,
    });
  },

  setViewMode: (mode) => set({ viewMode: mode }),
}));

// Selector hooks for convenience
export const useIMSCredentials = () =>
  useIMSStore((state) => ({
    hasCredentials: state.hasCredentials,
    credentialsValidated: state.credentialsValidated,
    credentialsError: state.credentialsError,
  }));

export const useIMSSearch = () =>
  useIMSStore((state) => ({
    isSearching: state.isSearching,
    searchQuery: state.searchQuery,
    currentJob: state.currentJob,
  }));

export const useIMSTabs = () =>
  useIMSStore((state) => ({
    searchTabs: state.searchTabs,
    activeTabId: state.activeTabId,
    viewMode: state.viewMode,
  }));
