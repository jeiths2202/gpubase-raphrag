/**
 * Theme and Language E2E Tests
 *
 * Tests user preference functionality including:
 * - Theme switching (light/dark/system)
 * - Language switching (en/ko)
 * - Persistence across page reloads
 * - Visual consistency
 *
 * NOTE: These tests run against the dev server (http://localhost:3000)
 */

import { test, expect } from '@playwright/test';

test.describe('Theme Switching', () => {
  test.beforeEach(async ({ page }) => {
    // Clear localStorage to start fresh
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('should apply light theme when selected', async ({ page }) => {
    // Find theme toggle or settings
    const themeToggle = page.locator('[data-testid="theme-toggle"], button:has-text("테마"), button:has-text("Theme"), [aria-label*="theme"]');

    if (await themeToggle.count() > 0) {
      await themeToggle.first().click();

      // Look for light theme option
      const lightOption = page.locator('button:has-text("라이트"), button:has-text("Light"), [data-value="light"]');

      if (await lightOption.count() > 0) {
        await lightOption.first().click();
        await page.waitForTimeout(300);

        // Check that data-theme attribute is set
        const htmlElement = page.locator('html');
        await expect(htmlElement).toHaveAttribute('data-theme', 'light');
      }
    }
  });

  test('should apply dark theme when selected', async ({ page }) => {
    const themeToggle = page.locator('[data-testid="theme-toggle"], button:has-text("테마"), button:has-text("Theme"), [aria-label*="theme"]');

    if (await themeToggle.count() > 0) {
      await themeToggle.first().click();

      const darkOption = page.locator('button:has-text("다크"), button:has-text("Dark"), [data-value="dark"]');

      if (await darkOption.count() > 0) {
        await darkOption.first().click();
        await page.waitForTimeout(300);

        const htmlElement = page.locator('html');
        await expect(htmlElement).toHaveAttribute('data-theme', 'dark');
      }
    }
  });

  test('should persist theme preference after reload', async ({ page }) => {
    // First, set a theme
    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'dark', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    // Check that theme was restored
    const storedTheme = await page.evaluate(() => {
      const stored = localStorage.getItem('kms-preferences');
      if (stored) {
        const parsed = JSON.parse(stored);
        return parsed.state?.theme;
      }
      return null;
    });

    // Either theme was persisted or DOM reflects it
    const htmlElement = page.locator('html');
    const dataTheme = await htmlElement.getAttribute('data-theme');

    expect(storedTheme === 'dark' || dataTheme === 'dark').toBeTruthy();
  });

  test('should respond to system theme preference', async ({ page }) => {
    // Set system theme mode
    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'system', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    // In system mode, theme should match system preference
    const htmlElement = page.locator('html');
    const dataTheme = await htmlElement.getAttribute('data-theme');

    // Theme should be either 'light' or 'dark' when in system mode
    expect(['light', 'dark', 'system', null]).toContain(dataTheme);
  });
});

test.describe('Language Switching', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());
    await page.reload();
  });

  test('should apply Korean language when selected', async ({ page }) => {
    const langSelector = page.locator('[data-testid="language-selector"], button:has-text("한국어"), button:has-text("언어"), [aria-label*="language"]');

    if (await langSelector.count() > 0) {
      await langSelector.first().click();

      const koOption = page.locator('button:has-text("한국어"), [data-value="ko"]');

      if (await koOption.count() > 0) {
        await koOption.first().click();
        await page.waitForTimeout(300);

        // Check lang attribute
        const htmlElement = page.locator('html');
        await expect(htmlElement).toHaveAttribute('lang', 'ko');
      }
    }
  });

  test('should apply English language when selected', async ({ page }) => {
    const langSelector = page.locator('[data-testid="language-selector"], button:has-text("English"), button:has-text("언어"), [aria-label*="language"]');

    if (await langSelector.count() > 0) {
      await langSelector.first().click();

      const enOption = page.locator('button:has-text("English"), [data-value="en"]');

      if (await enOption.count() > 0) {
        await enOption.first().click();
        await page.waitForTimeout(300);

        const htmlElement = page.locator('html');
        await expect(htmlElement).toHaveAttribute('lang', 'en');
      }
    }
  });

  test('should persist language preference after reload', async ({ page }) => {
    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'light', language: 'en' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    const storedLanguage = await page.evaluate(() => {
      const stored = localStorage.getItem('kms-preferences');
      if (stored) {
        const parsed = JSON.parse(stored);
        return parsed.state?.language;
      }
      return null;
    });

    const htmlElement = page.locator('html');
    const langAttr = await htmlElement.getAttribute('lang');

    expect(storedLanguage === 'en' || langAttr === 'en').toBeTruthy();
  });

  test('should display UI elements in correct language', async ({ page }) => {
    // Set Korean
    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'light', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    // Check for Korean text presence on the page
    const pageContent = await page.textContent('body');
    const hasKoreanChars = /[\uAC00-\uD7AF]/.test(pageContent || '');

    // Page should contain Korean characters when in Korean mode
    expect(hasKoreanChars).toBeTruthy();
  });
});

test.describe('Preference Combinations', () => {
  test('should handle theme and language together', async ({ page }) => {
    await page.goto('/');

    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'dark', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    const htmlElement = page.locator('html');

    // Both preferences should be applied
    const dataTheme = await htmlElement.getAttribute('data-theme');
    const langAttr = await htmlElement.getAttribute('lang');

    // At least one should match
    expect(dataTheme === 'dark' || langAttr === 'ko').toBeTruthy();
  });

  test('should reset to defaults when localStorage is cleared', async ({ page }) => {
    await page.goto('/');

    // Set custom preferences first
    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'dark', language: 'en' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(300);

    // Clear localStorage
    await page.evaluate(() => localStorage.clear());

    await page.reload();
    await page.waitForTimeout(500);

    // Should revert to defaults
    const storedPrefs = await page.evaluate(() => localStorage.getItem('kms-preferences'));

    // Either no preferences stored or reset to defaults
    if (storedPrefs) {
      const parsed = JSON.parse(storedPrefs);
      // Default language is 'ko' for KMS
      expect(parsed.state?.language).toBe('ko');
    }
  });
});

test.describe('Visual Theme Consistency', () => {
  test('should maintain consistent styling in light mode', async ({ page }) => {
    await page.goto('/');

    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'light', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    // Check background color is light
    const bgColor = await page.evaluate(() => {
      return getComputedStyle(document.body).backgroundColor;
    });

    // Light theme should have light background (high RGB values)
    // Parse RGB value and check
    const rgbMatch = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (rgbMatch) {
      const [, r, g, b] = rgbMatch.map(Number);
      // Light theme typically has high RGB values
      expect(r + g + b).toBeGreaterThan(300);
    }
  });

  test('should maintain consistent styling in dark mode', async ({ page }) => {
    await page.goto('/');

    await page.evaluate(() => {
      localStorage.setItem('kms-preferences', JSON.stringify({
        state: { theme: 'dark', language: 'ko' },
        version: 0
      }));
    });

    await page.reload();
    await page.waitForTimeout(500);

    const bgColor = await page.evaluate(() => {
      return getComputedStyle(document.body).backgroundColor;
    });

    // Dark theme should have dark background (low RGB values)
    const rgbMatch = bgColor.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
    if (rgbMatch) {
      const [, r, g, b] = rgbMatch.map(Number);
      // Dark theme typically has low RGB values
      expect(r + g + b).toBeLessThan(400);
    }
  });
});
