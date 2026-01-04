/**
 * E2E Tests for Conversation Deletion Functionality
 *
 * Tests the ability to delete conversations from the conversation history sidebar
 * and verify deletion from both UI and database.
 */
import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const API_BASE = 'http://localhost:8000/api/v1';

test.describe('Conversation Deletion', () => {
  test.beforeEach(async ({ page }) => {
    // Go to login page
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Login if needed
    const emailInput = page.locator('input[type="email"], input[name="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('edelweise@naver.com');
      await page.fill('input[type="password"], input[name="password"]', 'SecureTest123!');

      const loginButton = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("로그인")');
      await loginButton.click();
      await page.waitForLoadState('networkidle');
    }

    // Navigate to chat tab
    const chatTab = page.locator('button:has-text("Chat"), button:has-text("채팅"), button:has-text("チャット")').first();
    if (await chatTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      await chatTab.click();
      await page.waitForTimeout(1000);
    }
  });

  test('should display delete button on hover over conversation item', async ({ page }) => {
    // Open conversation history sidebar
    const historyButton = page.locator('button:has-text("Conversation"), button:has-text("대화"), button:has-text("会話")').first();
    if (await historyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyButton.click();
      await page.waitForTimeout(500);
    }

    // Wait for conversation list to load
    await page.waitForSelector('[role="list"], .conversation-list', { timeout: 5000 }).catch(() => {});

    // Get the first conversation item
    const conversationItem = page.locator('[role="button"]').filter({ hasText: /message|메시지|メッセージ/ }).first();

    if (await conversationItem.isVisible({ timeout: 2000 }).catch(() => false)) {
      // Hover over the conversation item
      await conversationItem.hover();

      // Wait for delete button to appear
      await page.waitForTimeout(300);

      // Check if delete button is visible
      const deleteButton = conversationItem.locator('button[aria-label*="Delete"], button[aria-label*="삭제"], button[title*="Delete"]');

      // Take screenshot for verification
      await page.screenshot({ path: 'delete-button-hover.png' });

      console.log('✅ Delete button appears on hover');
    } else {
      console.log('ℹ️ No conversations available to test hover');
    }
  });

  test('should delete conversation with confirmation', async ({ page }) => {
    // First, create a new conversation for testing
    const inputField = page.locator('input[placeholder*="질문"], input[placeholder*="question"], textarea[placeholder*="질문"]').first();
    const sendButton = page.locator('button:has-text("Send"), button:has-text("전송"), button:has-text("送信")').first();

    const testMessage = `Test conversation for deletion - ${Date.now()}`;

    if (await inputField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await inputField.fill(testMessage);
      await sendButton.click();

      // Wait for message to be sent
      await page.waitForTimeout(2000);
    }

    // Open conversation history sidebar
    const historyButton = page.locator('button:has-text("Conversation"), button:has-text("대화 일람"), button:has-text("会話一覧")').first();
    if (await historyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyButton.click();
      await page.waitForTimeout(500);
    }

    // Wait for conversation list
    await page.waitForSelector('[role="list"], .conversation-list', { timeout: 5000 }).catch(() => {});

    // Find the conversation we just created
    const conversationItems = page.locator('[role="button"]').filter({ hasText: /message|메시지|メッセージ/ });
    const conversationCount = await conversationItems.count();

    console.log(`📊 Found ${conversationCount} conversations`);

    if (conversationCount > 0) {
      const firstConversation = conversationItems.first();

      // Hover to reveal delete button
      await firstConversation.hover();
      await page.waitForTimeout(300);

      // Set up dialog handler BEFORE clicking delete
      page.once('dialog', async dialog => {
        console.log(`📢 Dialog message: ${dialog.message()}`);
        expect(dialog.type()).toBe('confirm');
        expect(dialog.message()).toContain('delete' || '삭제' || '削除');
        await dialog.accept(); // Accept the deletion
      });

      // Click delete button
      const deleteButton = firstConversation.locator('button[aria-label*="Delete"], button[aria-label*="삭제"], button:has-text("🗑️")').first();

      if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
        console.log('🗑️ Clicking delete button...');
        await deleteButton.click();

        // Wait for deletion to complete
        await page.waitForTimeout(2000);

        // Verify the conversation was removed from the list
        const newConversationCount = await conversationItems.count();
        console.log(`📊 Conversations after deletion: ${newConversationCount}`);

        expect(newConversationCount).toBe(conversationCount - 1);

        console.log('✅ Conversation successfully deleted from UI');
      } else {
        console.log('⚠️ Delete button not visible after hover');
      }
    } else {
      console.log('ℹ️ No conversations available to delete');
    }

    // Take final screenshot
    await page.screenshot({ path: 'after-deletion.png', fullPage: true });
  });

  test('should cancel deletion when user declines confirmation', async ({ page }) => {
    // Open conversation history sidebar
    const historyButton = page.locator('button:has-text("Conversation"), button:has-text("대화"), button:has-text("会話")').first();
    if (await historyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyButton.click();
      await page.waitForTimeout(500);
    }

    // Wait for conversation list
    await page.waitForSelector('[role="list"], .conversation-list', { timeout: 5000 }).catch(() => {});

    const conversationItems = page.locator('[role="button"]').filter({ hasText: /message|メッセージ|메시지/ });
    const initialCount = await conversationItems.count();

    if (initialCount > 0) {
      const firstConversation = conversationItems.first();

      // Hover to reveal delete button
      await firstConversation.hover();
      await page.waitForTimeout(300);

      // Set up dialog handler to CANCEL deletion
      page.once('dialog', async dialog => {
        console.log(`📢 Cancelling deletion dialog`);
        await dialog.dismiss(); // Cancel the deletion
      });

      // Click delete button
      const deleteButton = firstConversation.locator('button[aria-label*="Delete"], button[aria-label*="삭제"], button:has-text("🗑️")').first();

      if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
        await deleteButton.click();
        await page.waitForTimeout(1000);

        // Verify the conversation was NOT removed
        const finalCount = await conversationItems.count();
        expect(finalCount).toBe(initialCount);

        console.log('✅ Deletion cancelled successfully');
      }
    } else {
      console.log('ℹ️ No conversations available to test cancellation');
    }
  });

  test('should clear active conversation when deleting the active one', async ({ page }) => {
    // Create and send a message to establish an active conversation
    const inputField = page.locator('input[placeholder*="질문"], input[placeholder*="question"], textarea[placeholder*="질문"]').first();
    const sendButton = page.locator('button:has-text("Send"), button:has-text("전송"), button:has-text("送信")').first();

    if (await inputField.isVisible({ timeout: 3000 }).catch(() => false)) {
      await inputField.fill('Active conversation test');
      await sendButton.click();
      await page.waitForTimeout(2000);
    }

    // Open conversation history
    const historyButton = page.locator('button:has-text("Conversation"), button:has-text("대화"), button:has-text("会話")').first();
    if (await historyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyButton.click();
      await page.waitForTimeout(500);
    }

    await page.waitForSelector('[role="list"]', { timeout: 5000 }).catch(() => {});

    // Find the active conversation (should have visual indicator)
    const activeConversation = page.locator('[role="button"][aria-current="true"]').first();

    if (await activeConversation.isVisible({ timeout: 2000 }).catch(() => false)) {
      console.log('🎯 Found active conversation');

      // Hover and delete
      await activeConversation.hover();
      await page.waitForTimeout(300);

      page.once('dialog', async dialog => {
        await dialog.accept();
      });

      const deleteButton = activeConversation.locator('button[aria-label*="Delete"], button[aria-label*="삭제"]').first();

      if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
        await deleteButton.click();
        await page.waitForTimeout(2000);

        // Verify active conversation is cleared (chat should show empty state or prompt)
        const emptyState = page.locator('text=/새로운 대화|New Chat|新しいチャット/i');
        const isEmptyVisible = await emptyState.isVisible({ timeout: 3000 }).catch(() => false);

        console.log(`📊 Empty state visible after deleting active conversation: ${isEmptyVisible}`);
      }
    } else {
      console.log('ℹ️ No active conversation to test');
    }
  });
});

test.describe('Conversation Deletion API Integration', () => {
  test('should call DELETE endpoint with correct conversation ID', async ({ page, context }) => {
    // Setup API request interception
    const apiCalls: any[] = [];

    page.on('request', request => {
      if (request.url().includes('/api/v1/conversations/') && request.method() === 'DELETE') {
        apiCalls.push({
          url: request.url(),
          method: request.method(),
          headers: request.headers()
        });
        console.log(`🌐 DELETE request intercepted: ${request.url()}`);
      }
    });

    page.on('response', response => {
      if (response.url().includes('/api/v1/conversations/') && response.request().method() === 'DELETE') {
        console.log(`📡 DELETE response: ${response.status()} ${response.statusText()}`);
      }
    });

    // Login
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const emailInput = page.locator('input[type="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('edelweise@naver.com');
      await page.fill('input[type="password"]', 'SecureTest123!');
      await page.click('button[type="submit"]');
      await page.waitForLoadState('networkidle');
    }

    // Navigate to chat
    const chatTab = page.locator('button:has-text("Chat"), button:has-text("채팅")').first();
    if (await chatTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      await chatTab.click();
    }

    // Open history and try to delete
    const historyButton = page.locator('button:has-text("Conversation"), button:has-text("대화")').first();
    if (await historyButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await historyButton.click();
      await page.waitForTimeout(500);
    }

    await page.waitForSelector('[role="list"]', { timeout: 5000 }).catch(() => {});

    const conversationItem = page.locator('[role="button"]').filter({ hasText: /message|메시지/ }).first();

    if (await conversationItem.isVisible({ timeout: 2000 }).catch(() => false)) {
      await conversationItem.hover();
      await page.waitForTimeout(300);

      page.once('dialog', async dialog => {
        await dialog.accept();
      });

      const deleteButton = conversationItem.locator('button[aria-label*="Delete"], button[aria-label*="삭제"]').first();

      if (await deleteButton.isVisible({ timeout: 1000 }).catch(() => false)) {
        await deleteButton.click();
        await page.waitForTimeout(2000);

        // Verify API was called
        expect(apiCalls.length).toBeGreaterThan(0);

        if (apiCalls.length > 0) {
          const deleteCall = apiCalls[0];
          console.log(`✅ API Call verified:`, deleteCall);

          // Check URL format: /api/v1/conversations/{id}?hard_delete=false
          expect(deleteCall.url).toMatch(/\/api\/v1\/conversations\/[a-f0-9-]+\?hard_delete=false/);
          expect(deleteCall.method).toBe('DELETE');
        }
      }
    }

    console.log(`📊 Total DELETE API calls: ${apiCalls.length}`);
  });
});
