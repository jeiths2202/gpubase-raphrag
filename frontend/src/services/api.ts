import axios from 'axios';
import type {
  ApiResponse,
  MindmapFull,
  MindmapInfo,
  GenerateMindmapRequest,
  GenerateMindmapResponse,
  ExpandNodeRequest,
  ExpandNodeResponse,
  QueryNodeRequest,
  QueryNodeResponse,
  NodeDetailResponse,
} from '../types/mindmap';

const API_BASE_URL = '/api/v1';

// Axios instance with default config
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Mindmap API functions
export const mindmapApi = {
  // Generate mindmap from documents
  generate: async (request: GenerateMindmapRequest): Promise<MindmapFull> => {
    const response = await api.post<ApiResponse<GenerateMindmapResponse>>(
      '/mindmap/generate',
      request
    );
    return response.data.data.mindmap;
  },

  // Generate mindmap from all documents
  generateFromAll: async (params?: {
    title?: string;
    max_nodes?: number;
    focus_topic?: string;
    language?: string;
  }): Promise<MindmapFull> => {
    const response = await api.post<ApiResponse<GenerateMindmapResponse>>(
      '/mindmap/from-all-documents',
      null,
      { params }
    );
    return response.data.data.mindmap;
  },

  // List all mindmaps
  list: async (page = 1, limit = 20): Promise<{ mindmaps: MindmapInfo[]; total: number }> => {
    const response = await api.get<ApiResponse<{ mindmaps: MindmapInfo[]; total: number }>>(
      '/mindmap',
      { params: { page, limit } }
    );
    return response.data.data;
  },

  // Get mindmap by ID
  get: async (mindmapId: string): Promise<MindmapFull> => {
    const response = await api.get<ApiResponse<MindmapFull>>(`/mindmap/${mindmapId}`);
    return response.data.data;
  },

  // Delete mindmap
  delete: async (mindmapId: string): Promise<boolean> => {
    const response = await api.delete<ApiResponse<{ deleted: boolean }>>(`/mindmap/${mindmapId}`);
    return response.data.data.deleted;
  },

  // Expand node
  expand: async (mindmapId: string, request: ExpandNodeRequest): Promise<ExpandNodeResponse> => {
    const response = await api.post<ApiResponse<ExpandNodeResponse>>(
      `/mindmap/${mindmapId}/expand`,
      request
    );
    return response.data.data;
  },

  // Query node
  query: async (mindmapId: string, request: QueryNodeRequest): Promise<QueryNodeResponse> => {
    const response = await api.post<ApiResponse<QueryNodeResponse>>(
      `/mindmap/${mindmapId}/query`,
      request
    );
    return response.data.data;
  },

  // Get node detail
  getNodeDetail: async (mindmapId: string, nodeId: string): Promise<NodeDetailResponse> => {
    const response = await api.get<ApiResponse<NodeDetailResponse>>(
      `/mindmap/${mindmapId}/node/${nodeId}`
    );
    return response.data.data;
  },
};

// Documents API (for getting available documents)
export const documentsApi = {
  list: async (): Promise<Array<{ id: string; name: string }>> => {
    try {
      const response = await api.get<ApiResponse<{ documents: Array<{ id: string; name: string }> }>>(
        '/documents'
      );
      return response.data.data.documents || [];
    } catch {
      return [];
    }
  },
};

export default api;
