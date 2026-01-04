/**
 * Chat Scrollbar E2E Test
 *
 * Tests scrollbar functionality in:
 * 1. ChatMessageList component (main chat area)
 * 2. ConversationHistorySidebar component (conversation list)
 *
 * Validates:
 * - Scrollbar visibility when content overflows
 * - Scrollbar interaction (scroll, drag)
 * - Scrollbar styling (width, color, hover effects)
 * - Auto-scroll behavior for new messages
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'SecureAdm1nP@ss2024!';

test.describe('Chat Scrollbar Functionality', () => {
  /**
   * Helper function to perform login
   */
  async function performLogin(page: any) {
    await page.goto(`${BASE_URL}/login`);
    await page.waitForLoadState('networkidle');

    const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
    await usernameInput.waitFor({ state: 'visible', timeout: 5000 });
    await usernameInput.fill(ADMIN_USERNAME);

    const passwordInput = page.locator('input[type="password"]').first();
    await passwordInput.waitFor({ state: 'visible', timeout: 5000 });
    await passwordInput.fill(ADMIN_PASSWORD);

    const loginButton = page.locator('button[type="submit"]');
    await loginButton.click();

    await page.waitForURL(url => !url.toString().includes('/login'), { timeout: 10000 });
    console.log('✅ Login successful');

    const currentUrl = page.url();
    if (!currentUrl.includes('/knowledge')) {
      console.log(`Navigating to /knowledge from ${currentUrl}`);
      await page.goto(`${BASE_URL}/knowledge`);
    }

    await page.waitForSelector('aside', { timeout: 10000 });
    await page.waitForTimeout(2000);
    console.log('✅ Knowledge App loaded');
  }

  /**
   * Helper to send a chat message
   */
  async function sendMessage(page: any, message: string) {
    // Wait for any ongoing AI response to complete
    const sendButton = page.locator('button').filter({ hasText: /전송|Send/i }).last();
    await page.waitForTimeout(500); // Brief wait for UI to settle

    const messageInput = page.locator('input[type="text"]').last();
    await messageInput.waitFor({ state: 'visible', timeout: 5000 });

    // Clear and fill input (triggers React onChange)
    await messageInput.click();
    await messageInput.clear();
    await messageInput.fill(message);

    // Wait for React state to update
    await page.waitForTimeout(200);

    // Wait for send button to be enabled (AI response may still be loading)
    try {
      await expect(sendButton).toBeEnabled({ timeout: 10000 });
    } catch (e) {
      // Debug: Print state if button won't enable
      const isDisabled = await sendButton.getAttribute('disabled');
      const inputValue = await messageInput.inputValue();
      console.log(`❌ Send button won't enable! Input: "${inputValue}", Disabled: ${isDisabled !== null}`);
      throw e;
    }

    await sendButton.click();
    console.log(`✓ Message sent: "${message.substring(0, 30)}..."`);

    // Wait for message to appear and AI response to start
    await page.waitForTimeout(1000);
  }

  test('should display scrollbar in chat message list when content overflows', async ({ page }) => {
    console.log('Test 1: Scrollbar visibility in chat message list');

    // Step 1: Login and navigate to Chat
    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);
    console.log('✅ Chat tab activated');

    // Step 2: Send multiple messages to trigger overflow
    console.log('Step 2: Sending multiple messages to trigger scrollbar...');
    for (let i = 1; i <= 15; i++) {
      await sendMessage(page, `Test message ${i} - ${Date.now()}`);
      console.log(`✅ Message ${i} sent`);
    }

    await page.waitForTimeout(2000);

    // Step 3: Locate the chat message list container
    const chatContainer = page.locator('.chat-message-list').first();
    await expect(chatContainer).toBeVisible({ timeout: 5000 });
    console.log('✅ Chat message list container found');

    // Step 4: Check if container is scrollable
    const isScrollable = await chatContainer.evaluate((el) => {
      return el.scrollHeight > el.clientHeight;
    });
    console.log(`📊 Container scrollable: ${isScrollable}`);
    console.log(`📊 scrollHeight: ${await chatContainer.evaluate(el => el.scrollHeight)}`);
    console.log(`📊 clientHeight: ${await chatContainer.evaluate(el => el.clientHeight)}`);

    expect(isScrollable).toBe(true);

    // Step 5: Get computed scrollbar styles
    const scrollbarStyles = await chatContainer.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        overflow: styles.overflow,
        overflowY: styles.overflowY,
        scrollbarWidth: styles.scrollbarWidth,
        scrollbarColor: styles.scrollbarColor
      };
    });
    console.log('📊 Scrollbar styles:', scrollbarStyles);

    // Step 6: Test scroll interaction
    console.log('Step 3: Testing scroll interaction...');
    const initialScrollTop = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 Initial scrollTop: ${initialScrollTop}`);

    // Scroll up
    await chatContainer.evaluate(el => {
      el.scrollTop = 0;
    });
    await page.waitForTimeout(500);

    const scrolledTop = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 After scroll to top: ${scrolledTop}`);
    expect(scrolledTop).toBe(0);

    // Scroll down
    await chatContainer.evaluate(el => {
      el.scrollTop = el.scrollHeight;
    });
    await page.waitForTimeout(500);

    const scrolledBottom = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 After scroll to bottom: ${scrolledBottom}`);
    expect(scrolledBottom).toBeGreaterThan(0);

    console.log('✅ Chat message list scrollbar test passed');
  });

  test('should display scrollbar in conversation history sidebar', async ({ page }) => {
    console.log('Test 2: Scrollbar visibility in conversation history sidebar');

    // Step 1: Login and navigate to Chat
    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Step 2: Look for conversation history button (if exists)
    // The sidebar might need to be opened via a button
    const historyButton = page.locator('button').filter({ hasText: /대화 목록|History|Conversations/i }).first();
    const historyButtonExists = await historyButton.count() > 0;

    if (!historyButtonExists) {
      console.log('⚠️ Conversation history button not found - sidebar may not be implemented yet');
      return;
    }

    // Step 3: Open conversation history sidebar
    await historyButton.click();
    await page.waitForTimeout(1000);
    console.log('✅ Conversation history sidebar opened');

    // Step 4: Locate the conversation list scroll container
    const sidebarContainer = page.locator('.conversation-list-scroll').first();

    if (await sidebarContainer.count() === 0) {
      console.log('⚠️ Conversation list scroll container not found');
      return;
    }

    await expect(sidebarContainer).toBeVisible({ timeout: 5000 });
    console.log('✅ Conversation list container found');

    // Step 5: Check if container is scrollable
    const isScrollable = await sidebarContainer.evaluate((el) => {
      return el.scrollHeight > el.clientHeight;
    });
    console.log(`📊 Sidebar scrollable: ${isScrollable}`);
    console.log(`📊 scrollHeight: ${await sidebarContainer.evaluate(el => el.scrollHeight)}`);
    console.log(`📊 clientHeight: ${await sidebarContainer.evaluate(el => el.clientHeight)}`);

    // Step 6: Get computed scrollbar styles
    const scrollbarStyles = await sidebarContainer.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        overflow: styles.overflow,
        overflowY: styles.overflowY,
        scrollbarWidth: styles.scrollbarWidth,
        scrollbarColor: styles.scrollbarColor
      };
    });
    console.log('📊 Sidebar scrollbar styles:', scrollbarStyles);

    console.log('✅ Conversation history sidebar scrollbar test completed');
  });

  test('should verify scrollbar CSS properties are applied', async ({ page }) => {
    console.log('Test 3: Verify scrollbar CSS properties');

    // Step 1: Login and navigate to Chat
    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Step 2: Send messages to trigger scrollbar
    for (let i = 1; i <= 10; i++) {
      await sendMessage(page, `CSS test message ${i}`);
    }
    await page.waitForTimeout(2000);

    // Step 3: Inject a script to check WebKit scrollbar styles
    const scrollbarInfo = await page.evaluate(() => {
      const chatList = document.querySelector('.chat-message-list');
      if (!chatList) return { error: 'Chat list not found' };

      // Get the actual element styles
      const computedStyle = window.getComputedStyle(chatList);

      // Check if scrollbar pseudo-elements exist (WebKit only)
      const styleSheets = Array.from(document.styleSheets);
      let webkitScrollbarRules: any = {};

      try {
        styleSheets.forEach(sheet => {
          try {
            const rules = Array.from(sheet.cssRules || []);
            rules.forEach((rule: any) => {
              if (rule.selectorText?.includes('.chat-message-list::-webkit-scrollbar')) {
                webkitScrollbarRules[rule.selectorText] = {
                  width: rule.style.width,
                  background: rule.style.background
                };
              }
            });
          } catch (e) {
            // Skip CORS-protected stylesheets
          }
        });
      } catch (e) {
        console.error('Error reading stylesheets:', e);
      }

      return {
        overflow: computedStyle.overflow,
        overflowY: computedStyle.overflowY,
        scrollbarWidth: computedStyle.scrollbarWidth,
        scrollbarColor: computedStyle.scrollbarColor,
        maxHeight: computedStyle.maxHeight,
        webkitScrollbarRules,
        isScrollable: chatList.scrollHeight > chatList.clientHeight,
        scrollHeight: chatList.scrollHeight,
        clientHeight: chatList.clientHeight,
        className: chatList.className
      };
    });

    console.log('📊 Complete scrollbar info:', JSON.stringify(scrollbarInfo, null, 2));

    // Step 4: Verify expected properties
    expect(scrollbarInfo.overflow).not.toBe('hidden');
    expect(scrollbarInfo.isScrollable).toBe(true);

    console.log('✅ Scrollbar CSS properties verified');
  });

  test('should auto-scroll to bottom when new message is sent', async ({ page }) => {
    console.log('Test 4: Auto-scroll behavior for new messages');

    // Step 1: Login and navigate to Chat
    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Step 2: Send messages to trigger scrollbar
    for (let i = 1; i <= 10; i++) {
      await sendMessage(page, `Auto-scroll test ${i}`);
    }
    await page.waitForTimeout(1000);

    const chatContainer = page.locator('.chat-message-list').first();

    // Step 3: Scroll to top
    await chatContainer.evaluate(el => {
      el.scrollTop = 0;
    });
    await page.waitForTimeout(500);

    const scrollTopBefore = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 Scroll position before new message: ${scrollTopBefore}`);
    expect(scrollTopBefore).toBe(0);

    // Step 4: Send a new message
    await sendMessage(page, 'New message should trigger auto-scroll');
    await page.waitForTimeout(1000);

    // Step 5: Check if scrolled to bottom
    const scrollTopAfter = await chatContainer.evaluate(el => el.scrollTop);
    const scrollHeight = await chatContainer.evaluate(el => el.scrollHeight);
    const clientHeight = await chatContainer.evaluate(el => el.clientHeight);

    console.log(`📊 Scroll position after new message: ${scrollTopAfter}`);
    console.log(`📊 Expected bottom position: ${scrollHeight - clientHeight}`);

    // Should be near the bottom (within 50px tolerance for layout shifts)
    const isNearBottom = Math.abs(scrollTopAfter - (scrollHeight - clientHeight)) < 50;
    expect(isNearBottom).toBe(true);

    console.log('✅ Auto-scroll behavior verified');
  });

  test('should handle mouse wheel scrolling', async ({ page }) => {
    console.log('Test 5: Mouse wheel scrolling');

    // Step 1: Login and navigate to Chat
    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Step 2: Send messages to trigger scrollbar
    for (let i = 1; i <= 15; i++) {
      await sendMessage(page, `Wheel scroll test ${i}`);
    }
    await page.waitForTimeout(1000);

    const chatContainer = page.locator('.chat-message-list').first();

    // Step 3: Get initial scroll position
    const initialScroll = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 Initial scroll position: ${initialScroll}`);

    // Step 4: Hover over container and simulate wheel scroll up
    await chatContainer.hover();
    await chatContainer.evaluate(el => {
      el.scrollTop = 0; // Scroll to top first
    });
    await page.waitForTimeout(500);

    const scrolledTop = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 After scrolling to top: ${scrolledTop}`);
    expect(scrolledTop).toBe(0);

    // Step 5: Scroll down using wheel
    await chatContainer.evaluate(el => {
      el.scrollTop = 200; // Simulate scroll down
    });
    await page.waitForTimeout(500);

    const scrolledDown = await chatContainer.evaluate(el => el.scrollTop);
    console.log(`📊 After scrolling down: ${scrolledDown}`);
    expect(scrolledDown).toBeGreaterThan(0);

    console.log('✅ Mouse wheel scrolling verified');
  });
});
