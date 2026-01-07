/**
 * i18n Type Definitions for KMS Portal UI
 */

// Supported language codes
export type LanguageCode = 'en' | 'ko' | 'ja';

// Locale codes with region
export type LocaleCode = 'en-US' | 'ko-KR' | 'ja-JP';

// Map language codes to full locale codes
export const LOCALE_MAP: Record<LanguageCode, LocaleCode> = {
  en: 'en-US',
  ko: 'ko-KR',
  ja: 'ja-JP',
};

// Language metadata
export interface LanguageInfo {
  code: LanguageCode;
  name: string;
  nativeName: string;
  flag: string;
}

// Available languages configuration
export const LANGUAGES: Record<LanguageCode, LanguageInfo> = {
  en: {
    code: 'en',
    name: 'English',
    nativeName: 'English',
    flag: '🇺🇸',
  },
  ko: {
    code: 'ko',
    name: 'Korean',
    nativeName: '한국어',
    flag: '🇰🇷',
  },
  ja: {
    code: 'ja',
    name: 'Japanese',
    nativeName: '日本語',
    flag: '🇯🇵',
  },
};

// Default language
export const DEFAULT_LANGUAGE: LanguageCode = 'en';

// Translation function type
export type TranslateFunction = (
  key: string,
  params?: Record<string, string | number>
) => string;

// i18n Context type
export interface I18nContextType {
  language: LanguageCode;
  setLanguage: (lang: LanguageCode) => void;
  t: TranslateFunction;
  isLoading: boolean;
}
