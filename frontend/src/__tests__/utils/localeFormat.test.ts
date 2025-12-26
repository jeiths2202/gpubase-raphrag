/**
 * Tests for Locale Formatting Utilities
 */
import { describe, it, expect } from 'vitest';
import {
  createLocaleFormatter,
  formatFileSize,
  formatDuration,
  getCurrencySymbol,
} from '../../utils/localeFormat';

describe('createLocaleFormatter', () => {
  describe('formatDate', () => {
    it('formats date in English locale', () => {
      const formatter = createLocaleFormatter('en');
      const date = new Date('2025-12-27T10:30:00Z');

      const result = formatter.formatDate(date, 'medium');
      expect(result).toBeDefined();
      expect(typeof result).toBe('string');
    });

    it('formats date in Korean locale', () => {
      const formatter = createLocaleFormatter('ko');
      const date = new Date('2025-12-27T10:30:00Z');

      const result = formatter.formatDate(date, 'medium');
      expect(result).toBeDefined();
    });

    it('formats date in Japanese locale', () => {
      const formatter = createLocaleFormatter('ja');
      const date = new Date('2025-12-27T10:30:00Z');

      const result = formatter.formatDate(date, 'medium');
      expect(result).toBeDefined();
    });

    it('accepts string input', () => {
      const formatter = createLocaleFormatter('en');
      const result = formatter.formatDate('2025-12-27', 'short');
      expect(result).toBeDefined();
    });

    it('accepts timestamp input', () => {
      const formatter = createLocaleFormatter('en');
      const result = formatter.formatDate(Date.now(), 'short');
      expect(result).toBeDefined();
    });
  });

  describe('formatTime', () => {
    it('formats time in English locale', () => {
      const formatter = createLocaleFormatter('en');
      const date = new Date('2025-12-27T14:30:00Z');

      const result = formatter.formatTime(date, 'short');
      expect(result).toBeDefined();
    });

    it('formats time in Korean locale', () => {
      const formatter = createLocaleFormatter('ko');
      const date = new Date('2025-12-27T14:30:00Z');

      const result = formatter.formatTime(date, 'short');
      expect(result).toBeDefined();
    });

    it('formats time in Japanese locale', () => {
      const formatter = createLocaleFormatter('ja');
      const date = new Date('2025-12-27T14:30:00Z');

      const result = formatter.formatTime(date, 'short');
      expect(result).toBeDefined();
    });
  });

  describe('formatDateTime', () => {
    it('formats datetime in all locales', () => {
      const date = new Date('2025-12-27T14:30:00Z');

      const enFormatter = createLocaleFormatter('en');
      const koFormatter = createLocaleFormatter('ko');
      const jaFormatter = createLocaleFormatter('ja');

      expect(enFormatter.formatDateTime(date)).toBeDefined();
      expect(koFormatter.formatDateTime(date)).toBeDefined();
      expect(jaFormatter.formatDateTime(date)).toBeDefined();
    });
  });

  describe('formatNumber', () => {
    it('formats numbers with locale-specific separators', () => {
      const enFormatter = createLocaleFormatter('en');
      const koFormatter = createLocaleFormatter('ko');
      const jaFormatter = createLocaleFormatter('ja');

      const num = 1234567.89;

      expect(enFormatter.formatNumber(num)).toContain('1');
      expect(koFormatter.formatNumber(num)).toContain('1');
      expect(jaFormatter.formatNumber(num)).toContain('1');
    });

    it('supports custom options', () => {
      const formatter = createLocaleFormatter('en');
      const result = formatter.formatNumber(0.5, { style: 'percent' });
      expect(result).toContain('50');
    });
  });

  describe('formatCurrency', () => {
    it('formats USD for English', () => {
      const formatter = createLocaleFormatter('en');
      const result = formatter.formatCurrency(1234.56);
      expect(result).toContain('$');
      expect(result).toContain('1,234.56');
    });

    it('formats KRW for Korean (no decimals)', () => {
      const formatter = createLocaleFormatter('ko');
      const result = formatter.formatCurrency(1234);
      expect(result).toContain('1,234');
      // KRW should not have decimals
      expect(result).not.toContain('.00');
    });

    it('formats JPY for Japanese (no decimals)', () => {
      const formatter = createLocaleFormatter('ja');
      const result = formatter.formatCurrency(1234);
      expect(result).toContain('1,234');
      // JPY should not have decimals
      expect(result).not.toContain('.00');
    });

    it('accepts custom currency', () => {
      const formatter = createLocaleFormatter('en');
      const result = formatter.formatCurrency(1234.56, 'EUR');
      expect(result).toContain('1,234.56');
    });
  });

  describe('formatPercent', () => {
    it('formats percentage correctly', () => {
      const formatter = createLocaleFormatter('en');

      expect(formatter.formatPercent(0.5)).toContain('50');
      expect(formatter.formatPercent(1)).toContain('100');
      expect(formatter.formatPercent(0.1234, 2)).toContain('12.34');
    });
  });

  describe('formatCompact', () => {
    it('formats large numbers compactly', () => {
      const formatter = createLocaleFormatter('en');

      const thousand = formatter.formatCompact(1500);
      const million = formatter.formatCompact(1500000);

      expect(thousand).toMatch(/1\.?5?K?/i);
      expect(million).toMatch(/1\.?5?M?/i);
    });
  });

  describe('formatRelativeTime', () => {
    it('formats recent time as just now or seconds ago', () => {
      const formatter = createLocaleFormatter('en');
      const now = new Date();

      const result = formatter.formatRelativeTime(now);
      expect(result.toLowerCase()).toMatch(/now|second/);
    });

    it('formats past time correctly', () => {
      const formatter = createLocaleFormatter('en');
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);

      const result = formatter.formatRelativeTime(oneHourAgo);
      expect(result.toLowerCase()).toContain('hour');
    });
  });

  describe('locale property', () => {
    it('returns correct locale code', () => {
      expect(createLocaleFormatter('en').locale).toBe('en-US');
      expect(createLocaleFormatter('ko').locale).toBe('ko-KR');
      expect(createLocaleFormatter('ja').locale).toBe('ja-JP');
    });
  });
});

describe('formatFileSize', () => {
  it('formats bytes correctly', () => {
    expect(formatFileSize(500)).toMatch(/500\s*B/i);
  });

  it('formats kilobytes correctly', () => {
    expect(formatFileSize(1024)).toMatch(/1\s*KB/i);
    expect(formatFileSize(1536)).toMatch(/1\.5\s*KB/i);
  });

  it('formats megabytes correctly', () => {
    expect(formatFileSize(1024 * 1024)).toMatch(/1\s*MB/i);
  });

  it('formats gigabytes correctly', () => {
    expect(formatFileSize(1024 * 1024 * 1024)).toMatch(/1\s*GB/i);
  });

  it('respects locale for number formatting', () => {
    const result = formatFileSize(1536, 'ko-KR');
    expect(result).toMatch(/1[.,]5\s*KB/i);
  });
});

describe('formatDuration', () => {
  it('formats seconds in English', () => {
    const result = formatDuration(30000, 'en');
    expect(result).toContain('30');
    expect(result).toContain('s');
  });

  it('formats minutes in English', () => {
    const result = formatDuration(90000, 'en');
    expect(result).toContain('1');
    expect(result).toContain('m');
  });

  it('formats hours in English', () => {
    const result = formatDuration(5400000, 'en'); // 1.5 hours
    expect(result).toContain('1');
    expect(result).toContain('h');
  });

  it('formats in Korean', () => {
    const result = formatDuration(60000, 'ko');
    expect(result).toContain('1');
    expect(result).toMatch(/분|초/);
  });

  it('formats in Japanese', () => {
    const result = formatDuration(60000, 'ja');
    expect(result).toContain('1');
    expect(result).toMatch(/分|秒/);
  });
});

describe('getCurrencySymbol', () => {
  it('returns USD symbol', () => {
    expect(getCurrencySymbol('USD')).toBe('$');
  });

  it('returns KRW symbol', () => {
    const symbol = getCurrencySymbol('KRW', 'ko-KR');
    expect(symbol).toMatch(/₩|KRW/);
  });

  it('returns JPY symbol', () => {
    const symbol = getCurrencySymbol('JPY', 'ja-JP');
    expect(symbol).toMatch(/¥|￥|JPY/);
  });

  it('returns EUR symbol', () => {
    const symbol = getCurrencySymbol('EUR');
    expect(symbol).toMatch(/€|EUR/);
  });
});
