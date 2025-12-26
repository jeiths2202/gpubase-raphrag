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
