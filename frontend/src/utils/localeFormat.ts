/**
 * Locale-Specific Formatting Utility
 *
 * Provides locale-aware formatting for dates, numbers, and currency
 * using the Intl API for consistent formatting across languages.
 */

import { LanguageCode, LocaleCode, LOCALE_MAP } from '../i18n/types';

/**
 * Locale formatter interface
 */
export interface LocaleFormatter {
  /** Format date with specified style */
  formatDate: (date: Date | string | number, style?: 'full' | 'long' | 'medium' | 'short') => string;
  /** Format time with specified style */
  formatTime: (date: Date | string | number, style?: 'full' | 'long' | 'medium' | 'short') => string;
  /** Format date and time together */
  formatDateTime: (
    date: Date | string | number,
    dateStyle?: 'full' | 'long' | 'medium' | 'short',
    timeStyle?: 'full' | 'long' | 'medium' | 'short'
  ) => string;
  /** Format number with options */
  formatNumber: (num: number, options?: Intl.NumberFormatOptions) => string;
  /** Format currency amount */
  formatCurrency: (amount: number, currency?: string) => string;
  /** Format relative time (e.g., "2 hours ago") */
  formatRelativeTime: (date: Date | string | number) => string;
  /** Format percentage */
  formatPercent: (value: number, decimals?: number) => string;
  /** Format compact number (e.g., 1K, 1M) */
  formatCompact: (num: number) => string;
  /** Get the current locale code */
  locale: LocaleCode;
}

/**
 * Default currency per language
 */
const DEFAULT_CURRENCIES: Record<LanguageCode, string> = {
  en: 'USD',
  ko: 'KRW',
  ja: 'JPY',
};

/**
 * Convert input to Date object
 */
function toDate(input: Date | string | number): Date {
  if (input instanceof Date) return input;
  return new Date(input);
}

/**
 * Calculate relative time units
 */
function getRelativeTimeUnit(diffMs: number): { value: number; unit: Intl.RelativeTimeFormatUnit } {
  const absDiff = Math.abs(diffMs);
  const sign = diffMs < 0 ? -1 : 1;

  const seconds = absDiff / 1000;
  const minutes = seconds / 60;
  const hours = minutes / 60;
  const days = hours / 24;
  const weeks = days / 7;
  const months = days / 30;
  const years = days / 365;

  if (seconds < 60) return { value: sign * Math.round(seconds), unit: 'second' };
  if (minutes < 60) return { value: sign * Math.round(minutes), unit: 'minute' };
  if (hours < 24) return { value: sign * Math.round(hours), unit: 'hour' };
  if (days < 7) return { value: sign * Math.round(days), unit: 'day' };
  if (weeks < 4) return { value: sign * Math.round(weeks), unit: 'week' };
  if (months < 12) return { value: sign * Math.round(months), unit: 'month' };
  return { value: sign * Math.round(years), unit: 'year' };
}

/**
 * Create a locale formatter for the specified language
 */
export function createLocaleFormatter(language: LanguageCode): LocaleFormatter {
  const locale = LOCALE_MAP[language];

  return {
    locale,

    formatDate: (date, style = 'medium') => {
      try {
        return new Intl.DateTimeFormat(locale, { dateStyle: style }).format(toDate(date));
      } catch {
        return toDate(date).toLocaleDateString(locale);
      }
    },

    formatTime: (date, style = 'short') => {
      try {
        return new Intl.DateTimeFormat(locale, { timeStyle: style }).format(toDate(date));
      } catch {
        return toDate(date).toLocaleTimeString(locale);
      }
    },

    formatDateTime: (date, dateStyle = 'medium', timeStyle = 'short') => {
      try {
        return new Intl.DateTimeFormat(locale, { dateStyle, timeStyle }).format(toDate(date));
      } catch {
        return toDate(date).toLocaleString(locale);
      }
    },

    formatNumber: (num, options = {}) => {
      return new Intl.NumberFormat(locale, options).format(num);
    },

    formatCurrency: (amount, currency = DEFAULT_CURRENCIES[language]) => {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        // JPY and KRW don't use decimal places
        minimumFractionDigits: ['JPY', 'KRW'].includes(currency) ? 0 : 2,
        maximumFractionDigits: ['JPY', 'KRW'].includes(currency) ? 0 : 2,
      }).format(amount);
    },

    formatRelativeTime: (date) => {
      const now = Date.now();
      const then = toDate(date).getTime();
      const diff = then - now; // Negative if in the past

      const { value, unit } = getRelativeTimeUnit(diff);

      try {
        const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
        return rtf.format(value, unit);
      } catch {
        // Fallback for environments without RelativeTimeFormat
        const absValue = Math.abs(value);
        const suffix = value < 0 ? 'ago' : 'from now';
        return `${absValue} ${unit}${absValue !== 1 ? 's' : ''} ${suffix}`;
      }
    },

    formatPercent: (value, decimals = 1) => {
      return new Intl.NumberFormat(locale, {
        style: 'percent',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value);
    },

    formatCompact: (num) => {
      return new Intl.NumberFormat(locale, {
        notation: 'compact',
        compactDisplay: 'short',
      }).format(num);
    },
  };
}

/**
 * Get currency symbol for a currency code
 */
export function getCurrencySymbol(currencyCode: string, locale: LocaleCode = 'en-US'): string {
  try {
    const parts = new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: currencyCode,
    }).formatToParts(0);

    const symbolPart = parts.find(part => part.type === 'currency');
    return symbolPart?.value ?? currencyCode;
  } catch {
    return currencyCode;
  }
}

/**
 * Format file size in human-readable format
 */
export function formatFileSize(bytes: number, locale: LocaleCode = 'en-US'): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let unitIndex = 0;
  let size = bytes;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  const formatted = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 1,
  }).format(size);

  return `${formatted} ${units[unitIndex]}`;
}

/**
 * Format duration in human-readable format
 */
export function formatDuration(
  milliseconds: number,
  language: LanguageCode = 'en'
): string {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const labels: Record<LanguageCode, { d: string; h: string; m: string; s: string }> = {
    en: { d: 'd', h: 'h', m: 'm', s: 's' },
    ko: { d: '일', h: '시간', m: '분', s: '초' },
    ja: { d: '日', h: '時間', m: '分', s: '秒' },
  };

  const l = labels[language];

  if (days > 0) return `${days}${l.d} ${hours % 24}${l.h}`;
  if (hours > 0) return `${hours}${l.h} ${minutes % 60}${l.m}`;
  if (minutes > 0) return `${minutes}${l.m} ${seconds % 60}${l.s}`;
  return `${seconds}${l.s}`;
}
