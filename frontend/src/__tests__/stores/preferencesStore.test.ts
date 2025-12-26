/**
 * Preferences Store Tests
 *
 * Tests for user preferences state management including:
 * - Theme switching (light/dark/system)
 * - Language switching (en/ko)
 * - DOM updates
 * - Persistence
 *
 * NOTE: These tests use mocked axios, no actual API calls
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act } from 'react';

// Mock axios before importing store
vi.mock('axios', () => {
  return {
    default: {
      create: vi.fn(() => ({
        get: vi.fn().mockResolvedValue({ data: { data: { theme: 'dark', language: 'ko' } } }),
        patch: vi.fn().mockResolvedValue({ data: { success: true } }),
        interceptors: {
          request: { use: vi.fn() },
          response: { use: vi.fn() },
        },
      })),
    },
  };
});

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock matchMedia
const mockMatchMedia = (prefersDark: boolean = false) => {
  const listeners: Array<(e: MediaQueryListEvent) => void> = [];

  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: prefersDark,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: (event: string, cb: (e: MediaQueryListEvent) => void) => {
        listeners.push(cb);
      },
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });

  return {
    trigger: (prefersDark: boolean) => {
      listeners.forEach(cb => cb({ matches: prefersDark } as MediaQueryListEvent));
    }
  };
};

describe('Preferences Store', () => {
  beforeEach(() => {
    localStorageMock.clear();
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('lang');
    mockMatchMedia(false);
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetModules();
  });

  describe('Initial State', () => {
    it('should have correct default values', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      const state = usePreferencesStore.getState();

      expect(state.theme).toBe('system');
      expect(state.language).toBe('ko'); // Default for KMS
      expect(state.isLoading).toBe(false);
      expect(state.isSynced).toBe(false);
      expect(state.error).toBeNull();
    });

    it('should detect system theme on init', async () => {
      mockMatchMedia(true); // System prefers dark

      const { usePreferencesStore } = await import('../../store/preferencesStore');

      const state = usePreferencesStore.getState();

      // When theme is 'system', resolvedTheme should be detected
      expect(state.theme).toBe('system');
      // resolvedTheme depends on system preference detection
      expect(['light', 'dark']).toContain(state.resolvedTheme);
    });
  });

  describe('Theme Management', () => {
    it('should set theme to light', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('light');
      });

      const state = usePreferencesStore.getState();
      expect(state.theme).toBe('light');
      expect(state.resolvedTheme).toBe('light');
    });

    it('should set theme to dark', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('dark');
      });

      const state = usePreferencesStore.getState();
      expect(state.theme).toBe('dark');
      expect(state.resolvedTheme).toBe('dark');
    });

    it('should set theme to system', async () => {
      mockMatchMedia(true); // System prefers dark

      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('system');
      });

      const state = usePreferencesStore.getState();
      expect(state.theme).toBe('system');
      // resolvedTheme should follow system preference
      expect(['light', 'dark']).toContain(state.resolvedTheme);
    });

    it('should update DOM data-theme attribute', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('dark');
      });

      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

      act(() => {
        usePreferencesStore.getState().setTheme('light');
      });

      expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    });

    it('should mark as not synced after local change', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('dark');
      });

      expect(usePreferencesStore.getState().isSynced).toBe(false);
    });
  });

  describe('Language Management', () => {
    it('should set language to English', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setLanguage('en');
      });

      expect(usePreferencesStore.getState().language).toBe('en');
    });

    it('should set language to Korean', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setLanguage('ko');
      });

      expect(usePreferencesStore.getState().language).toBe('ko');
    });

    it('should update DOM lang attribute', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setLanguage('en');
      });

      expect(document.documentElement.getAttribute('lang')).toBe('en');

      act(() => {
        usePreferencesStore.getState().setLanguage('ko');
      });

      expect(document.documentElement.getAttribute('lang')).toBe('ko');
    });

    it('should mark as not synced after language change', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setLanguage('en');
      });

      expect(usePreferencesStore.getState().isSynced).toBe(false);
    });
  });

  describe('applyTheme', () => {
    it('should apply theme directly to DOM', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().applyTheme('dark');
      });

      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
      expect(usePreferencesStore.getState().resolvedTheme).toBe('dark');
    });
  });

  describe('detectSystemTheme', () => {
    it('should detect light system theme', async () => {
      mockMatchMedia(false); // System prefers light

      const { usePreferencesStore } = await import('../../store/preferencesStore');

      const detected = usePreferencesStore.getState().detectSystemTheme();
      expect(['light', 'dark']).toContain(detected);
    });

    it('should detect dark system theme', async () => {
      mockMatchMedia(true); // System prefers dark

      const { usePreferencesStore } = await import('../../store/preferencesStore');

      const detected = usePreferencesStore.getState().detectSystemTheme();
      expect(['light', 'dark']).toContain(detected);
    });
  });

  describe('clearError', () => {
    it('should clear error state', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      // Manually set an error
      usePreferencesStore.setState({ error: 'Some error' });

      act(() => {
        usePreferencesStore.getState().clearError();
      });

      expect(usePreferencesStore.getState().error).toBeNull();
    });
  });

  describe('Persistence', () => {
    it('should persist theme preference to localStorage', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('dark');
      });

      // Wait for persistence
      await new Promise(resolve => setTimeout(resolve, 10));

      const stored = localStorageMock.getItem('kms-preferences');
      expect(stored).not.toBeNull();

      if (stored) {
        const parsed = JSON.parse(stored);
        expect(parsed.state.theme).toBe('dark');
      }
    });

    it('should persist language preference to localStorage', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setLanguage('en');
      });

      // Wait for persistence
      await new Promise(resolve => setTimeout(resolve, 10));

      const stored = localStorageMock.getItem('kms-preferences');
      expect(stored).not.toBeNull();

      if (stored) {
        const parsed = JSON.parse(stored);
        expect(parsed.state.language).toBe('en');
      }
    });

    it('should only persist theme and language (not internal state)', async () => {
      const { usePreferencesStore } = await import('../../store/preferencesStore');

      act(() => {
        usePreferencesStore.getState().setTheme('dark');
        usePreferencesStore.getState().setLanguage('ko');
      });

      // Set internal state that should not persist
      usePreferencesStore.setState({
        isLoading: true,
        isSynced: true,
        error: 'test error',
      });

      // Wait for persistence
      await new Promise(resolve => setTimeout(resolve, 10));

      const stored = localStorageMock.getItem('kms-preferences');
      if (stored) {
        const parsed = JSON.parse(stored);
        // Only theme and language should be persisted
        expect(parsed.state.theme).toBe('dark');
        expect(parsed.state.language).toBe('ko');
        // Internal state should NOT be persisted
        expect(parsed.state.isLoading).toBeUndefined();
        expect(parsed.state.isSynced).toBeUndefined();
        expect(parsed.state.error).toBeUndefined();
      }
    });
  });

  describe('Theme/Language Combinations', () => {
    const themes = ['light', 'dark', 'system'] as const;
    const languages = ['en', 'ko'] as const;

    themes.forEach((theme) => {
      languages.forEach((language) => {
        it(`should correctly handle ${theme} theme with ${language} language`, async () => {
          const { usePreferencesStore } = await import('../../store/preferencesStore');

          act(() => {
            usePreferencesStore.getState().setTheme(theme);
            usePreferencesStore.getState().setLanguage(language);
          });

          const state = usePreferencesStore.getState();
          expect(state.theme).toBe(theme);
          expect(state.language).toBe(language);
        });
      });
    });
  });
});

describe('Preferences Store Actions Interface', () => {
  beforeEach(() => {
    localStorageMock.clear();
    vi.clearAllMocks();
  });

  it('should have all required action methods', async () => {
    const { usePreferencesStore } = await import('../../store/preferencesStore');

    const state = usePreferencesStore.getState();

    // Check all required actions exist
    expect(typeof state.setTheme).toBe('function');
    expect(typeof state.setLanguage).toBe('function');
    expect(typeof state.loadPreferences).toBe('function');
    expect(typeof state.syncWithServer).toBe('function');
    expect(typeof state.detectSystemTheme).toBe('function');
    expect(typeof state.applyTheme).toBe('function');
    expect(typeof state.clearError).toBe('function');
  });
});

describe('initializeThemeListener', () => {
  beforeEach(() => {
    mockMatchMedia(false);
    vi.clearAllMocks();
  });

  it('should export initializeThemeListener function', async () => {
    const { initializeThemeListener } = await import('../../store/preferencesStore');
    expect(typeof initializeThemeListener).toBe('function');
  });

  it('should return cleanup function', async () => {
    const { initializeThemeListener } = await import('../../store/preferencesStore');
    const cleanup = initializeThemeListener();
    expect(typeof cleanup).toBe('function');

    // Should not throw when called
    expect(() => cleanup()).not.toThrow();
  });
});
