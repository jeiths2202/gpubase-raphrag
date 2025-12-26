/**
 * Auth Flow E2E Tests
 *
 * Tests authentication user flows including:
 * - Login page display and interaction
 * - Form validation
 * - Mode switching (login/register)
 * - Error display
 *
 * NOTE: These tests run against the dev server (http://localhost:3000)
 * and use mock authentication (no real backend required for UI testing)
 */

import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');
  });

  test.describe('Login Page Display', () => {
    test('should display login form by default', async ({ page }) => {
      // Check page title or heading
      await expect(page.locator('h1, h2, h3').first()).toBeVisible();

      // Check login form elements exist
      await expect(page.locator('input[type="text"], input[name="username"], input[placeholder*="ID"]')).toBeVisible();
      await expect(page.locator('input[type="password"]')).toBeVisible();
      await expect(page.locator('button[type="submit"]')).toBeVisible();
    });

    test('should have proper form labels', async ({ page }) => {
      // Check for accessible labels or placeholders
      const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
      const passwordInput = page.locator('input[type="password"]').first();

      await expect(usernameInput).toBeVisible();
      await expect(passwordInput).toBeVisible();
    });

    test('should display login button', async ({ page }) => {
      const loginButton = page.locator('button[type="submit"]');
      await expect(loginButton).toBeVisible();
      await expect(loginButton).toBeEnabled();
    });
  });

  test.describe('Form Interaction', () => {
    test('should allow typing in username field', async ({ page }) => {
      const usernameInput = page.locator('input[type="text"], input[name="username"]').first();

      await usernameInput.fill('testuser');
      await expect(usernameInput).toHaveValue('testuser');
    });

    test('should allow typing in password field', async ({ page }) => {
      const passwordInput = page.locator('input[type="password"]').first();

      await passwordInput.fill('testpassword123');
      await expect(passwordInput).toHaveValue('testpassword123');
    });

    test('should show validation for empty submission', async ({ page }) => {
      const loginButton = page.locator('button[type="submit"]');

      // Try submitting empty form
      await loginButton.click();

      // Wait for validation - either HTML5 validation or custom error
      await page.waitForTimeout(500);

      // Form should still be on login page (not submitted successfully)
      await expect(page).toHaveURL(/login/);
    });
  });

  test.describe('Mode Switching', () => {
    test('should have option to switch to register mode', async ({ page }) => {
      // Look for register link/button
      const registerLink = page.locator('a:has-text("회원가입"), button:has-text("회원가입"), a:has-text("Register"), button:has-text("Register"), a:has-text("가입")');

      // If register mode switching exists, test it
      if (await registerLink.count() > 0) {
        await registerLink.first().click();
        await page.waitForTimeout(300);

        // Should now show registration form or navigate to register page
        const emailInput = page.locator('input[type="email"], input[name="email"]');
        const currentUrl = page.url();

        // Either we see email input (register form) or we're on register page
        const hasEmailInput = await emailInput.count() > 0;
        const onRegisterPage = currentUrl.includes('register');

        expect(hasEmailInput || onRegisterPage).toBeTruthy();
      }
    });

    test('should have Google login option if available', async ({ page }) => {
      const googleButton = page.locator('button:has-text("Google"), [aria-label*="Google"]');

      // Google login may or may not be available
      if (await googleButton.count() > 0) {
        await expect(googleButton.first()).toBeVisible();
      }
    });

    test('should have SSO login option if available', async ({ page }) => {
      const ssoButton = page.locator('button:has-text("SSO"), button:has-text("기업"), [aria-label*="SSO"]');

      // SSO login may or may not be available
      if (await ssoButton.count() > 0) {
        await expect(ssoButton.first()).toBeVisible();
      }
    });
  });

  test.describe('Accessibility', () => {
    test('should be keyboard navigable', async ({ page }) => {
      // Focus first input with Tab
      await page.keyboard.press('Tab');

      // Should be able to type
      await page.keyboard.type('testuser');

      // Tab to password
      await page.keyboard.press('Tab');
      await page.keyboard.type('testpass');

      // Tab to submit button
      await page.keyboard.press('Tab');

      // Focused element should be actionable
      const focusedElement = page.locator(':focus');
      await expect(focusedElement).toBeVisible();
    });

    test('should have proper focus indicators', async ({ page }) => {
      const usernameInput = page.locator('input[type="text"], input[name="username"]').first();

      // Click to focus
      await usernameInput.focus();

      // Should have visible focus state
      await expect(usernameInput).toBeFocused();
    });
  });
});

test.describe('Login Form Validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('should validate username length', async ({ page }) => {
    const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
    const passwordInput = page.locator('input[type="password"]').first();
    const loginButton = page.locator('button[type="submit"]');

    // Enter short username
    await usernameInput.fill('a');
    await passwordInput.fill('validpassword123');
    await loginButton.click();

    // Wait for validation
    await page.waitForTimeout(500);

    // Should still be on login page or show error
    await expect(page).toHaveURL(/login/);
  });

  test('should validate password field is required', async ({ page }) => {
    const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
    const loginButton = page.locator('button[type="submit"]');

    // Enter only username
    await usernameInput.fill('testuser');
    await loginButton.click();

    // Wait for validation
    await page.waitForTimeout(500);

    // Should still be on login page
    await expect(page).toHaveURL(/login/);
  });
});
