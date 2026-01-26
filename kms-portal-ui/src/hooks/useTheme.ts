/**
 * useTheme Hook
 *
 * Custom hook for theme management:
 * - Access current theme state
 * - Toggle between themes
 * - Detect system preference changes
 */
import { useEffect, useCallback } from 'react';
import {
  usePreferencesStore,
  initializeThemeListener,
  Theme,
  ResolvedTheme,
} from '../store/preferencesStore';

interface UseThemeReturn {
  /** Current theme setting ('light' | 'dark' | 'system') */
  theme: Theme;
  /** Resolved theme (actual applied theme: 'light' | 'dark') */
  resolvedTheme: ResolvedTheme;
  /** Set theme preference */
  setTheme: (theme: Theme) => void;
  /** Toggle between light and dark */
  toggleTheme: () => void;
  /** Cycle through all themes (light -> dark -> system -> light) */
  cycleTheme: () => void;
  /** Is current resolved theme dark? */
  isDark: boolean;
  /** Is current resolved theme light? */
  isLight: boolean;
  /** Is theme set to follow system? */
  isSystem: boolean;
}

/**
 * Hook for theme management
 */
export const useTheme = (): UseThemeReturn => {
  const { theme, resolvedTheme, setTheme } = usePreferencesStore();

  // Set up system theme listener on mount
  useEffect(() => {
    const cleanup = initializeThemeListener();
    return cleanup;
  }, []);

  /**
   * Toggle between light and dark
   * If currently on system, switches to opposite of resolved theme
   */
  const toggleTheme = useCallback(() => {
    if (theme === 'system') {
      // Switch to opposite of current resolved theme
      setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
    } else {
      // Toggle between light and dark
      setTheme(theme === 'dark' ? 'light' : 'dark');
    }
  }, [theme, resolvedTheme, setTheme]);

  /**
   * Cycle through themes: light -> dark -> system -> light
   */
  const cycleTheme = useCallback(() => {
    const themeOrder: Theme[] = ['light', 'dark', 'system'];
    const currentIndex = themeOrder.indexOf(theme);
    const nextIndex = (currentIndex + 1) % themeOrder.length;
    setTheme(themeOrder[nextIndex]);
  }, [theme, setTheme]);

  return {
    theme,
    resolvedTheme,
    setTheme,
    toggleTheme,
    cycleTheme,
    isDark: resolvedTheme === 'dark',
    isLight: resolvedTheme === 'light',
    isSystem: theme === 'system',
  };
};

export default useTheme;
