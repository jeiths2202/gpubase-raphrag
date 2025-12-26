/**
 * i18n Module
 *
 * Internationalization system for KMS Platform
 * Supports English (en) and Korean (ko)
 */

import { LanguageCode, DEFAULT_LANGUAGE } from './types';

// Import English translations
import enCommon from './locales/en/common.json';
import enAuth from './locales/en/auth.json';
import enDashboard from './locales/en/dashboard.json';
import enKnowledge from './locales/en/knowledge.json';
import enMindmap from './locales/en/mindmap.json';
import enAdmin from './locales/en/admin.json';
import enErrors from './locales/en/errors.json';
import enTime from './locales/en/time.json';
import enStatus from './locales/en/status.json';

// Import Korean translations
import koCommon from './locales/ko/common.json';
import koAuth from './locales/ko/auth.json';
import koDashboard from './locales/ko/dashboard.json';
import koKnowledge from './locales/ko/knowledge.json';
import koMindmap from './locales/ko/mindmap.json';
import koAdmin from './locales/ko/admin.json';
import koErrors from './locales/ko/errors.json';
import koTime from './locales/ko/time.json';
import koStatus from './locales/ko/status.json';

// Import Japanese translations
import jaCommon from './locales/ja/common.json';
import jaAuth from './locales/ja/auth.json';
import jaDashboard from './locales/ja/dashboard.json';
import jaKnowledge from './locales/ja/knowledge.json';
import jaMindmap from './locales/ja/mindmap.json';
import jaAdmin from './locales/ja/admin.json';
import jaErrors from './locales/ja/errors.json';
import jaTime from './locales/ja/time.json';
import jaStatus from './locales/ja/status.json';

// Merge translations by namespace
const translations: Record<LanguageCode, Record<string, unknown>> = {
  en: {
    common: enCommon,
    auth: enAuth,
    dashboard: enDashboard,
    knowledge: enKnowledge,
    mindmap: enMindmap,
    admin: enAdmin,
    errors: enErrors,
    time: enTime,
    status: enStatus,
  },
  ko: {
    common: koCommon,
    auth: koAuth,
    dashboard: koDashboard,
    knowledge: koKnowledge,
    mindmap: koMindmap,
    admin: koAdmin,
    errors: koErrors,
    time: koTime,
    status: koStatus,
  },
  ja: {
    common: jaCommon,
    auth: jaAuth,
    dashboard: jaDashboard,
    knowledge: jaKnowledge,
    mindmap: jaMindmap,
    admin: jaAdmin,
    errors: jaErrors,
    time: jaTime,
    status: jaStatus,
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
 * Handle pluralization
 * Looks for key_plural when count > 1
 */
function handlePlural(
  translations: Record<string, unknown>,
  namespace: string,
  key: string,
  count?: number
): string | undefined {
  const nsData = translations[namespace];
  if (!nsData || typeof nsData !== 'object') return undefined;

  // If count is provided and > 1, try plural form first
  if (count !== undefined && count !== 1) {
    const pluralKey = `${key}_plural`;
    const pluralValue = getNestedValue(nsData, pluralKey);
    if (pluralValue) return pluralValue;
  }

  return getNestedValue(nsData, key);
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

  // Get count for pluralization
  const count = params?.count as number | undefined;

  // Try requested language first
  let value = handlePlural(langTranslations, namespace, translationKey, count);

  // Fallback to default language if not found
  if (value === undefined && language !== DEFAULT_LANGUAGE) {
    const defaultTranslations = translations[DEFAULT_LANGUAGE];
    value = handlePlural(defaultTranslations, namespace, translationKey, count);

    if (value !== undefined && process.env.NODE_ENV === 'development') {
      console.warn(`[i18n] Missing translation for "${key}" in "${language}", using fallback`);
    }
  }

  // Return key if not found anywhere
  if (value === undefined) {
    if (process.env.NODE_ENV === 'development') {
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
