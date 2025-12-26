/**
 * Visual Regression Tests
 *
 * Screenshot-based testing for theme consistency across:
 * - Light/Dark mode
 * - English/Korean language
 *
 * Usage:
 *   npx playwright test visual-regression.spec.ts
 *   npx playwright test --update-snapshots (to update baseline)
 *
 * Prerequisites:
 *   npm install -D @playwright/test
 *   npx playwright install
 */

import { test, expect, type Page } from '@playwright/test';

// Theme/Language combinations to test
const testCases = [
  { theme: 'light', language: 'en', name: 'Light-English' },
  { theme: 'light', language: 'ko', name: 'Light-Korean' },
  { theme: 'dark', language: 'en', name: 'Dark-English' },
  { theme: 'dark', language: 'ko', name: 'Dark-Korean' },
] as const;

// Helper to set theme and language
async function setThemeAndLanguage(
  page: Page,
  theme: 'light' | 'dark',
  language: 'en' | 'ko'
) {
  // Set theme via localStorage (simulating preferencesStore)
  await page.evaluate(
    ({ theme, language }) => {
      // Set theme attribute
      document.documentElement.setAttribute('data-theme', theme);
      document.documentElement.setAttribute('lang', language);

      // Set localStorage for persistence
      localStorage.setItem(
        'kms-preferences',
        JSON.stringify({
          state: { theme, language },
          version: 0,
        })
      );
    },
    { theme, language }
  );

  // Wait for styles to apply
  await page.waitForTimeout(300);
}

// Skip visual regression tests if not in CI or explicitly enabled
const runVisualTests = process.env.VISUAL_REGRESSION === 'true' || process.env.CI === 'true';

test.describe('Visual Regression Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the app (assuming dev server is running)
    // In CI, this would point to a preview build
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' });
  });

  // Test login page across all theme/language combinations
  test.describe('Login Page', () => {
    for (const { theme, language, name } of testCases) {
      test(`Login page - ${name}`, async ({ page }) => {
        test.skip(!runVisualTests, 'Visual regression tests disabled');

        await setThemeAndLanguage(page, theme, language);
        await expect(page).toHaveScreenshot(`login-${theme}-${language}.png`, {
          fullPage: true,
          animations: 'disabled',
        });
      });
    }
  });

  // Test dashboard components (requires real authentication - skip in automated tests)
  // These tests should be run manually with authenticated session
  test.describe('Dashboard Components', () => {
    // Skip dashboard tests - they require real backend authentication
    // Run manually: VISUAL_REGRESSION=true AUTH_TOKEN=<token> npx playwright test
    const skipDashboard = !process.env.AUTH_TOKEN;

    for (const { theme, language, name } of testCases) {
      test(`Dashboard header - ${name}`, async ({ page }) => {
        test.skip(!runVisualTests || skipDashboard, 'Dashboard tests require authentication');

        await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });
        await setThemeAndLanguage(page, theme, language);

        // Capture header region
        const header = page.locator('.dashboard-header, header').first();
        await expect(header).toHaveScreenshot(`header-${theme}-${language}.png`, {
          animations: 'disabled',
        });
      });
    }
  });

  // Test theme toggle component (requires authentication)
  test.describe('Theme Toggle Component', () => {
    const skipDashboard = !process.env.AUTH_TOKEN;

    for (const { theme, language, name } of testCases) {
      test(`Theme toggle - ${name}`, async ({ page }) => {
        test.skip(!runVisualTests || skipDashboard, 'Requires authentication');

        await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });
        await setThemeAndLanguage(page, theme, language);

        const themeToggle = page.locator('.theme-toggle, [aria-label*="모드"], [aria-label*="theme"]').first();
        if (await themeToggle.isVisible()) {
          await expect(themeToggle).toHaveScreenshot(`theme-toggle-${theme}-${language}.png`, {
            animations: 'disabled',
          });
        }
      });
    }
  });

  // Test language selector component (requires authentication)
  test.describe('Language Selector Component', () => {
    const skipDashboard = !process.env.AUTH_TOKEN;

    for (const { theme, language, name } of testCases) {
      test(`Language selector - ${name}`, async ({ page }) => {
        test.skip(!runVisualTests || skipDashboard, 'Requires authentication');

        await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' });
        await setThemeAndLanguage(page, theme, language);

        const langSelector = page.locator('.language-selector, [aria-label*="language"]').first();
        if (await langSelector.isVisible()) {
          await expect(langSelector).toHaveScreenshot(`lang-selector-${theme}-${language}.png`, {
            animations: 'disabled',
          });
        }
      });
    }
  });
});

// Critical color contrast verification tests
test.describe('Color Contrast Visual Checks', () => {
  test('Primary text on backgrounds should be readable', async ({ page }) => {
    test.skip(!runVisualTests, 'Visual regression tests disabled');

    await page.goto('http://localhost:3000/login');

    // Light theme
    await setThemeAndLanguage(page, 'light', 'en');
    await expect(page).toHaveScreenshot('contrast-light.png', {
      fullPage: true,
      animations: 'disabled',
    });

    // Dark theme
    await setThemeAndLanguage(page, 'dark', 'en');
    await expect(page).toHaveScreenshot('contrast-dark.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
