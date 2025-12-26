/**
 * useTranslation Hook
 *
 * Custom hook for easy access to i18n functionality
 * Provides translation function and language management
 */

import { useCallback } from 'react';
import { useI18nContext } from '../i18n/I18nContext';
import { LanguageCode, LANGUAGES, TranslateFunction } from '../i18n/types';

interface UseTranslationReturn {
  /** Current language code */
  language: LanguageCode;
  /** Set the language */
  setLanguage: (lang: LanguageCode) => void;
  /** Translation function */
  t: TranslateFunction;
  /** Is i18n still loading */
  isLoading: boolean;
  /** Available languages */
  languages: typeof LANGUAGES;
  /** Is current language Korean */
  isKorean: boolean;
  /** Is current language English */
  isEnglish: boolean;
  /** Toggle between languages */
  toggleLanguage: () => void;
}

/**
 * Hook for accessing translations
 *
 * @example
 * const { t, language, setLanguage } = useTranslation();
 *
 * return (
 *   <div>
 *     <h1>{t('common.appName')}</h1>
 *     <p>{t('dashboard.welcome', { name: 'John' })}</p>
 *     <button onClick={() => setLanguage('ko')}>한국어</button>
 *   </div>
 * );
 */
export const useTranslation = (): UseTranslationReturn => {
  const { language, setLanguage, t, isLoading } = useI18nContext();

  /**
   * Toggle between English and Korean
   */
  const toggleLanguage = useCallback(() => {
    setLanguage(language === 'en' ? 'ko' : 'en');
  }, [language, setLanguage]);

  return {
    language,
    setLanguage,
    t: t as TranslateFunction,
    isLoading,
    languages: LANGUAGES,
    isKorean: language === 'ko',
    isEnglish: language === 'en',
    toggleLanguage,
  };
};

export default useTranslation;
