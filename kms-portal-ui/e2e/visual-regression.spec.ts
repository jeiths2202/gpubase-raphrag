/**
 * Visual Regression Tests
 *
 * Screenshot comparison tests for UI consistency.
 * Uses Playwright's toMatchSnapshot for visual regression.
 */

import { test, expect } from '@playwright/test';

test.describe('Visual Regression - Login Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    // Wait for animations to complete
    await page.waitForTimeout(500);
  });

  test('login page - default state', async ({ page }) => {
    await expect(page).toHaveScreenshot('login-default.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - with credentials filled', async ({ page }) => {
    await page.locator('#userId').fill('testuser');
    await page.locator('#password').fill('password123');

    await expect(page).toHaveScreenshot('login-filled.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - registration tab', async ({ page }) => {
    await page.locator('.tab').nth(1).click();
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-register-tab.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - SSO form', async ({ page }) => {
    await page.locator('.btn-sso').click();
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-sso-form.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - error state', async ({ page }) => {
    // Submit empty form to trigger error
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-error-state.png', {
      maxDiffPixelRatio: 0.1,
    });
  });
});

test.describe('Visual Regression - Theme', () => {
  test('login page - light theme', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Ensure light theme
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    });

    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-light-theme.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - dark theme', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Switch to dark theme
    await page.evaluate(() => {
      document.documentElement.classList.remove('light');
      document.documentElement.classList.add('dark');
    });

    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-dark-theme.png', {
      maxDiffPixelRatio: 0.1,
    });
  });
});

test.describe('Visual Regression - Responsive', () => {
  test('login page - mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-mobile.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-tablet.png', {
      maxDiffPixelRatio: 0.1,
    });
  });

  test('login page - desktop viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot('login-desktop.png', {
      maxDiffPixelRatio: 0.1,
    });
  });
});
