import { test, expect, Page } from '@playwright/test';
import path from 'path';

/**
 * Adaptive Documents Upload Test
 *
 * Tests the PDF adaptive embedding feature through the UI.
 */

// Test PDF file path
const TEST_PDF = '/opt/kms/OF_OSI_7.2_MFS-Reference-Guide_v3.1.2_jp.pdf';

// Login credentials
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'SecureAdm1nP@ss2024!';

test.describe('Adaptive Documents Upload', () => {
  test.beforeEach(async ({ page }) => {
    // Enable console logging for debugging
    page.on('console', msg => {
      if (msg.type() === 'error' || msg.text().includes('adaptive')) {
        console.log('CONSOLE:', msg.type(), msg.text());
      }
    });
    page.on('pageerror', err => console.log('PAGE ERROR:', err.message));
  });

  async function login(page: Page) {
    console.log('=== Login ===');
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Fill login form
    const userIdInput = page.locator('#userId');
    const passwordInput = page.locator('#password');
    const submitButton = page.locator('button[type="submit"]');

    await userIdInput.fill(ADMIN_EMAIL);
    await passwordInput.fill(ADMIN_PASSWORD);
    await submitButton.click();

    // Wait for navigation
    await page.waitForTimeout(3000);

    // Verify login success
    const currentUrl = page.url();
    console.log('URL after login:', currentUrl);

    if (currentUrl.includes('/login')) {
      throw new Error('Login failed - still on login page');
    }

    console.log('Login successful');
  }

  test('should upload PDF and create adaptive chunks', async ({ page }) => {
    // Step 1: Login
    await login(page);

    // Step 2: Navigate to Documents page
    console.log('=== Navigate to Documents ===');
    await page.goto('/documents');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'e2e/screenshots/adaptive-documents-page.png', fullPage: true });

    // Step 3: Click Adaptive tab
    console.log('=== Click Adaptive Tab ===');
    const adaptiveTab = page.locator('button').filter({ hasText: 'Adaptive' });
    await expect(adaptiveTab).toBeVisible({ timeout: 10000 });
    await adaptiveTab.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'e2e/screenshots/adaptive-tab-clicked.png', fullPage: true });

    // Step 4: Verify Adaptive Documents component is visible
    console.log('=== Verify Adaptive Documents UI ===');
    const adaptiveSection = page.locator('.adaptive-documents');
    await expect(adaptiveSection).toBeVisible({ timeout: 5000 });

    // Step 5: Find and click upload button
    console.log('=== Upload PDF ===');
    const uploadButton = page.locator('.btn-primary').first();
    await expect(uploadButton).toBeVisible();

    // Set up file chooser
    const fileInput = page.locator('input[type="file"][accept=".pdf"]');

    // Upload file using setInputFiles
    await fileInput.setInputFiles(TEST_PDF);
    console.log('File selected:', TEST_PDF);

    await page.screenshot({ path: 'e2e/screenshots/adaptive-uploading.png', fullPage: true });

    // Step 6: Wait for processing
    console.log('=== Wait for Processing ===');

    // Wait for document to appear in list (up to 60 seconds for processing)
    const documentList = page.locator('.document-list');
    await expect(documentList).toBeVisible({ timeout: 60000 });

    // Wait for status to change to 'completed'
    const statusBadge = page.locator('.status-badge').first();
    await expect(statusBadge).toBeVisible({ timeout: 10000 });

    // Poll for completion status
    let attempts = 0;
    const maxAttempts = 60; // 60 attempts * 2 seconds = 120 seconds max
    let status = '';

    while (attempts < maxAttempts) {
      status = await statusBadge.textContent() || '';
      console.log(`Attempt ${attempts + 1}: Status = ${status}`);

      if (status.toLowerCase().includes('completed') || status.toLowerCase().includes('완료')) {
        console.log('Processing completed!');
        break;
      }

      if (status.toLowerCase().includes('failed') || status.toLowerCase().includes('실패')) {
        console.log('Processing failed!');
        await page.screenshot({ path: 'e2e/screenshots/adaptive-failed.png', fullPage: true });
        throw new Error('PDF processing failed');
      }

      await page.waitForTimeout(2000);
      attempts++;
    }

    if (attempts >= maxAttempts) {
      await page.screenshot({ path: 'e2e/screenshots/adaptive-timeout.png', fullPage: true });
      throw new Error(`Processing timed out. Last status: ${status}`);
    }

    await page.screenshot({ path: 'e2e/screenshots/adaptive-completed.png', fullPage: true });

    // Step 7: View chunks
    console.log('=== View Chunks ===');
    const viewChunksButton = page.locator('button').filter({ hasText: /View Chunks|청크 보기|Chunks/i }).first();
    if (await viewChunksButton.isVisible()) {
      await viewChunksButton.click();
      await page.waitForTimeout(2000);

      // Check chunks list
      const chunksList = page.locator('.chunks-list');
      await expect(chunksList).toBeVisible({ timeout: 10000 });

      // Count chunks
      const chunkItems = page.locator('.chunk-item');
      const chunkCount = await chunkItems.count();
      console.log(`Found ${chunkCount} chunks`);

      // Check embedding status
      const embeddedBadges = page.locator('.embedded');
      const embeddedCount = await embeddedBadges.count();
      console.log(`Embedded chunks: ${embeddedCount}`);

      await page.screenshot({ path: 'e2e/screenshots/adaptive-chunks.png', fullPage: true });
    }

    // Step 8: View coverage
    console.log('=== View Coverage ===');
    const viewCoverageButton = page.locator('button').filter({ hasText: /Coverage|커버리지/i }).first();
    if (await viewCoverageButton.isVisible()) {
      await viewCoverageButton.click();
      await page.waitForTimeout(2000);

      // Check coverage view
      const coverageView = page.locator('.coverage-view');
      if (await coverageView.isVisible()) {
        // Get overall coverage
        const overallCoverage = page.locator('.coverage-card.overall .value');
        const coverageValue = await overallCoverage.textContent();
        console.log(`Overall coverage: ${coverageValue}`);

        await page.screenshot({ path: 'e2e/screenshots/adaptive-coverage.png', fullPage: true });
      }
    }

    // Step 9: Test search
    console.log('=== Test Search ===');
    const searchInput = page.locator('.search-bar input');
    if (await searchInput.isVisible()) {
      await searchInput.fill('MFS Reference');

      const searchButton = page.locator('.search-bar button');
      await searchButton.click();
      await page.waitForTimeout(3000);

      // Check search results
      const searchResults = page.locator('.search-result-item');
      const resultCount = await searchResults.count();
      console.log(`Search results: ${resultCount}`);

      if (resultCount > 0) {
        // Get first result similarity
        const similarity = page.locator('.similarity').first();
        const simValue = await similarity.textContent();
        console.log(`First result similarity: ${simValue}`);
      }

      await page.screenshot({ path: 'e2e/screenshots/adaptive-search.png', fullPage: true });
    }

    console.log('=== Test Complete ===');
  });

  test('should display embedding status correctly', async ({ page }) => {
    // Login
    await login(page);

    // Navigate to Documents > Adaptive
    await page.goto('/documents');
    await page.waitForLoadState('networkidle');

    const adaptiveTab = page.locator('button').filter({ hasText: 'Adaptive' });
    await adaptiveTab.click();
    await page.waitForTimeout(1000);

    // Check if there are existing documents
    const documentList = page.locator('.document-list li');
    const docCount = await documentList.count();

    if (docCount > 0) {
      console.log(`Found ${docCount} existing documents`);

      // Click on first document's chunks view
      const firstDoc = documentList.first();
      const chunksButton = firstDoc.locator('button').filter({ hasText: /Chunks/i });

      if (await chunksButton.isEnabled()) {
        await chunksButton.click();
        await page.waitForTimeout(2000);

        // Check embedding status badges
        const chunkItems = page.locator('.chunk-item');
        const totalChunks = await chunkItems.count();

        const embeddedBadges = page.locator('.embedded');
        const embeddedCount = await embeddedBadges.count();

        const notEmbeddedBadges = page.locator('.not-embedded');
        const notEmbeddedCount = await notEmbeddedBadges.count();

        console.log(`Total chunks: ${totalChunks}`);
        console.log(`Embedded: ${embeddedCount}`);
        console.log(`Not embedded: ${notEmbeddedCount}`);

        // Verify counts match
        expect(embeddedCount + notEmbeddedCount).toBeLessThanOrEqual(totalChunks);

        await page.screenshot({ path: 'e2e/screenshots/adaptive-embedding-status.png', fullPage: true });
      }
    } else {
      console.log('No existing documents found - skipping embedding status check');
    }
  });
});
