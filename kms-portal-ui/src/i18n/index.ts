/**
 * i18n Module for KMS Portal UI
 *
 * Internationalization system supporting English, Korean, and Japanese
 */

import { LanguageCode, DEFAULT_LANGUAGE } from './types';

// Import English translations
import enCommon from './locales/en/common.json';
import enAuth from './locales/en/auth.json';
import enKnowledge from './locales/en/knowledge.json';
import enIms from './locales/en/ims.json';
import enMindmap from './locales/en/mindmap.json';
import enStudio from './locales/en/studio.json';
import enPortal from './locales/en/portal.json';
import enFaq from './locales/en/faq.json';

// Import Korean translations
import koCommon from './locales/ko/common.json';
import koAuth from './locales/ko/auth.json';
import koKnowledge from './locales/ko/knowledge.json';
import koIms from './locales/ko/ims.json';
import koMindmap from './locales/ko/mindmap.json';
import koStudio from './locales/ko/studio.json';
import koPortal from './locales/ko/portal.json';
import koFaq from './locales/ko/faq.json';

// Import Japanese translations
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import jaKnowledge from './locales/ja/knowledge.json';
import jaIms from './locales/ja/ims.json';
import jaMindmap from './locales/ja/mindmap.json';
import jaStudio from './locales/ja/studio.json';
import jaPortal from './locales/ja/portal.json';
import jaFaq from './locales/ja/faq.json';

// Merge translations by namespace
const translations: Record<LanguageCode, Record<string, unknown>> = {
  en: {
    common: enCommon,
    auth: enAuth,
    knowledge: enKnowledge,
    ims: enIms,
    mindmap: enMindmap,
    studio: enStudio,
    portal: enPortal,
    faq: enFaq,
  },
  ko: {
    common: koCommon,
    auth: koAuth,
    knowledge: koKnowledge,
    ims: koIms,
    mindmap: koMindmap,
    studio: koStudio,
    portal: koPortal,
    faq: koFaq,
  },
  ja: {
    common: jaCommon,
    auth: jaAuth,
    knowledge: jaKnowledge,
    ims: jaIms,
    mindmap: jaMindmap,
    studio: jaStudio,
    portal: jaPortal,
    faq: jaFaq,
  },
};

/**
 * Get nested value from object using dot notation
 */
function getNestedValue(obj: unknown, path: string): string | undefined {
  const keys = path.split('.');
  let current: unknown = obj;

  for (const key of keys) {
    if (current === null || current === undefined) {
      return undefined;
    }
    if (typeof current === 'object' && key in current) {
      current = (current as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }

  return typeof current === 'string' ? current : undefined;
}

/**
 * Replace template variables in string
 * Supports {{variable}} syntax
 */
function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;

  return template.replace(/\{\{(\w+)\}\}/g, (match, key) => {
    const value = params[key];
    return value !== undefined ? String(value) : match;
  });
}

/**
 * Translate a key to the specified language
 */
export function translate(
  language: LanguageCode,
  key: string,
  params?: Record<string, string | number>
): string {
  // Parse key: "namespace.path.to.key" or "namespace.key"
  const [namespace, ...rest] = key.split('.');
  const translationKey = rest.join('.');

  if (!translationKey) {
    console.warn(`[i18n] Invalid key format: ${key}`);
    return key;
  }

  const langTranslations = translations[language];
  if (!langTranslations) {
    console.warn(`[i18n] Unknown language: ${language}`);
    return key;
  }

  // Try requested language first
  const nsData = langTranslations[namespace];
  let value = nsData ? getNestedValue(nsData, translationKey) : undefined;

  // Fallback to default language if not found
  if (value === undefined && language !== DEFAULT_LANGUAGE) {
    const defaultTranslations = translations[DEFAULT_LANGUAGE];
    const defaultNsData = defaultTranslations[namespace];
    value = defaultNsData ? getNestedValue(defaultNsData, translationKey) : undefined;

    if (value !== undefined && import.meta.env.DEV) {
      console.warn(`[i18n] Missing translation for "${key}" in "${language}", using fallback`);
    }
  }

  // Return key if not found anywhere
  if (value === undefined) {
    if (import.meta.env.DEV) {
      console.warn(`[i18n] Missing translation: ${key}`);
    }
    return key;
  }

  // Interpolate params
  return interpolate(value, params);
}

/**
 * Create a translation function bound to a specific language
 */
export function createTranslator(language: LanguageCode) {
  return (key: string, params?: Record<string, string | number>) =>
    translate(language, key, params);
}

/**
 * Get all translations for a language
 */
export function getTranslations(language: LanguageCode): Record<string, unknown> {
  return translations[language] || translations[DEFAULT_LANGUAGE];
}

// Re-export types
export * from './types';
