import { test, expect } from '@playwright/test';

test.describe('Login Page Test', () => {
  test('should display login page with all elements', async ({ page }) => {
    // Enable all console logging
    page.on('console', msg => {
      console.log('CONSOLE:', msg.type(), msg.text());
    });
    page.on('pageerror', err => console.log('PAGE ERROR:', err.message));

    console.log('=== Login Page Test ===');

    // Navigate to login page
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Take screenshot
    await page.screenshot({ path: 'e2e/screenshots/login-page.png', fullPage: true });

    // Check for KMS title
    const title = page.locator('h1');
    await expect(title).toBeVisible();
    console.log('Title visible:', await title.textContent());

    // Check for login form elements
    const userIdInput = page.locator('#userId');
    const passwordInput = page.locator('#password');
    const submitButton = page.locator('button[type="submit"]');

    await expect(userIdInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitButton).toBeVisible();

    console.log('All form elements visible');

    // Fill credentials with real admin account
    await userIdInput.fill('admin@example.com');
    await passwordInput.fill('SecureAdm1nP@ss2024!');

    console.log('Credentials filled');
    await page.screenshot({ path: 'e2e/screenshots/login-filled.png', fullPage: true });

    // Click login button
    await submitButton.click();
    console.log('Login button clicked');

    // Wait for response
    await page.waitForTimeout(5000);

    // Take screenshot after login attempt
    await page.screenshot({ path: 'e2e/screenshots/login-after.png', fullPage: true });

    const currentUrl = page.url();
    console.log('Current URL after login:', currentUrl);

    // Check if we're still on login page (login failed) or navigated away (login success)
    if (currentUrl.includes('/login')) {
      console.log('Still on login page - checking for error message or mock login');

      // Check for error message
      const errorMessage = page.locator('.message.error');
      const hasError = await errorMessage.isVisible().catch(() => false);
      if (hasError) {
        console.log('Error message:', await errorMessage.textContent());
      }
    } else {
      console.log('Login successful - navigated to:', currentUrl);
    }

    console.log('=== Test Complete ===');
  });
});
