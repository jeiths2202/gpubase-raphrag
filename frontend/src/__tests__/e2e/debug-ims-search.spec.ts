import { test, expect } from '@playwright/test';

test.describe('IMS Knowledge Service - Search Debug', () => {
  test('Debug IMS search functionality', async ({ page }) => {
    // Enable console and network logging
    page.on('console', msg => {
      console.log(`[BROWSER ${msg.type().toUpperCase()}]:`, msg.text());
    });

    page.on('requestfailed', request => {
      console.log(`[REQUEST FAILED]: ${request.url()}`);
      console.log(`  Failure: ${request.failure()?.errorText}`);
    });

    page.on('response', response => {
      const status = response.status();
      const url = response.url();
      if (url.includes('/api/') && (status >= 400 || url.includes('ims'))) {
        console.log(`[API RESPONSE]: ${response.status()} ${url}`);
      }
    });

    // Navigate to login page
    console.log('\n=== Step 1: Navigate to login ===');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');

    // KMS Login
    console.log('\n=== Step 2: KMS Login ===');
    await page.fill('input[placeholder*="이메일"]', 'edelweise@naver.com');
    await page.fill('input[placeholder*="비밀번호"]', 'SecureTest123!');

    const loginButton = page.locator('form button[type="submit"]:has-text("로그인")');
    await loginButton.click();

    // Wait for login to complete (might redirect to / or /knowledge)
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    console.log(`✓ KMS Login successful - Current URL: ${page.url()}`);

    // Navigate to IMS Knowledge Service if not already there
    if (!page.url().includes('/knowledge')) {
      console.log('\n=== Step 3: Navigate to IMS Knowledge Service ===');
      await page.goto('http://localhost:3000/knowledge');
      await page.waitForLoadState('networkidle');
    } else {
      console.log('\n=== Step 3: Already on /knowledge URL ===');
    }

    // Click IMS 지식 서비스 menu item in sidebar
    console.log('\n=== Step 4: Click IMS 지식 서비스 menu ===');
    const imsMenuItem = page.locator('text=IMS 지식 서비스');
    if (await imsMenuItem.isVisible()) {
      await imsMenuItem.click();
      await page.waitForTimeout(2000);
      console.log('✓ IMS 지식 서비스 menu clicked');
    }

    // IMS Credentials Setup - Wait for modal to appear
    console.log('\n=== Step 5: IMS Credentials Setup ===');
    await page.waitForTimeout(2000);

    // Check if credentials setup modal is visible
    const credentialsModal = page.locator('text=IMS Credentials Setup');
    const isModalVisible = await credentialsModal.isVisible().catch(() => false);

    if (isModalVisible) {
      console.log('IMS Credentials Setup modal detected - filling credentials...');

      // Fill Username field (find by label)
      const usernameField = page.locator('label:has-text("Username") + input, input[placeholder*="Username"]').first();
      await usernameField.fill('yijae.shin');
      console.log('✓ Username filled: yijae.shin');

      // Fill Password field (find by label)
      const passwordField = page.locator('label:has-text("Password") + input, input[placeholder*="Password"]').last();
      await passwordField.fill('12qwaszx');
      console.log('✓ Password filled');

      // Click Save & Validate button
      const saveButton = page.locator('button:has-text("Save & Validate"), button:has-text("Save")');
      await saveButton.click();
      console.log('✓ Save & Validate clicked');

      // Wait for validation and modal to close
      await page.waitForTimeout(5000);
      console.log('✓ IMS Credentials saved and validated');
    } else {
      console.log('✓ IMS Credentials already configured');
    }

    // Find search input and button (after modal is closed)
    console.log('\n=== Step 6: Execute search ===');

    // Wait for the main search interface to be ready
    await page.waitForTimeout(2000);

    // Find the search input - should be a textarea in the main interface, NOT in any modal
    const searchInput = page.locator('textarea, input[type="text"]').last();
    await searchInput.waitFor({ state: 'visible', timeout: 10000 });
    await searchInput.fill('온라인서버 CPU과부하 원인에 대한 해결방안 알려줘');
    console.log('✓ Search query entered');

    // Capture network requests
    const searchRequests: any[] = [];
    page.on('request', request => {
      if (request.url().includes('/api/v1/ims')) {
        searchRequests.push({
          url: request.url(),
          method: request.method(),
          headers: request.headers(),
          postData: request.postData()
        });
      }
    });

    const searchButton = page.locator('button:has-text("Search")');
    await searchButton.click();

    console.log('✓ Search button clicked');

    // Wait for any network activity
    await page.waitForTimeout(5000);

    // Check search requests
    console.log('\n=== Step 7: Analyze network requests ===');
    if (searchRequests.length === 0) {
      console.error('❌ ERROR: No API requests made!');
      console.log('This means the search button click did not trigger any backend API calls.');
    } else {
      console.log(`✓ Found ${searchRequests.length} API request(s):`);
      searchRequests.forEach((req, idx) => {
        console.log(`\nRequest ${idx + 1}:`);
        console.log(`  URL: ${req.url}`);
        console.log(`  Method: ${req.method}`);
        console.log(`  Post Data: ${req.postData}`);
      });
    }

    // Check page state
    console.log('\n=== Step 8: Check page state ===');
    const pendingStatus = page.locator('text=pending');
    const foundCount = page.locator('text=/Found: \\d+/');

    const hasPending = await pendingStatus.isVisible().catch(() => false);
    const foundText = await foundCount.textContent().catch(() => '');

    console.log(`Status: ${hasPending ? 'pending' : 'not pending'}`);
    console.log(`Found count: ${foundText}`);

    // Check for any error messages
    const errorMessages = await page.locator('[class*="error"], [class*="Error"]').allTextContents();
    if (errorMessages.length > 0) {
      console.log('\n=== Error messages found ===');
      errorMessages.forEach(msg => console.log(`  - ${msg}`));
    }

    // Take screenshot
    await page.screenshot({ path: 'debug-ims-search-state.png', fullPage: true });
    console.log('\n✓ Screenshot saved: debug-ims-search-state.png');
  });
});
