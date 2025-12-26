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
  /** Is current language Japanese */
  isJapanese: boolean;
  /** Cycle through languages (en → ko → ja → en) */
  toggleLanguage: () => void;
  /** Get next language in cycle */
  getNextLanguage: () => LanguageCode;
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
// Language cycle order
const LANGUAGE_CYCLE: LanguageCode[] = ['en', 'ko', 'ja'];

export const useTranslation = (): UseTranslationReturn => {
  const { language, setLanguage, t, isLoading } = useI18nContext();

  /**
   * Get the next language in the cycle
   */
  const getNextLanguage = useCallback((): LanguageCode => {
    const currentIndex = LANGUAGE_CYCLE.indexOf(language);
    const nextIndex = (currentIndex + 1) % LANGUAGE_CYCLE.length;
    return LANGUAGE_CYCLE[nextIndex];
  }, [language]);

  /**
   * Cycle through languages: en → ko → ja → en
   */
  const toggleLanguage = useCallback(() => {
    setLanguage(getNextLanguage());
  }, [getNextLanguage, setLanguage]);

  return {
    language,
    setLanguage,
    t: t as TranslateFunction,
    isLoading,
    languages: LANGUAGES,
    isKorean: language === 'ko',
    isEnglish: language === 'en',
    isJapanese: language === 'ja',
    toggleLanguage,
    getNextLanguage,
  };
};

export default useTranslation;
