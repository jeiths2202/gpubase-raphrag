import { test, expect } from '@playwright/test';

test.describe('Chat UI Test - Phase 3 Components', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto('http://localhost:3000');

    // Login with email
    await page.fill('input[type="text"]', 'edelweise@naver.com');
    await page.fill('input[type="password"]', 'SecureTest123!');
    await page.click('button[type="submit"]');

    // Wait for redirect to knowledge/chat page
    await page.waitForURL('**/knowledge', { timeout: 10000 });
    await page.waitForLoadState('networkidle');
  });

  test('should render chat components after login', async ({ page }) => {
    // Check if we're on the knowledge page
    await expect(page).toHaveURL(/\/knowledge/);

    // Take screenshot of the page
    await page.screenshot({ path: 'chat-page-loaded.png', fullPage: true });

    // Check for Phase 3 refactored components
    const hasNewConversationButton = await page.locator('.new-conversation-btn').count();
    const hasChatMessageList = await page.locator('.chat-message-list').count();
    const hasConversationSidebar = await page.locator('.conversation-sidebar-panel').count();

    console.log('New Conversation Button:', hasNewConversationButton);
    console.log('Chat Message List:', hasChatMessageList);
    console.log('Conversation Sidebar:', hasConversationSidebar);
  });

  test('should click new conversation button', async ({ page }) => {
    // Find and click new conversation button
    const newChatButton = page.locator('.new-conversation-btn');

    if (await newChatButton.count() > 0) {
      await newChatButton.click();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: 'new-conversation-clicked.png', fullPage: true });
    } else {
      console.log('New conversation button not found');
      await page.screenshot({ path: 'no-new-button.png', fullPage: true });
    }
  });

  test('should open conversation history sidebar', async ({ page }) => {
    // Look for sidebar trigger button
    const sidebarTrigger = page.locator('button').filter({ hasText: /history|대화|목록/i });

    if (await sidebarTrigger.count() > 0) {
      await sidebarTrigger.first().click();
      await page.waitForTimeout(500);

      // Check if sidebar appeared
      const sidebar = await page.locator('.conversation-sidebar-panel').count();
      console.log('Sidebar visible:', sidebar > 0);

      await page.screenshot({ path: 'sidebar-opened.png', fullPage: true });
    } else {
      console.log('Sidebar trigger not found');
      await page.screenshot({ path: 'no-sidebar-trigger.png', fullPage: true });
    }
  });

  test('should capture console errors', async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    page.on('pageerror', error => {
      pageErrors.push(error.message);
    });

    // Wait and collect errors
    await page.waitForTimeout(3000);

    console.log('Console Errors:', consoleErrors);
    console.log('Page Errors:', pageErrors);

    // Take final screenshot
    await page.screenshot({ path: 'final-state.png', fullPage: true });
  });
});
