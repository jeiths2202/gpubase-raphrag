/**
 * useLanguagePolicy Hook
 *
 * Provides language policy information based on user's role.
 * Fetches allowed languages from the backend and validates language selections.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuthStore } from '../store/authStore';
import { LanguageCode, LANGUAGES } from '../i18n/types';

/**
 * Language restriction levels
 */
export type RestrictionLevel = 'none' | 'preferred' | 'enforced';

/**
 * Language policy response from API
 */
export interface LanguagePolicyInfo {
  allowed_languages: string[];
  default_language: string;
  restriction_level: RestrictionLevel;
  allow_auto_detect: boolean;
  current_language: string | null;
}

/**
 * Hook return type
 */
export interface UseLanguagePolicyReturn {
  /** List of languages allowed for current user */
  allowedLanguages: LanguageCode[];
  /** Default language for current user */
  defaultLanguage: LanguageCode;
  /** Restriction level for current user */
  restrictionLevel: RestrictionLevel;
  /** Whether auto-detect is allowed */
  allowAutoDetect: boolean;
  /** Whether policy is still loading */
  isLoading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Check if a specific language is allowed */
  isLanguageAllowed: (lang: LanguageCode) => boolean;
  /** Get filtered language options for selectors */
  getFilteredLanguages: () => Array<{ code: LanguageCode; name: string; nativeName: string; flag: string }>;
  /** Refresh policy from server */
  refreshPolicy: () => Promise<void>;
}

/**
 * Default policy when not authenticated or API fails
 */
const DEFAULT_POLICY: LanguagePolicyInfo = {
  allowed_languages: ['en', 'ko', 'ja'],
  default_language: 'en',
  restriction_level: 'none',
  allow_auto_detect: true,
  current_language: null,
};

/**
 * Hook for accessing language policy based on user role
 *
 * @example
 * const { allowedLanguages, isLanguageAllowed, getFilteredLanguages } = useLanguagePolicy();
 *
 * // Check if Japanese is allowed
 * if (isLanguageAllowed('ja')) {
 *   // Show Japanese option
 * }
 *
 * // Get only allowed languages for selector
 * const languages = getFilteredLanguages();
 */
export function useLanguagePolicy(): UseLanguagePolicyReturn {
  const [policy, setPolicy] = useState<LanguagePolicyInfo>(DEFAULT_POLICY);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { isAuthenticated, user } = useAuthStore();

  /**
   * Fetch language policy from server
   */
  const fetchPolicy = useCallback(async () => {
    if (!isAuthenticated) {
      setPolicy(DEFAULT_POLICY);
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/v1/preferences/language-policy', {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch language policy');
      }

      const data = await response.json();
      if (data.data) {
        setPolicy(data.data);
      }
    } catch (err) {
      console.warn('Failed to fetch language policy, using defaults:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
      // Use default policy on error
      setPolicy(DEFAULT_POLICY);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  /**
   * Refresh policy from server
   */
  const refreshPolicy = useCallback(async () => {
    await fetchPolicy();
  }, [fetchPolicy]);

  // Fetch policy on mount and when auth changes
  useEffect(() => {
    fetchPolicy();
  }, [fetchPolicy, user?.role]);

  /**
   * Get allowed languages as LanguageCode array
   */
  const allowedLanguages = useMemo<LanguageCode[]>(() => {
    return policy.allowed_languages.filter(
      (lang): lang is LanguageCode => ['en', 'ko', 'ja'].includes(lang)
    );
  }, [policy.allowed_languages]);

  /**
   * Get default language as LanguageCode
   */
  const defaultLanguage = useMemo<LanguageCode>(() => {
    const lang = policy.default_language;
    return ['en', 'ko', 'ja'].includes(lang) ? (lang as LanguageCode) : 'en';
  }, [policy.default_language]);

  /**
   * Check if a language is allowed
   */
  const isLanguageAllowed = useCallback(
    (lang: LanguageCode): boolean => {
      return allowedLanguages.includes(lang);
    },
    [allowedLanguages]
  );

  /**
   * Get filtered language options for UI selectors
   */
  const getFilteredLanguages = useCallback(() => {
    return allowedLanguages.map((code) => ({
      code,
      name: LANGUAGES[code].name,
      nativeName: LANGUAGES[code].nativeName,
      flag: LANGUAGES[code].flag,
    }));
  }, [allowedLanguages]);

  return {
    allowedLanguages,
    defaultLanguage,
    restrictionLevel: policy.restriction_level,
    allowAutoDetect: policy.allow_auto_detect,
    isLoading,
    error,
    isLanguageAllowed,
    getFilteredLanguages,
    refreshPolicy,
  };
}

export default useLanguagePolicy;
