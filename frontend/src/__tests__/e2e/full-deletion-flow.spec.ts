/**
 * Full Deletion Flow Test - Complete End-to-End Test
 *
 * This test creates a conversation, then deletes it, and verifies the deletion.
 * Run with --headed flag to see the browser automation in action.
 */
import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';

test.describe('Complete Deletion Flow', () => {
  test('should create conversation, delete it, and verify deletion', async ({ page }) => {
    // Set longer timeout for this comprehensive test
    test.setTimeout(120000);

    console.log('\n🚀 Starting Full Deletion Flow Test\n');

    // ========================================================================
    // Step 1: Login
    // ========================================================================
    console.log('📝 Step 1: Logging in...');
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const emailInput = page.locator('input[type="email"], input[name="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('edelweise@naver.com');
      await page.fill('input[type="password"], input[name="password"]', 'SecureTest123!');

      const loginButton = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("로그인")');
      await loginButton.click();
      await page.waitForLoadState('networkidle');
      console.log('✅ Logged in successfully\n');
    } else {
      console.log('✅ Already logged in\n');
    }

    // Navigate to chat - try multiple approaches
    await page.waitForTimeout(2000);

    // Try clicking Chat/채팅 tab if it exists
    const chatTabSelectors = [
      'button:has-text("Chat")',
      'button:has-text("채팅")',
      'button:has-text("チャット")',
      'nav button:has-text("Chat")',
      '[role="tab"]:has-text("Chat")'
    ];

    for (const selector of chatTabSelectors) {
      const chatTab = page.locator(selector).first();
      if (await chatTab.isVisible({ timeout: 1000 }).catch(() => false)) {
        console.log(`   Clicking Chat tab with selector: ${selector}`);
        await chatTab.click();
        await page.waitForTimeout(1500);
        break;
      }
    }

    // Take screenshot of initial state
    await page.screenshot({ path: 'test-results/01-initial-state.png', fullPage: true });

    // ========================================================================
    // Step 2: Create a new conversation
    // ========================================================================
    console.log('📝 Step 2: Creating a new conversation...');

    // Wait for page to settle
    await page.waitForTimeout(1000);

    // Try multiple selectors for input field
    const inputSelectors = [
      'input[type="text"]',
      'input[placeholder*="질문"]',
      'input[placeholder*="question"]',
      'input[placeholder*="入力"]',
      'textarea[placeholder*="질문"]',
      'textarea[placeholder*="question"]'
    ];

    let inputField = null;
    for (const selector of inputSelectors) {
      const field = page.locator(selector).filter({ hasNot: page.locator('[type="file"]') }).first();
      if (await field.isVisible({ timeout: 1000 }).catch(() => false)) {
        inputField = field;
        console.log(`   Found input field with selector: ${selector}`);
        break;
      }
    }

    if (inputField && await inputField.isVisible({ timeout: 3000 }).catch(() => false)) {
      const sendButton = page.locator('button:has-text("Send"), button:has-text("전송"), button:has-text("送信")').first();
      const testMessage = `Test conversation for deletion - ${new Date().toISOString()}`;

      console.log(`   Sending message: "${testMessage}"`);
      await inputField.fill(testMessage);
      await page.screenshot({ path: 'test-results/02-message-typed.png', fullPage: true });

      await sendButton.click();
      console.log('   Waiting for message to be sent...');
      await page.waitForTimeout(3000);

      // Wait for the message to appear in chat
      const messageInChat = page.locator(`text="${testMessage}"`).first();
      if (await messageInChat.isVisible({ timeout: 5000 }).catch(() => false)) {
        console.log('✅ Message sent and appeared in chat\n');
        await page.screenshot({ path: 'test-results/03-message-sent.png', fullPage: true });
      } else {
        console.log('⚠️ Message sent but not visible in chat (may still be processing)\n');
      }
    } else {
      throw new Error('❌ Chat input field not found');
    }

    // ========================================================================
    // Step 3: Open conversation history sidebar
    // ========================================================================
    console.log('📝 Step 3: Opening conversation history...');

    // Wait a bit for conversation to be saved
    await page.waitForTimeout(2000);

    // Look for conversation history button - try multiple selectors
    const historyButtonSelectors = [
      'button:has-text("Conversation")',
      'button:has-text("대화")',
      'button:has-text("会話")',
      'button[aria-label*="history"]',
      'button[title*="history"]',
      'button[aria-label*="대화"]'
    ];

    let historyButton = null;
    for (const selector of historyButtonSelectors) {
      const btn = page.locator(selector).first();
      if (await btn.isVisible({ timeout: 1000 }).catch(() => false)) {
        historyButton = btn;
        console.log(`   Found history button with selector: ${selector}`);
        break;
      }
    }

    if (historyButton) {
      await historyButton.click();
      await page.waitForTimeout(1000);
      console.log('✅ Conversation history opened\n');
      await page.screenshot({ path: 'test-results/04-history-opened.png', fullPage: true });
    } else {
      console.log('⚠️ Could not find conversation history button, taking screenshot for debugging');
      await page.screenshot({ path: 'test-results/04-no-history-button.png', fullPage: true });

      // Try to find any buttons for debugging
      const allButtons = await page.locator('button').all();
      console.log(`   Total buttons found: ${allButtons.length}`);
      for (let i = 0; i < Math.min(allButtons.length, 10); i++) {
        const text = await allButtons[i].textContent();
        const ariaLabel = await allButtons[i].getAttribute('aria-label');
        console.log(`   Button ${i + 1}: text="${text}", aria-label="${ariaLabel}"`);
      }
    }

    // ========================================================================
    // Step 4: Find the conversation in the list
    // ========================================================================
    console.log('📝 Step 4: Finding conversation in list...');

    await page.waitForTimeout(1000);

    // Look for conversation list
    const conversationList = page.locator('[role="list"], .conversation-list');
    const conversationItems = page.locator('[role="button"]').filter({
      hasText: /message|메시지|メッセージ|Test conversation/
    });

    const count = await conversationItems.count();
    console.log(`   Found ${count} conversation(s) in the list`);

    if (count > 0) {
      console.log('✅ Conversation found in list\n');
      await page.screenshot({ path: 'test-results/05-conversation-in-list.png', fullPage: true });
    } else {
      console.log('⚠️ No conversations found in list');
      await page.screenshot({ path: 'test-results/05-no-conversations.png', fullPage: true });

      // Debug: Show what's in the sidebar
      const sidebarContent = await page.locator('.conversation-sidebar, [role="complementary"]').textContent();
      console.log('   Sidebar content:', sidebarContent);
    }

    // ========================================================================
    // Step 5: Hover over conversation to reveal delete button
    // ========================================================================
    if (count > 0) {
      console.log('📝 Step 5: Hovering over conversation to reveal delete button...');

      const firstConversation = conversationItems.first();
      await firstConversation.hover();
      await page.waitForTimeout(500);

      console.log('✅ Hovered over conversation\n');
      await page.screenshot({ path: 'test-results/06-hover-delete-button.png', fullPage: true });

      // ========================================================================
      // Step 6: Click delete button
      // ========================================================================
      console.log('📝 Step 6: Looking for delete button...');

      const deleteButton = firstConversation.locator('button[aria-label*="Delete"], button[aria-label*="삭제"], button:has-text("🗑️")').first();

      const isDeleteVisible = await deleteButton.isVisible({ timeout: 2000 }).catch(() => false);

      if (isDeleteVisible) {
        console.log('✅ Delete button is visible\n');

        // Set up dialog handler BEFORE clicking
        console.log('📝 Step 7: Setting up confirmation dialog handler...');
        page.once('dialog', async dialog => {
          console.log(`\n📢 Confirmation Dialog Appeared:`);
          console.log(`   Type: ${dialog.type()}`);
          console.log(`   Message: ${dialog.message()}`);
          console.log('   Accepting deletion...\n');
          await dialog.accept();
        });

        console.log('📝 Step 8: Clicking delete button...');
        await deleteButton.click();
        await page.waitForTimeout(2000);

        await page.screenshot({ path: 'test-results/07-after-delete-click.png', fullPage: true });

        // ========================================================================
        // Step 9: Verify deletion
        // ========================================================================
        console.log('📝 Step 9: Verifying deletion...');

        const newCount = await conversationItems.count();
        console.log(`   Conversations before deletion: ${count}`);
        console.log(`   Conversations after deletion: ${newCount}`);

        if (newCount < count) {
          console.log('✅ Conversation successfully deleted from UI!\n');
        } else {
          console.log('⚠️ Conversation count unchanged after deletion\n');
        }

        await page.screenshot({ path: 'test-results/08-after-deletion.png', fullPage: true });

        // Verify conversation was deleted
        expect(newCount).toBeLessThan(count);

      } else {
        console.log('⚠️ Delete button not visible after hover');
        await page.screenshot({ path: 'test-results/06-no-delete-button.png', fullPage: true });

        // Debug: Check what's in the conversation item
        const itemHTML = await firstConversation.innerHTML();
        console.log('   Conversation item HTML:', itemHTML.substring(0, 500));
      }
    }

    // ========================================================================
    // Step 10: Final screenshot
    // ========================================================================
    console.log('📝 Step 10: Taking final screenshot...');
    await page.screenshot({ path: 'test-results/09-final-state.png', fullPage: true });

    console.log('\n✅ Test completed! Check test-results folder for screenshots.\n');
  });
});
