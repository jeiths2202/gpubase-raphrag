/**
 * IMS Store - Zustand state management for IMS Crawler
 *
 * Manages:
 * - User credentials status
 * - Search state and results
 * - Active crawl jobs
 * - View mode preferences
 */

import { create } from 'zustand';
import type { CompletionStats } from '../types/progress';

export type ViewMode = 'table' | 'cards' | 'graph';

export interface IMSIssue {
  id: string;
  ims_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  reporter: string;
  assignee?: string;
  project_key: string;
  labels: string[];
  created_at: string;
  updated_at: string;
  similarity_score?: number;
}

export interface IMSJob {
  id: string;
  status: string;
  current_step: string;
  progress_percentage: number;
  issues_found: number;
  issues_crawled: number;
  attachments_processed: number;
  error_message?: string;
}

export interface IMSSearchTab {
  id: string;
  query: string;
  timestamp: string;
  results: IMSIssue[];
  viewMode: ViewMode;
  completionStats?: CompletionStats;
}

interface IMSState {
  // Credentials
  hasCredentials: boolean;
  credentialsValidated: boolean;
  credentialsError?: string;

  // Search
  isSearching: boolean;
  searchQuery: string;
  searchResults: IMSIssue[];
  currentJob?: IMSJob;

  // Tabs
  searchTabs: IMSSearchTab[];
  activeTabId: string | null;

  // UI State
  viewMode: ViewMode;

  // Actions
  setHasCredentials: (has: boolean) => void;
  setCredentialsValidated: (validated: boolean) => void;
  setCredentialsError: (error?: string) => void;
  setIsSearching: (searching: boolean) => void;
  setSearchQuery: (query: string) => void;
  setSearchResults: (results: IMSIssue[]) => void;
  setCurrentJob: (job?: IMSJob) => void;
  setJobProgress: (progress: Partial<IMSJob>) => void;
  setViewMode: (mode: ViewMode) => void;
  checkCredentials: () => Promise<void>;
  clearSearch: () => void;

  // Tab Actions
  fetchResults: (query: string, completionStats?: CompletionStats) => Promise<void>;
  setActiveTab: (id: string) => void;
  removeSearchTab: (id: string) => void;
  updateTabViewMode: (id: string, mode: ViewMode) => void;
  getActiveTab: () => IMSSearchTab | null;
}

export const useIMSStore = create<IMSState>((set, get) => ({
  // Initial state
  hasCredentials: false,
  credentialsValidated: false,
  isSearching: false,
  searchQuery: '',
  searchResults: [],
  searchTabs: [],
  activeTabId: null,
  viewMode: 'table',

  // Actions
  setHasCredentials: (has) => set({ hasCredentials: has }),
  setCredentialsValidated: (validated) => set({ credentialsValidated: validated }),
  setCredentialsError: (error) => set({ credentialsError: error }),
  setIsSearching: (searching) => set({ isSearching: searching }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSearchResults: (results) => set({ searchResults: results }),
  setCurrentJob: (job) => set({ currentJob: job }),
  setJobProgress: (progress) => set((state) => ({
    currentJob: state.currentJob ? { ...state.currentJob, ...progress } : undefined
  })),
  setViewMode: (mode) => set({ viewMode: mode }),

  checkCredentials: async () => {
    try {
      const response = await fetch('/api/v1/ims-credentials', {
        headers: { 'Accept': 'application/json' },
        credentials: 'include'
      });

      if (response.ok) {
        const data = await response.json();
        set({
          hasCredentials: true,
          credentialsValidated: data.is_validated,
          credentialsError: data.validation_error
        });
      } else if (response.status === 404) {
        set({ hasCredentials: false, credentialsValidated: false });
      }
    } catch (error) {
      console.error('Failed to check credentials:', error);
      set({ hasCredentials: false, credentialsValidated: false });
    }
  },

  clearSearch: () => set({
    searchQuery: '',
    searchResults: [],
    currentJob: undefined,
    isSearching: false
  }),

  // Tab Actions
  fetchResults: async (query, completionStats) => {
    set({ isSearching: true, searchQuery: query });
    try {
      // In a real scenario, we might fetch from API
      // For now, let's assume we search and get results
      const response = await fetch('/api/v1/ims-search/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, max_results: 50 })
      });

      if (response.ok) {
        const data = await response.json();
        const results = data.results || [];

        const newTab: IMSSearchTab = {
          id: Math.random().toString(36).substr(2, 9),
          query,
          timestamp: new Date().toISOString(),
          results,
          viewMode: get().viewMode,
          completionStats
        };

        set((state) => ({
          searchTabs: [newTab, ...state.searchTabs],
          activeTabId: newTab.id,
          isSearching: false,
          searchResults: results
        }));
      }
    } catch (error) {
      console.error('Failed to fetch results:', error);
      set({ isSearching: false });
    }
  },

  setActiveTab: (id) => set({ activeTabId: id }),

  removeSearchTab: (id) => set((state) => {
    const newTabs = state.searchTabs.filter(t => t.id !== id);
    let newActiveId = state.activeTabId;
    if (newActiveId === id) {
      newActiveId = newTabs.length > 0 ? newTabs[0].id : null;
    }
    return { searchTabs: newTabs, activeTabId: newActiveId };
  }),

  updateTabViewMode: (id, mode) => set((state) => ({
    searchTabs: state.searchTabs.map(t => t.id === id ? { ...t, viewMode: mode } : t)
  })),

  getActiveTab: () => {
    const { searchTabs, activeTabId } = get();
    return searchTabs.find(t => t.id === activeTabId) || null;
  }
}));
