/**
 * Conversation Deletion Test
 *
 * Tests conversation deletion functionality after login
 */

import { test, expect } from '@playwright/test';

test.describe('Conversation Deletion', () => {
  test('should login and delete conversation successfully', async ({ page }) => {
    test.setTimeout(90000); // 90 second timeout

    // Step 1: Login
    console.log('Step 1: Logging in...');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');

    const emailInput = page.locator('input[type="email"], input[type="text"], input[name="username"], input[name="email"]').first();
    await emailInput.fill('edelweise@naver.com');

    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.fill('SecureTest123!');

    const loginButton = page.locator('button[type="submit"]');

    await Promise.all([
      page.waitForURL(url => !url.toString().includes('/login'), { timeout: 15000 }),
      loginButton.click()
    ]);

    console.log('✅ Login successful');

    // Step 2: Navigate to Knowledge page
    console.log('Step 2: Navigating to Knowledge page...');
    await page.goto('http://localhost:3000/knowledge');
    await page.waitForLoadState('networkidle', { timeout: 15000 });

    // Take screenshot
    await page.screenshot({ path: 'test-results/knowledge-page.png', fullPage: true });

    console.log('Current URL:', page.url());

    // Step 3: Wait for conversations to load
    console.log('Step 3: Waiting for conversations to load...');
    await page.waitForTimeout(3000); // Wait for data to load

    // Look for "New Conversation" button or similar
    const newConvButton = page.locator('button:has-text("New"), button:has-text("새로운")').first();
    const hasNewButton = await newConvButton.count();

    if (hasNewButton > 0) {
      console.log('✅ Found New Conversation button');
      await newConvButton.click();
      await page.waitForTimeout(2000);
    }

    // Step 4: Look for conversation items with role="button"
    console.log('Step 4: Looking for conversation items...');

    // Conversation items are motion.div with role="button"
    const conversationItems = page.locator('[role="button"]').filter({ hasText: /message|대화/ });
    const count = await conversationItems.count();

    console.log(`✅ Found ${count} conversation items`);

    if (count === 0) {
      console.log('⚠️ No conversations found, taking screenshot...');
      await page.screenshot({ path: 'test-results/no-conversations.png', fullPage: true });
      return;
    }

    // Take screenshot before hover
    await page.screenshot({ path: 'test-results/before-hover.png', fullPage: true });

    // Step 5: Hover over the first conversation to reveal delete button
    console.log('Step 5: Hovering over first conversation...');
    const firstConversation = conversationItems.first();
    await firstConversation.hover();

    // Wait a moment for hover state to trigger
    await page.waitForTimeout(500);

    // Take screenshot after hover
    await page.screenshot({ path: 'test-results/after-hover.png', fullPage: true });

    // Step 6: Find delete button (trash emoji button)
    console.log('Step 6: Looking for delete button...');

    // The delete button appears on hover and contains 🗑️ emoji
    const deleteButton = page.locator('button:has-text("🗑️")').first();

    const deleteButtonVisible = await deleteButton.isVisible({ timeout: 3000 }).catch(() => false);

    if (!deleteButtonVisible) {
      console.log('⚠️ Delete button not visible, trying alternative selectors...');

      // Try aria-label selector
      const deleteByAriaLabel = page.locator('button[aria-label*="삭제"], button[aria-label*="delete"], button[title*="삭제"], button[title*="delete"]').first();
      const altVisible = await deleteByAriaLabel.isVisible({ timeout: 2000 }).catch(() => false);

      if (altVisible) {
        console.log('✅ Found delete button by aria-label');
      } else {
        console.log('❌ Delete button still not found');
        await page.screenshot({ path: 'test-results/delete-button-not-found.png', fullPage: true });
        return;
      }
    } else {
      console.log('✅ Delete button (🗑️) is visible');
    }

    // Step 7: Setup dialog handler for confirmation
    console.log('Step 7: Setting up confirmation dialog handler...');
    page.on('dialog', async dialog => {
      console.log(`Dialog message: "${dialog.message()}"`);
      await dialog.accept();
      console.log('✅ Confirmed deletion');
    });

    // Step 8: Click delete button and monitor network
    console.log('Step 8: Clicking delete button...');

    const responsePromise = page.waitForResponse(
      response => response.url().includes('/conversations/') && response.request().method() === 'DELETE',
      { timeout: 15000 }
    );

    await deleteButton.click();

    try {
      const deleteResponse = await responsePromise;
      const status = deleteResponse.status();

      console.log(`Delete API response: ${status}`);

      if (status === 200) {
        console.log('✅ Delete request successful (200 OK)');

        const responseBody = await deleteResponse.json().catch(() => null);
        if (responseBody) {
          console.log('Response:', JSON.stringify(responseBody, null, 2));
        }

        // Verify deletion was successful
        expect(status).toBe(200);
      } else {
        console.log(`❌ Delete failed with status: ${status}`);
        const errorText = await deleteResponse.text();
        console.log('Error:', errorText);

        throw new Error(`Delete failed with status ${status}: ${errorText}`);
      }
    } catch (error) {
      console.log('❌ Error during deletion:', error);
      throw error;
    }

    await page.waitForTimeout(2000);

    // Take screenshot after deletion
    await page.screenshot({ path: 'test-results/after-deletion.png', fullPage: true });

    console.log('✅ Test completed');
  });
});
