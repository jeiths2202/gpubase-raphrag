import { test, expect } from '@playwright/test';

test.describe('Debug Chat UI Issues', () => {
  test('detailed error investigation', async ({ page }) => {
    const consoleMessages: string[] = [];
    const errors: string[] = [];
    const warnings: string[] = [];
    const networkErrors: string[] = [];

    // Capture all console messages
    page.on('console', msg => {
      const text = `[${msg.type()}] ${msg.text()}`;
      consoleMessages.push(text);

      if (msg.type() === 'error') {
        errors.push(msg.text());
      } else if (msg.type() === 'warning') {
        warnings.push(msg.text());
      }
    });

    // Capture page errors
    page.on('pageerror', error => {
      errors.push(`PAGE ERROR: ${error.message}\n${error.stack}`);
    });

    // Capture network failures
    page.on('requestfailed', request => {
      networkErrors.push(`${request.method()} ${request.url()} - ${request.failure()?.errorText}`);
    });

    // Navigate to login page
    await page.goto('http://localhost:3000');
    await page.waitForLoadState('networkidle');

    console.log('=== BEFORE LOGIN ===');
    console.log('Errors:', errors);
    console.log('Network Errors:', networkErrors);

    // Clear arrays before login
    errors.length = 0;
    networkErrors.length = 0;

    // Login
    await page.fill('input[type="text"]', 'edelweise@naver.com');
    await page.fill('input[type="password"]', 'SecureTest123!');
    await page.click('button[type="submit"]');

    // Wait for navigation
    try {
      await page.waitForURL('**/knowledge', { timeout: 15000 });
    } catch (e) {
      console.log('Failed to navigate to /knowledge:', e);
      await page.screenshot({ path: 'navigation-failed.png', fullPage: true });
    }

    // Wait for page to stabilize
    await page.waitForTimeout(5000);

    console.log('=== AFTER LOGIN ===');
    console.log('Current URL:', page.url());
    console.log('Errors:', errors);
    console.log('Warnings:', warnings.slice(0, 5)); // First 5 warnings
    console.log('Network Errors:', networkErrors);

    // Check DOM structure
    const html = await page.content();
    console.log('Page has .knowledge-app:', html.includes('knowledge-app'));
    console.log('Page has .knowledge-main:', html.includes('knowledge-main'));
    console.log('Page has .chat-message-list:', html.includes('chat-message-list'));

    // Check if React rendered
    const reactRoot = await page.locator('#root').count();
    console.log('React root exists:', reactRoot > 0);

    // Check for loading indicators
    const loadingText = await page.locator('text=로딩').count();
    const loadingIndicators = await page.locator('[aria-busy="true"]').count();
    console.log('Loading text count:', loadingText);
    console.log('Loading indicators:', loadingIndicators);

    // Take final screenshot
    await page.screenshot({ path: 'debug-final-state.png', fullPage: true });

    // Print all console messages
    console.log('=== ALL CONSOLE MESSAGES ===');
    consoleMessages.forEach((msg, i) => {
      if (i < 50) console.log(msg); // First 50 messages
    });
  });
});
