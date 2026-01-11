/**
 * API Key Store
 *
 * Zustand store for API key management state.
 */

import { create } from 'zustand';
import {
  apiKeyApi,
  type ApiKeyResponse,
  type ApiKeyCreateRequest,
  type ApiKeyUpdateRequest,
  type ApiKeyCreatedResponse,
} from '../api/apiKey.api';
import { isApiError, getErrorMessage } from '../api/client';

// =============================================================================
// Types
// =============================================================================

interface ApiKeyState {
  // State
  apiKeys: ApiKeyResponse[];
  selectedKey: ApiKeyResponse | null;
  newlyCreatedKey: ApiKeyCreatedResponse | null;
  isLoading: boolean;
  error: string | null;
  total: number;
  page: number;
  pageSize: number;

  // Actions
  fetchApiKeys: (page?: number, includeInactive?: boolean) => Promise<void>;
  createApiKey: (data: ApiKeyCreateRequest) => Promise<ApiKeyCreatedResponse | null>;
  updateApiKey: (id: string, data: ApiKeyUpdateRequest) => Promise<boolean>;
  deleteApiKey: (id: string) => Promise<boolean>;
  selectKey: (key: ApiKeyResponse | null) => void;
  clearNewlyCreatedKey: () => void;
  clearError: () => void;
}

// =============================================================================
// Store
// =============================================================================

export const useApiKeyStore = create<ApiKeyState>((set, get) => ({
  // Initial state
  apiKeys: [],
  selectedKey: null,
  newlyCreatedKey: null,
  isLoading: false,
  error: null,
  total: 0,
  page: 1,
  pageSize: 20,

  // Fetch API keys
  fetchApiKeys: async (page = 1, includeInactive = false) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiKeyApi.list(page, get().pageSize, includeInactive);
      set({
        apiKeys: response.items,
        total: response.total,
        page: response.page,
        isLoading: false,
      });
    } catch (error) {
      set({
        isLoading: false,
        error: getErrorMessage(error),
      });
    }
  },

  // Create new API key
  createApiKey: async (data: ApiKeyCreateRequest) => {
    set({ isLoading: true, error: null });

    try {
      const response = await apiKeyApi.create(data);
      set({
        newlyCreatedKey: response,
        isLoading: false,
      });

      // Refresh list
      await get().fetchApiKeys(get().page);

      return response;
    } catch (error) {
      set({
        isLoading: false,
        error: getErrorMessage(error),
      });
      return null;
    }
  },

  // Update API key
  updateApiKey: async (id: string, data: ApiKeyUpdateRequest) => {
    set({ isLoading: true, error: null });

    try {
      const updated = await apiKeyApi.update(id, data);

      // Update in list
      set((state) => ({
        apiKeys: state.apiKeys.map((key) => (key.id === id ? updated : key)),
        selectedKey: state.selectedKey?.id === id ? updated : state.selectedKey,
        isLoading: false,
      }));

      return true;
    } catch (error) {
      set({
        isLoading: false,
        error: getErrorMessage(error),
      });
      return false;
    }
  },

  // Delete API key
  deleteApiKey: async (id: string) => {
    set({ isLoading: true, error: null });

    try {
      await apiKeyApi.delete(id);

      // Remove from list
      set((state) => ({
        apiKeys: state.apiKeys.filter((key) => key.id !== id),
        selectedKey: state.selectedKey?.id === id ? null : state.selectedKey,
        total: state.total - 1,
        isLoading: false,
      }));

      return true;
    } catch (error) {
      set({
        isLoading: false,
        error: getErrorMessage(error),
      });
      return false;
    }
  },

  // Select key for viewing/editing
  selectKey: (key: ApiKeyResponse | null) => {
    set({ selectedKey: key });
  },

  // Clear newly created key (after user has copied it)
  clearNewlyCreatedKey: () => {
    set({ newlyCreatedKey: null });
  },

  // Clear error
  clearError: () => {
    set({ error: null });
  },
}));

export default useApiKeyStore;
