/**
 * useLocaleFormat Hook
 *
 * React hook for locale-aware formatting of dates, numbers, and currency.
 * Automatically updates when the language preference changes.
 */

import { useMemo } from 'react';
import { usePreferencesStore } from '../store/preferencesStore';
import {
  createLocaleFormatter,
  formatFileSize,
  formatDuration,
  getCurrencySymbol,
  LocaleFormatter,
} from '../utils/localeFormat';
import { LOCALE_MAP } from '../i18n/types';

/**
 * Extended locale formatter with additional utilities
 */
export interface UseLocaleFormatReturn extends LocaleFormatter {
  /** Format file size (e.g., "1.5 MB") */
  formatFileSize: (bytes: number) => string;
  /** Format duration (e.g., "2h 30m") */
  formatDuration: (milliseconds: number) => string;
  /** Get currency symbol */
  getCurrencySymbol: (currencyCode: string) => string;
  /** Current language code */
  language: 'en' | 'ko' | 'ja';
}

/**
 * Hook for locale-aware formatting
 *
 * @example
 * const format = useLocaleFormat();
 *
 * return (
 *   <div>
 *     <p>Date: {format.formatDate(new Date())}</p>
 *     <p>Time: {format.formatTime(new Date())}</p>
 *     <p>Price: {format.formatCurrency(1234.56)}</p>
 *     <p>Percent: {format.formatPercent(0.85)}</p>
 *     <p>Relative: {format.formatRelativeTime(pastDate)}</p>
 *     <p>Size: {format.formatFileSize(1024000)}</p>
 *   </div>
 * );
 */
export function useLocaleFormat(): UseLocaleFormatReturn {
  const language = usePreferencesStore((state) => state.language);

  const formatter = useMemo(() => {
    const baseFormatter = createLocaleFormatter(language);
    const locale = LOCALE_MAP[language];

    return {
      ...baseFormatter,
      language,
      formatFileSize: (bytes: number) => formatFileSize(bytes, locale),
      formatDuration: (milliseconds: number) => formatDuration(milliseconds, language),
      getCurrencySymbol: (currencyCode: string) => getCurrencySymbol(currencyCode, locale),
    };
  }, [language]);

  return formatter;
}

export default useLocaleFormat;
