// Application constants

export const APP_CONFIG = {
  name: 'KMS',
  fullName: 'Knowledge Management System',
  version: '1.0.0',
};

// Google OAuth Client ID - Replace with your actual client ID
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

// API Base URL
export const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

// Application Environment
export const APP_ENV = (import.meta.env.VITE_APP_ENV || 'development') as 'development' | 'staging' | 'production';

// Service Endpoints (for status display and admin links)
export const SERVICE_ENDPOINTS = {
  neo4j: import.meta.env.VITE_NEO4J_BROWSER_URL || 'http://localhost:7474',
  nemotronLlm: import.meta.env.VITE_NEMOTRON_LLM_URL || 'http://localhost:12800',
  nemoEmbedding: import.meta.env.VITE_NEMO_EMBEDDING_URL || 'http://localhost:12801',
  mistralCoder: import.meta.env.VITE_MISTRAL_CODER_URL || 'http://localhost:12802',
};

// Feature Flags
export const FEATURES = {
  mindmap: import.meta.env.VITE_ENABLE_MINDMAP !== 'false',
  knowledgeGraph: import.meta.env.VITE_ENABLE_KNOWLEDGE_GRAPH !== 'false',
  vision: import.meta.env.VITE_ENABLE_VISION !== 'false',
};

// UI Defaults
export const UI_DEFAULTS = {
  theme: (import.meta.env.VITE_DEFAULT_THEME || 'dark') as 'dark' | 'light',
  language: (import.meta.env.VITE_DEFAULT_LANGUAGE || 'en') as 'en' | 'ko' | 'ja',
};

// Corporate email domains for SSO
export const CORP_EMAIL_DOMAINS = [
  'company.com',
  'company.co.kr',
  // Add your corporate domains here
];

// Check if email is corporate
export const isCorpEmail = (email: string): boolean => {
  const domain = email.split('@')[1]?.toLowerCase();
  return CORP_EMAIL_DOMAINS.includes(domain);
};

// Authentication storage keys
export const AUTH_STORAGE_KEYS = {
  accessToken: 'kms_access_token',
  refreshToken: 'kms_refresh_token',
  user: 'kms_user',
};
