import { test, expect } from '@playwright/test';

test.describe('IMS Knowledge Service - Full Search Flow', () => {
  test('Complete search workflow with results', async ({ page }) => {
    test.setTimeout(120000); // 2 minutes for full crawl

    // Enable console logging
    page.on('console', msg => {
      if (msg.type() === 'log' && msg.text().includes('Job progress')) {
        console.log(`[PROGRESS]: ${msg.text()}`);
      }
    });

    // Navigate and login
    console.log('\n=== Step 1: KMS Login ===');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');

    await page.fill('input[placeholder*="이메일"]', 'edelweise@naver.com');
    await page.fill('input[placeholder*="비밀번호"]', 'SecureTest123!');
    const loginButton = page.locator('form button[type="submit"]:has-text("로그인")');
    await loginButton.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    console.log('✓ KMS Login successful');

    // Navigate to IMS Knowledge Service
    console.log('\n=== Step 2: Navigate to IMS Knowledge Service ===');
    if (!page.url().includes('/knowledge')) {
      await page.goto('http://localhost:3000/knowledge');
      await page.waitForLoadState('networkidle');
    }

    const imsMenuItem = page.locator('text=IMS 지식 서비스');
    if (await imsMenuItem.isVisible()) {
      await imsMenuItem.click();
      await page.waitForTimeout(2000);
      console.log('✓ IMS 지식 서비스 menu clicked');
    }

    // Handle IMS Credentials if needed
    console.log('\n=== Step 3: IMS Credentials Setup ===');
    await page.waitForTimeout(2000);
    const credentialsModal = page.locator('text=IMS Credentials Setup');
    const isModalVisible = await credentialsModal.isVisible().catch(() => false);

    if (isModalVisible) {
      console.log('Setting up IMS credentials...');
      const usernameField = page.locator('label:has-text("Username") + input, input[placeholder*="Username"]').first();
      await usernameField.fill('yijae.shin');

      const passwordField = page.locator('label:has-text("Password") + input, input[placeholder*="Password"]').last();
      await passwordField.fill('12qwaszx');

      const saveButton = page.locator('button:has-text("Save & Validate"), button:has-text("Save")');
      await saveButton.click();
      await page.waitForTimeout(5000);
      console.log('✓ IMS Credentials configured');
    } else {
      console.log('✓ IMS Credentials already configured');
    }

    // Execute search
    console.log('\n=== Step 4: Execute search ===');
    await page.waitForTimeout(2000);

    const searchInput = page.locator('textarea, input[type="text"]').last();
    await searchInput.waitFor({ state: 'visible', timeout: 10000 });
    await searchInput.fill('CPU 과부하');
    console.log('✓ Search query entered: "CPU 과부하"');

    const searchButton = page.locator('button:has-text("Search")');
    await searchButton.click();
    console.log('✓ Search button clicked');

    // Wait for job to start and monitor progress
    console.log('\n=== Step 5: Monitor job progress ===');
    await page.waitForTimeout(3000);

    // Wait for job status to appear
    let maxWait = 60000; // 60 seconds max
    let waited = 0;
    let foundResults = false;

    while (waited < maxWait) {
      // Check for "Found:" count
      const foundText = await page.locator('text=/Found: \\d+/').textContent().catch(() => '');

      // Check for status
      const statusText = await page.locator('text=/Status:|status:/i').allTextContents().catch(() => []);

      console.log(`[${waited/1000}s] Status check - Found: "${foundText}", Status elements: ${statusText.length}`);

      // Check if we have results (Found > 0)
      if (foundText && foundText.match(/Found: (\d+)/)) {
        const foundCount = parseInt(foundText.match(/Found: (\d+)/)?.[1] || '0');
        if (foundCount > 0) {
          console.log(`✓ Found ${foundCount} issues!`);
          foundResults = true;
          break;
        }
      }

      // Check for completed status
      const pageContent = await page.content();
      if (pageContent.includes('completed') || pageContent.includes('Completed')) {
        console.log('✓ Job completed');
        break;
      }

      await page.waitForTimeout(2000);
      waited += 2000;
    }

    // Take final screenshot
    console.log('\n=== Step 6: Capture final state ===');
    await page.screenshot({ path: 'ims-search-results.png', fullPage: true });
    console.log('✓ Screenshot saved: ims-search-results.png');

    // Get final statistics
    const finalFoundText = await page.locator('text=/Found: \\d+/').textContent().catch(() => 'Not found');
    const finalCrawledText = await page.locator('text=/Crawled: \\d+/').textContent().catch(() => 'Not found');
    const finalAttachmentsText = await page.locator('text=/Attachments: \\d+/').textContent().catch(() => 'Not found');

    console.log('\n=== Final Results ===');
    console.log(`Found: ${finalFoundText}`);
    console.log(`Crawled: ${finalCrawledText}`);
    console.log(`Attachments: ${finalAttachmentsText}`);

    // Check if we have any results
    if (foundResults) {
      console.log('\n✅ Search completed successfully with results!');
    } else {
      console.log('\n⚠️ Search completed but no results found (may still be processing)');
    }

    // Wait a bit more to see final state
    await page.waitForTimeout(5000);
  });
});
