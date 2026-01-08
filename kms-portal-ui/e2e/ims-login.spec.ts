import { test, expect } from '@playwright/test';

test.describe('IMS Login and Navigation Test', () => {
  test('should login and navigate to IMS page', async ({ page }) => {
    // Enable console logging
    page.on('console', msg => {
      console.log('CONSOLE:', msg.type(), msg.text());
    });
    page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

    console.log('=== Starting IMS Test ===');

    // Step 1: Navigate to login page
    console.log('Step 1: Navigating to login page...');
    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'e2e/screenshots/01-login-page.png', fullPage: true });

    // Verify login form is visible
    const userIdInput = page.locator('#userId');
    const passwordInput = page.locator('#password');
    const submitButton = page.locator('button[type="submit"]');

    await expect(userIdInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitButton).toBeVisible();
    console.log('Login form elements visible');

    // Step 2: Login with real admin credentials
    console.log('Step 2: Logging in with admin@example.com...');
    await userIdInput.fill('admin@example.com');
    await passwordInput.fill('SecureAdm1nP@ss2024!');
    await page.screenshot({ path: 'e2e/screenshots/02-credentials-filled.png', fullPage: true });

    await submitButton.click();
    console.log('Login button clicked');

    // Wait for login to complete and navigation
    await page.waitForTimeout(3000);
    await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10000 });

    const afterLoginUrl = page.url();
    console.log('After login URL:', afterLoginUrl);
    await page.screenshot({ path: 'e2e/screenshots/03-after-login.png', fullPage: true });

    // Verify login was successful (not on login page)
    expect(afterLoginUrl).not.toContain('/login');
    console.log('Login successful!');

    // Step 3: Navigate to IMS page
    console.log('Step 3: Navigating to IMS page...');
    await page.goto('/ims');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'e2e/screenshots/04-ims-page.png', fullPage: true });

    // Verify we're on IMS page
    const currentUrl = page.url();
    console.log('Current URL:', currentUrl);
    expect(currentUrl).toContain('/ims');

    // Step 4: Check for IMS page elements
    console.log('Step 4: Checking IMS page elements...');

    // Look for search input or credentials modal
    const searchInput = page.locator('input[type="text"]').first();
    const isSearchVisible = await searchInput.isVisible().catch(() => false);
    console.log('Search input visible:', isSearchVisible);

    await page.screenshot({ path: 'e2e/screenshots/05-ims-elements.png', fullPage: true });

    // Step 5: Try to enter search keyword if possible
    if (isSearchVisible) {
      console.log('Step 5: Entering search keyword...');
      await searchInput.fill('oscboot');
      await page.screenshot({ path: 'e2e/screenshots/06-search-keyword.png', fullPage: true });
      console.log('Search keyword entered');
    } else {
      console.log('Step 5: No search input found - credentials modal may be displayed');
    }

    // Final screenshot
    await page.screenshot({ path: 'e2e/screenshots/07-final.png', fullPage: true });

    console.log('=== IMS Test Completed ===');
    console.log('Final URL:', page.url());
  });
});
