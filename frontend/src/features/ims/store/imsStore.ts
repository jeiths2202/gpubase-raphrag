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
}

export const useIMSStore = create<IMSState>((set) => ({
  // Initial state
  hasCredentials: false,
  credentialsValidated: false,
  isSearching: false,
  searchQuery: '',
  searchResults: [],
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
  })
}));
