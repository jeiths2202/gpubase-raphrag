/**
 * Tests for Browser Language Detection Utility
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  detectBrowserLanguage,
  initializeLanguage,
  isSupportedLanguage,
  getBrowserLanguageInfo,
} from '../../utils/browserLanguage';

describe('detectBrowserLanguage', () => {
  const originalNavigator = global.navigator;

  afterEach(() => {
    // Restore original navigator
    Object.defineProperty(global, 'navigator', {
      value: originalNavigator,
      writable: true,
    });
  });

  it('returns "ja" for Japanese browser language', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ja-JP',
        languages: ['ja-JP', 'ja', 'en-US'],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('ja');
  });

  it('returns "ko" for Korean browser language', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ko-KR',
        languages: ['ko-KR', 'ko', 'en-US'],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('ko');
  });

  it('returns "en" for English browser language', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'en-US',
        languages: ['en-US', 'en'],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('en');
  });

  it('returns "en" for unsupported browser language', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'fr-FR',
        languages: ['fr-FR', 'fr'],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('en');
  });

  it('handles lowercase language codes', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'JA-jp',
        languages: ['JA-jp'],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('ja');
  });

  it('prioritizes first supported language in navigator.languages', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'fr-FR',
        languages: ['fr-FR', 'ko-KR', 'ja-JP', 'en-US'],
      },
      writable: true,
    });

    // Should return ko as it's the first supported language in the array
    expect(detectBrowserLanguage()).toBe('ko');
  });

  it('falls back to navigator.language if languages array is empty', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ja-JP',
        languages: [],
      },
      writable: true,
    });

    expect(detectBrowserLanguage()).toBe('ja');
  });
});

describe('initializeLanguage', () => {
  beforeEach(() => {
    // Clear localStorage before each test
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('returns stored language from localStorage', () => {
    localStorage.setItem(
      'kms-preferences',
      JSON.stringify({ state: { language: 'ja' } })
    );

    expect(initializeLanguage()).toBe('ja');
  });

  it('returns stored Korean language', () => {
    localStorage.setItem(
      'kms-preferences',
      JSON.stringify({ state: { language: 'ko' } })
    );

    expect(initializeLanguage()).toBe('ko');
  });

  it('falls back to browser detection when localStorage is empty', () => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ja-JP',
        languages: ['ja-JP'],
      },
      writable: true,
    });

    expect(initializeLanguage()).toBe('ja');
  });

  it('falls back to browser detection for invalid stored language', () => {
    localStorage.setItem(
      'kms-preferences',
      JSON.stringify({ state: { language: 'invalid' } })
    );

    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ko-KR',
        languages: ['ko-KR'],
      },
      writable: true,
    });

    expect(initializeLanguage()).toBe('ko');
  });

  it('handles malformed localStorage data', () => {
    localStorage.setItem('kms-preferences', 'invalid-json');

    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'en-US',
        languages: ['en-US'],
      },
      writable: true,
    });

    expect(initializeLanguage()).toBe('en');
  });
});

describe('isSupportedLanguage', () => {
  it('returns true for supported languages', () => {
    expect(isSupportedLanguage('en')).toBe(true);
    expect(isSupportedLanguage('ko')).toBe(true);
    expect(isSupportedLanguage('ja')).toBe(true);
  });

  it('returns false for unsupported languages', () => {
    expect(isSupportedLanguage('fr')).toBe(false);
    expect(isSupportedLanguage('de')).toBe(false);
    expect(isSupportedLanguage('zh')).toBe(false);
    expect(isSupportedLanguage('')).toBe(false);
    expect(isSupportedLanguage('invalid')).toBe(false);
  });
});

describe('getBrowserLanguageInfo', () => {
  beforeEach(() => {
    Object.defineProperty(global, 'navigator', {
      value: {
        language: 'ja-JP',
        languages: ['ja-JP', 'en-US', 'ko-KR'],
      },
      writable: true,
    });
  });

  it('returns detected language', () => {
    const info = getBrowserLanguageInfo();
    expect(info.detected).toBe('ja');
  });

  it('returns browser locale', () => {
    const info = getBrowserLanguageInfo();
    expect(info.browserLocale).toBe('ja-JP');
  });

  it('returns browser languages array', () => {
    const info = getBrowserLanguageInfo();
    expect(info.browserLanguages).toContain('ja-JP');
    expect(info.browserLanguages).toContain('en-US');
    expect(info.browserLanguages).toContain('ko-KR');
  });
});
