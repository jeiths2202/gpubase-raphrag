/**
 * User Preferences Store
 *
 * Manages user preferences for theme and language:
 * - Persists to localStorage for immediate access
 * - Syncs with server for cross-device persistence
 * - Supports system theme detection
 * - No sensitive data stored
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { API_BASE_URL } from '../config/constants';

// Theme types
export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';
export type Language = 'en' | 'ko' | 'ja';

interface PreferencesState {
  // State
  theme: Theme;
  language: Language;
  resolvedTheme: ResolvedTheme;
  isLoading: boolean;
  isSynced: boolean;
  error: string | null;

  // Actions
  setTheme: (theme: Theme) => void;
  setLanguage: (language: Language) => void;
  loadPreferences: () => Promise<void>;
  syncWithServer: () => Promise<void>;
  detectSystemTheme: () => ResolvedTheme;
  applyTheme: (theme: ResolvedTheme) => void;
  clearError: () => void;
}

/**
 * Detect system theme preference
 */
const detectSystemTheme = (): ResolvedTheme => {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }
  return 'dark'; // Default to dark
};

/**
 * Apply theme to DOM
 */
const applyThemeToDOM = (theme: ResolvedTheme): void => {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', theme);
    // Update meta theme-color for mobile browsers
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute(
        'content',
        theme === 'dark' ? '#0f172a' : '#ffffff'
      );
    }
  }
};

/**
 * Apply language to DOM
 */
const applyLanguageToDOM = (language: Language): void => {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', language);
  }
};

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set, get) => ({
      // Initial state
      theme: 'system',
      language: 'ko', // Default to Korean for this KMS
      resolvedTheme: detectSystemTheme(),
      isLoading: false,
      isSynced: false,
      error: null,

      detectSystemTheme,

      applyTheme: (theme: ResolvedTheme) => {
        applyThemeToDOM(theme);
        set({ resolvedTheme: theme });
      },

      setTheme: (theme: Theme) => {
        const resolvedTheme = theme === 'system'
          ? detectSystemTheme()
          : theme;

        // Apply immediately to DOM
        applyThemeToDOM(resolvedTheme);

        // Update state
        set({ theme, resolvedTheme, isSynced: false });

        // Sync with server (non-blocking)
        get().syncWithServer();
      },

      setLanguage: (language: Language) => {
        // Apply immediately to DOM
        applyLanguageToDOM(language);

        // Update state
        set({ language, isSynced: false });

        // Sync with server (non-blocking)
        get().syncWithServer();
      },

      loadPreferences: async () => {
        set({ isLoading: true, error: null });

        // Get current local preferences (from localStorage via zustand persist)
        const localTheme = get().theme;
        const localLanguage = get().language;

        try {
          // First, sync local preferences to server
          // This ensures the language selected on login page is preserved
          await fetch(`${API_BASE_URL}/preferences`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              theme: localTheme,
              language: localLanguage
            }),
          });

          // Apply local preferences to DOM (user's selection takes priority)
          const resolvedTheme = localTheme === 'system'
            ? detectSystemTheme()
            : localTheme as ResolvedTheme;

          applyThemeToDOM(resolvedTheme);
          applyLanguageToDOM(localLanguage);

          // Update state
          set({
            theme: localTheme,
            language: localLanguage,
            resolvedTheme,
            isLoading: false,
            isSynced: true,
          });
        } catch {
          // Server unavailable - use local preferences
          const resolvedTheme = localTheme === 'system'
            ? detectSystemTheme()
            : localTheme as ResolvedTheme;

          // Apply local preferences to DOM
          applyThemeToDOM(resolvedTheme);
          applyLanguageToDOM(localLanguage);

          set({
            resolvedTheme,
            isLoading: false,
            isSynced: false,
          });
        }
      },

      syncWithServer: async () => {
        const { theme, language } = get();

        try {
          await fetch(`${API_BASE_URL}/preferences`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ theme, language }),
          });
          set({ isSynced: true, error: null });
        } catch {
          // Silently fail - preferences still work locally
          set({ isSynced: false });
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'kms-preferences',
      // Only persist theme and language
      partialize: (state) => ({
        theme: state.theme,
        language: state.language,
      }),
      // On rehydrate, apply stored preferences to DOM
      onRehydrateStorage: () => (state) => {
        if (state) {
          const resolvedTheme = state.theme === 'system'
            ? detectSystemTheme()
            : state.theme as ResolvedTheme;

          applyThemeToDOM(resolvedTheme);
          applyLanguageToDOM(state.language);
        }
      },
    }
  )
);

/**
 * Initialize system theme listener
 * Call this in App.tsx on mount
 */
export const initializeThemeListener = (): (() => void) => {
  if (typeof window === 'undefined' || !window.matchMedia) {
    return () => {};
  }

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  const handleChange = (e: MediaQueryListEvent) => {
    const { theme, applyTheme } = usePreferencesStore.getState();

    // Only react if theme is set to 'system'
    if (theme === 'system') {
      const newTheme = e.matches ? 'dark' : 'light';
      applyTheme(newTheme);
    }
  };

  mediaQuery.addEventListener('change', handleChange);

  // Return cleanup function
  return () => {
    mediaQuery.removeEventListener('change', handleChange);
  };
};
