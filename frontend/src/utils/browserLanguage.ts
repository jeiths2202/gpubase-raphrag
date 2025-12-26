/**
 * Browser Language Detection Utility
 *
 * Detects user's preferred language from browser settings
 * and provides initialization for language preference.
 */

import type { LanguageCode } from '../i18n/types';

/**
 * Detect the user's preferred language from browser settings
 * Maps browser locale to our supported languages (en, ko, ja)
 */
export function detectBrowserLanguage(): LanguageCode {
  if (typeof navigator === 'undefined') {
    return 'en'; // Default for SSR
  }

  // Get browser languages in order of preference
  const browserLanguages = navigator.languages?.length
    ? navigator.languages
    : [navigator.language];

  for (const lang of browserLanguages) {
    const normalizedLang = lang.toLowerCase();

    // Check for Japanese
    if (normalizedLang.startsWith('ja')) {
      return 'ja';
    }

    // Check for Korean
    if (normalizedLang.startsWith('ko')) {
      return 'ko';
    }

    // Check for English
    if (normalizedLang.startsWith('en')) {
      return 'en';
    }
  }

  // Default fallback to English
  return 'en';
}

/**
 * Initialize language preference
 * Priority: localStorage > browser detection
 */
export function initializeLanguage(): LanguageCode {
  if (typeof localStorage === 'undefined') {
    return detectBrowserLanguage();
  }

  try {
    // Check localStorage first (user's explicit preference)
    const stored = localStorage.getItem('kms-preferences');
    if (stored) {
      const prefs = JSON.parse(stored);
      const storedLang = prefs.state?.language;
      if (storedLang && ['en', 'ko', 'ja'].includes(storedLang)) {
        return storedLang as LanguageCode;
      }
    }
  } catch {
    // localStorage parse failed, fall through to detection
  }

  // Fallback to browser detection
  return detectBrowserLanguage();
}

/**
 * Check if a language code is supported
 */
export function isSupportedLanguage(lang: string): lang is LanguageCode {
  return ['en', 'ko', 'ja'].includes(lang);
}

/**
 * Get language display info for browser locale
 */
export function getBrowserLanguageInfo(): {
  detected: LanguageCode;
  browserLocale: string;
  browserLanguages: readonly string[];
} {
  const browserLocale = typeof navigator !== 'undefined' ? navigator.language : 'en-US';
  const browserLanguages = typeof navigator !== 'undefined' && navigator.languages?.length
    ? navigator.languages
    : [browserLocale];

  return {
    detected: detectBrowserLanguage(),
    browserLocale,
    browserLanguages,
  };
}
