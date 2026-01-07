/**
 * I18n Context for KMS Portal UI
 *
 * React context for internationalization
 * Provides language state and translation function to components
 */

import React, { createContext, useContext, useCallback, useEffect, useState } from 'react';
import { LanguageCode, DEFAULT_LANGUAGE, I18nContextType } from './types';
import { translate } from './index';

// Create context with undefined default
const I18nContext = createContext<I18nContextType | undefined>(undefined);

// Storage key for language preference
const LANGUAGE_STORAGE_KEY = 'kms-portal-language';

// Provider props
interface I18nProviderProps {
  children: React.ReactNode;
  defaultLanguage?: LanguageCode;
}

/**
 * Get initial language from localStorage or browser
 */
function getInitialLanguage(defaultLang: LanguageCode): LanguageCode {
  // Check localStorage first
  const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (stored && ['en', 'ko', 'ja'].includes(stored)) {
    return stored as LanguageCode;
  }

  // Check browser language
  const browserLang = navigator.language.split('-')[0];
  if (['en', 'ko', 'ja'].includes(browserLang)) {
    return browserLang as LanguageCode;
  }

  return defaultLang;
}

/**
 * I18n Provider Component
 *
 * Wraps the app to provide translation context
 */
export const I18nProvider: React.FC<I18nProviderProps> = ({
  children,
  defaultLanguage = DEFAULT_LANGUAGE,
}) => {
  const [language, setLanguageState] = useState<LanguageCode>(() =>
    getInitialLanguage(defaultLanguage)
  );
  const [isLoading, setIsLoading] = useState(true);

  // Set document language attribute
  useEffect(() => {
    document.documentElement.lang = language;
    setIsLoading(false);
  }, [language]);

  // Set language handler with persistence
  const setLanguage = useCallback((newLanguage: LanguageCode) => {
    setLanguageState(newLanguage);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, newLanguage);
  }, []);

  // Translation function
  const t = useCallback(
    (key: string, params?: Record<string, string | number>) => {
      return translate(language, key, params);
    },
    [language]
  );

  const value: I18nContextType = {
    language,
    setLanguage,
    t,
    isLoading,
  };

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};

/**
 * Use I18n Context Hook
 *
 * Must be used within I18nProvider
 */
export const useI18nContext = (): I18nContextType => {
  const context = useContext(I18nContext);

  if (context === undefined) {
    throw new Error('useI18nContext must be used within an I18nProvider');
  }

  return context;
};

export default I18nContext;
