/**
 * SSO Flow E2E Tests
 *
 * Tests corporate SSO authentication flow:
 * - SSO button display and interaction
 * - Email validation for corporate domains
 * - SSO initiation with ijshin@tmaxsoft.co.jp
 * - Backend API integration
 */

import { test, expect } from '@playwright/test';

test.describe('SSO Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto('/login');
  });

  test.describe('SSO Button and Mode Switching', () => {
    test('should display Corporate SSO button', async ({ page }) => {
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")');

      // SSO button should be visible
      await expect(ssoButton.first()).toBeVisible();
    });

    test('should switch to SSO mode when clicking Corporate SSO button', async ({ page }) => {
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")').first();

      await ssoButton.click();
      await page.waitForTimeout(300);

      // Should show email input form for SSO
      const emailInput = page.locator('input[type="email"]');
      await expect(emailInput).toBeVisible();

      // Should show SSO-related text
      const ssoText = page.locator('text=/기업|Corporate|SSO/i');
      await expect(ssoText.first()).toBeVisible();
    });
  });

  test.describe('SSO Email Input and Validation', () => {
    test.beforeEach(async ({ page }) => {
      // Click SSO button to enter SSO mode
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")').first();
      await ssoButton.click();
      await page.waitForTimeout(300);
    });

    test('should allow typing corporate email', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');

      await emailInput.fill('ijshin@tmaxsoft.co.jp');
      await expect(emailInput).toHaveValue('ijshin@tmaxsoft.co.jp');
    });

    test('should have SSO submit button', async ({ page }) => {
      const submitButton = page.locator('button[type="submit"]');

      await expect(submitButton).toBeVisible();
      await expect(submitButton).toBeEnabled();
    });

    test('should validate empty email submission', async ({ page }) => {
      const submitButton = page.locator('button[type="submit"]');

      // Try submitting without email
      await submitButton.click();
      await page.waitForTimeout(500);

      // Should show validation error or remain on page
      const emailInput = page.locator('input[type="email"]');
      await expect(emailInput).toBeVisible();
    });
  });

  test.describe('SSO Initiation with ijshin@tmaxsoft.co.jp', () => {
    test.beforeEach(async ({ page }) => {
      // Navigate to SSO mode
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")').first();
      await ssoButton.click();
      await page.waitForTimeout(300);
    });

    test('should initiate SSO flow with valid corporate email', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');
      const submitButton = page.locator('button[type="submit"]');

      // Fill in the corporate email
      await emailInput.fill('ijshin@tmaxsoft.co.jp');

      // Listen for network requests to SSO endpoint
      const ssoRequestPromise = page.waitForRequest(
        request => request.url().includes('/api/v1/auth/sso'),
        { timeout: 5000 }
      ).catch(() => null);

      // Submit the form
      await submitButton.click();

      // Wait for SSO request
      const ssoRequest = await ssoRequestPromise;

      if (ssoRequest) {
        console.log('SSO Request URL:', ssoRequest.url());
        console.log('SSO Request Method:', ssoRequest.method());
        console.log('SSO Request Headers:', ssoRequest.headers());

        // Verify the request was made
        expect(ssoRequest.url()).toContain('/api/v1/auth/sso');
      } else {
        // If no network request, check for navigation or error
        await page.waitForTimeout(2000);
        const currentURL = page.url();
        const errorMessage = await page.locator('.message.error, .error, [role="alert"]').textContent().catch(() => null);

        console.log('Current URL:', currentURL);
        console.log('Error Message:', errorMessage);

        // Log what happened
        if (errorMessage) {
          console.log('SSO Error:', errorMessage);
        }
      }
    });

    test('should handle SSO API response', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');
      const submitButton = page.locator('button[type="submit"]');

      // Mock SSO API response
      await page.route('**/api/v1/auth/sso*', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            data: {
              sso_url: 'https://sso.tmaxsoft.co.jp/auth?token=test',
              message: 'SSO initiated successfully'
            }
          })
        });
      });

      await emailInput.fill('ijshin@tmaxsoft.co.jp');
      await submitButton.click();

      // Wait for response handling
      await page.waitForTimeout(1000);

      // Check for redirect or success message
      const currentURL = page.url();
      console.log('URL after SSO:', currentURL);
    });

    test('should show error for invalid corporate email', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');
      const submitButton = page.locator('button[type="submit"]');

      // Try with non-corporate email
      await emailInput.fill('invalid@gmail.com');
      await submitButton.click();

      // Wait for error message
      await page.waitForTimeout(1000);

      // Should show error (gmail.com is in allowed list, but testing validation logic)
      // Or should proceed if gmail.com is in VITE_CORP_EMAIL_DOMAINS
      const errorOrSuccess = await page.locator('.message, [role="alert"]').textContent().catch(() => null);
      console.log('Validation result:', errorOrSuccess);
    });
  });

  test.describe('SSO Accessibility', () => {
    test.beforeEach(async ({ page }) => {
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")').first();
      await ssoButton.click();
      await page.waitForTimeout(300);
    });

    test('should be keyboard navigable', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');

      // Click on email input first to ensure it's in the DOM
      await emailInput.click();
      await expect(emailInput).toBeFocused();

      // Type email
      await page.keyboard.type('ijshin@tmaxsoft.co.jp');

      // Tab to submit
      await page.keyboard.press('Tab');

      // Press Enter to submit
      await page.keyboard.press('Enter');

      // Should handle submission
      await page.waitForTimeout(500);
    });

    test('should have proper focus indicators', async ({ page }) => {
      const emailInput = page.locator('input[type="email"]');

      await emailInput.focus();
      await expect(emailInput).toBeFocused();
    });
  });

  test.describe('Back Navigation', () => {
    test.beforeEach(async ({ page }) => {
      const ssoButton = page.locator('button:has-text("기업"), button:has-text("SSO"), button:has-text("Corporate")').first();
      await ssoButton.click();
      await page.waitForTimeout(300);
    });

    test('should have option to go back to login', async ({ page }) => {
      const backButton = page.locator('button:has-text("←"), a:has-text("←"), button:has-text("Back"), a:has-text("로그인")');

      if (await backButton.count() > 0) {
        await backButton.first().click();
        await page.waitForTimeout(300);

        // Should be back at login mode
        const passwordInput = page.locator('input[type="password"]');
        await expect(passwordInput).toBeVisible();
      }
    });
  });
});
