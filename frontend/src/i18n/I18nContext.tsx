/**
 * I18n Context
 *
 * React context for internationalization
 * Provides language state and translation function to components
 */

import React, { createContext, useContext, useCallback, useEffect, useState } from 'react';
import { LanguageCode, DEFAULT_LANGUAGE, I18nContextType } from './types';
import { translate } from './index';
import { usePreferencesStore } from '../store/preferencesStore';

// Create context with undefined default
const I18nContext = createContext<I18nContextType | undefined>(undefined);

// Provider props
interface I18nProviderProps {
  children: React.ReactNode;
  defaultLanguage?: LanguageCode;
}

/**
 * I18n Provider Component
 *
 * Wraps the app to provide translation context
 * Integrates with preferencesStore for persistence
 */
export const I18nProvider: React.FC<I18nProviderProps> = ({
  children,
  defaultLanguage = DEFAULT_LANGUAGE,
}) => {
  const { language: storedLanguage, setLanguage: setStoredLanguage } = usePreferencesStore();
  const [isLoading, setIsLoading] = useState(true);

  // Use stored language or default
  const language = (storedLanguage as LanguageCode) || defaultLanguage;

  // Set document language attribute
  useEffect(() => {
    document.documentElement.lang = language;
    setIsLoading(false);
  }, [language]);

  // Set language handler
  const setLanguage = useCallback(
    (newLanguage: LanguageCode) => {
      setStoredLanguage(newLanguage);
    },
    [setStoredLanguage]
  );

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
