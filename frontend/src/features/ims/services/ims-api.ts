/**
 * IMS API Service - API client for IMS Crawler backend
 */

import axios from 'axios';

const API_BASE = '/api/v1';

const imsAPI = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true
});

export interface CredentialsRequest {
  ims_url: string;
  username: string;
  password: string;
}

export interface SearchRequest {
  query: string;
  max_results?: number;
  include_attachments?: boolean;
  include_related?: boolean;
  use_semantic_search?: boolean;
}

export interface CrawlJobRequest {
  query: string;
  include_attachments?: boolean;
  include_related_issues?: boolean;
  max_issues?: number;
}

export const imsApiService = {
  // Credentials Management
  createCredentials: async (data: CredentialsRequest) => {
    const response = await imsAPI.post('/ims-credentials/', data);
    return response.data;
  },

  getCredentials: async () => {
    const response = await imsAPI.get('/ims-credentials/');
    return response.data;
  },

  validateCredentials: async () => {
    const response = await imsAPI.post('/ims-credentials/validate');
    return response.data;
  },

  deleteCredentials: async () => {
    await imsAPI.delete('/ims-credentials/');
  },

  // Search
  searchIssues: async (request: SearchRequest) => {
    const response = await imsAPI.post('/ims-search/', request);
    return response.data;
  },

  getRecentIssues: async (limit: number = 20) => {
    const response = await imsAPI.get('/ims-search/recent', { params: { limit } });
    return response.data;
  },

  getIssueDetails: async (issueId: string) => {
    const response = await imsAPI.get(`/ims-search/${issueId}`);
    return response.data;
  },

  // Crawl Jobs
  createCrawlJob: async (request: CrawlJobRequest) => {
    const response = await imsAPI.post('/ims-jobs/', request);
    return response.data;
  },

  getJobStatus: async (jobId: string) => {
    const response = await imsAPI.get(`/ims-jobs/${jobId}`);
    return response.data;
  },

  listJobs: async (limit: number = 20) => {
    const response = await imsAPI.get('/ims-jobs/', { params: { limit } });
    return response.data;
  },

  cancelJob: async (jobId: string) => {
    await imsAPI.delete(`/ims-jobs/${jobId}`);
  }
};

export default imsApiService;
