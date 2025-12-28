import { test, expect } from '@playwright/test';

test.describe('Complete SSO Flow', () => {
  // Reset auth state before each test
  test.beforeEach(async ({ page }) => {
    // Clear cookies and local storage to ensure clean state
    await page.context().clearCookies();
    await page.goto('http://localhost:3000');
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test('should complete SSO login flow from start to dashboard', async ({ page }) => {
    // Step 1: Go to login page
    await page.goto('http://localhost:3000/login');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Step 2: Switch to SSO mode
    const ssoButton = page.locator('button:has-text("Corporate SSO"), button:has-text("회사 SSO")');
    await expect(ssoButton).toBeVisible({ timeout: 10000 });
    await ssoButton.click();

    // Wait for SSO mode to activate
    await page.waitForTimeout(500);

    // Step 3: Enter corporate email
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
    await emailInput.fill('ijshin@tmaxsoft.co.jp');

    // Step 4: Click SSO login button
    const ssoLoginButton = page.locator('button[type="submit"]:has-text("SSO")');
    await expect(ssoLoginButton).toBeVisible();
    await ssoLoginButton.click();

    // Step 5: Wait for redirect to SSO callback page
    // The page should redirect to /auth/sso/callback?token=...
    await page.waitForURL(url => url.pathname === '/auth/sso/callback', { timeout: 10000 });

    console.log('Redirected to callback page:', page.url());

    // Step 6: Wait for callback processing and redirect to dashboard
    // The callback page should process the token and redirect to dashboard
    await page.waitForURL(url => url.pathname === '/dashboard' || url.pathname === '/', { timeout: 10000 });

    console.log('Final URL:', page.url());

    // Step 7: Verify we're on the dashboard
    await expect(page).toHaveURL(/\/(dashboard)?$/);

    // Step 8: Verify user is authenticated
    // Check for user-specific elements (logout button, username, etc.)
    const logoutButton = page.locator('button:has-text("Logout"), button:has-text("로그아웃")');
    await expect(logoutButton).toBeVisible({ timeout: 5000 });

    // Step 9: Verify user info is displayed
    const username = page.locator('text=ijshin').first();
    await expect(username).toBeVisible({ timeout: 5000 });

    console.log('SSO login flow completed successfully!');
  });

  test('should handle SSO callback with invalid token', async ({ page }) => {
    // Navigate directly to callback with invalid token
    await page.goto('http://localhost:3000/auth/sso/callback?token=invalid-token-12345');

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Should show error message
    const errorHeading = page.locator('h2:has-text("Authentication Failed")');
    await expect(errorHeading).toBeVisible({ timeout: 10000 });

    // Verify error details are shown
    const errorMessage = page.locator('text=/SSO token|invalid|missing/i');
    await expect(errorMessage).toBeVisible({ timeout: 5000 });

    // Wait for redirect to login (happens after 3 seconds)
    await page.waitForURL(/\/login/, { timeout: 5000 });
  });

  test('should verify SSO token-based authentication works', async ({ page }) => {
    // This test verifies that SSO token authentication flow works correctly with a different user
    // Note: Testing actual token expiration would require waiting 6+ minutes
    // Token expiration logic is covered in backend unit tests

    // Go to login page
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');

    // Switch to SSO mode
    const ssoButton = page.locator('button:has-text("Corporate SSO"), button:has-text("회사 SSO")');
    await expect(ssoButton).toBeVisible({ timeout: 10000 });
    await ssoButton.click();
    await page.waitForTimeout(500);

    // Enter different corporate email (for test independence)
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toBeVisible();
    await emailInput.fill('testuser@tmaxsoft.com');

    // Click SSO login button
    const ssoLoginButton = page.locator('button[type="submit"]:has-text("SSO")');
    await expect(ssoLoginButton).toBeVisible();
    await ssoLoginButton.click();

    // Wait for redirect to callback page
    await page.waitForURL(url => url.pathname === '/auth/sso/callback', { timeout: 10000 });

    console.log('SSO token generated successfully');
    console.log('Redirected to callback page:', page.url());

    // Wait for callback processing and redirect to dashboard
    await page.waitForURL(url => url.pathname === '/dashboard' || url.pathname === '/', { timeout: 10000 });

    console.log('Final URL:', page.url());

    // Verify user is authenticated (logout button visible)
    const logoutButton = page.locator('button:has-text("Logout"), button:has-text("로그아웃")');
    await expect(logoutButton).toBeVisible({ timeout: 5000 });

    console.log('Token-based authentication verified successfully!');
    console.log('Note: Token expiration (5 minutes) is tested in backend unit tests');
  });
});
