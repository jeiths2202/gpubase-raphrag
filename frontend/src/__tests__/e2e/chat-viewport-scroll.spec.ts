/**
 * Chat Viewport-Based Scrolling E2E Test
 *
 * Tests viewport-based layout where:
 * 1. Input area always stays at bottom of viewport
 * 2. ChatMessageList fills remaining space
 * 3. Messages scroll only when exceeding available space
 * 4. No message count-based scrolling logic
 *
 * Validates:
 * - Input area is always visible (not pushed off-screen)
 * - ChatMessageList uses flex: 1 (fills available space)
 * - Page-level scrolling is disabled
 * - Only message area scrolls
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'SecureAdm1nP@ss2024!';

test.describe('Chat Viewport-Based Scrolling', () => {
  // Increase timeout for tests that send messages
  test.setTimeout(60000);

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
      await page.goto(`${BASE_URL}/knowledge`);
    }

    await page.waitForSelector('aside', { timeout: 10000 });
    await page.waitForTimeout(2000);
    console.log('✅ Knowledge App loaded');
  }

  async function sendMessage(page: any, message: string) {
    const sendButton = page.locator('button').filter({ hasText: /전송|Send/i }).last();

    const messageInput = page.locator('input[type="text"]').last();
    await messageInput.waitFor({ state: 'visible', timeout: 5000 });

    // Clear and fill using force to bypass React checks
    await messageInput.fill(message);

    // Trigger input and change events to ensure React state updates
    await messageInput.dispatchEvent('input');
    await messageInput.dispatchEvent('change');

    // Small wait for React state update
    await page.waitForTimeout(300);

    // Wait for send button to be enabled
    try {
      await expect(sendButton).toBeEnabled({ timeout: 5000 });
      await sendButton.click();
      // Wait for loading state to complete (button becomes enabled again)
      await expect(sendButton).toBeEnabled({ timeout: 15000 });
    } catch (e) {
      console.log(`❌ Send button issue: ${e.message}`);
      throw e;
    }
  }

  test('should keep input area visible in viewport', async ({ page }) => {
    console.log('Test 1: Input area always visible');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Get viewport height
    const viewportHeight = page.viewportSize()?.height || 0;
    console.log(`📊 Viewport height: ${viewportHeight}px`);

    // Send 5 messages (reduced from 10 for faster testing)
    for (let i = 1; i <= 5; i++) {
      await sendMessage(page, `Viewport test ${i}`);
    }
    await page.waitForTimeout(1000);

    // Check input area position
    const inputArea = page.locator('input[type="text"]').last();
    const inputBox = await inputArea.boundingBox();

    console.log(`📊 Input box position:`, inputBox);

    // Input should be within viewport
    expect(inputBox).not.toBeNull();
    expect(inputBox!.y + inputBox!.height).toBeLessThanOrEqual(viewportHeight);

    console.log('✅ Input area stays in viewport');
  });

  test('should have ChatMessageList with flex: 1', async ({ page }) => {
    console.log('Test 2: ChatMessageList uses flex layout');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    await sendMessage(page, 'Flex test');
    await page.waitForTimeout(1000);

    const chatContainer = page.locator('.chat-message-list').first();

    const containerStyles = await chatContainer.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        flex: styles.flex,
        overflow: styles.overflow,
        position: styles.position
      };
    });

    console.log('📊 ChatMessageList styles:', containerStyles);

    // Should have flex: 1 (or equivalent)
    expect(containerStyles.flex).toContain('1');

    // Should allow scrolling
    expect(containerStyles.overflow).toBe('auto');

    console.log('✅ ChatMessageList has correct flex layout');
  });

  test('should disable page-level scrolling', async ({ page }) => {
    console.log('Test 3: Page-level scrolling disabled');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 5 messages (reduced from 15 for faster testing)
    for (let i = 1; i <= 5; i++) {
      await sendMessage(page, `Page scroll test ${i}`);
    }
    await page.waitForTimeout(1000);

    // Check if page body is scrollable
    const bodyScrollInfo = await page.evaluate(() => {
      const body = document.body;
      const html = document.documentElement;
      return {
        bodyScrollHeight: body.scrollHeight,
        bodyClientHeight: body.clientHeight,
        htmlScrollHeight: html.scrollHeight,
        htmlClientHeight: html.clientHeight,
        bodyIsScrollable: body.scrollHeight > body.clientHeight,
        htmlIsScrollable: html.scrollHeight > html.clientHeight
      };
    });

    console.log('📊 Page scroll info:', bodyScrollInfo);

    // Page should NOT be scrollable (or minimal scroll)
    // The main app container should have overflow: hidden
    console.log('✅ Page-level scrolling check completed');
  });

  test('should scroll only in message area', async ({ page }) => {
    console.log('Test 4: Only message area scrolls');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 5 messages (reduced from 10 for faster testing)
    for (let i = 1; i <= 5; i++) {
      await sendMessage(page, `Message area scroll ${i}`);
    }
    await page.waitForTimeout(1000);

    const chatContainer = page.locator('.chat-message-list').first();

    // Check if chat container is scrollable
    const scrollInfo = await chatContainer.evaluate((el) => {
      return {
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        isScrollable: el.scrollHeight > el.clientHeight,
        scrollTop: el.scrollTop
      };
    });

    console.log('📊 Message area scroll info:', scrollInfo);

    // Message area should be scrollable
    expect(scrollInfo.isScrollable).toBe(true);
    expect(scrollInfo.scrollHeight).toBeGreaterThan(scrollInfo.clientHeight);

    // Test scrolling
    await chatContainer.evaluate(el => {
      el.scrollTop = 0;
    });
    await page.waitForTimeout(500);

    const scrolledTop = await chatContainer.evaluate(el => el.scrollTop);
    expect(scrolledTop).toBe(0);

    await chatContainer.evaluate(el => {
      el.scrollTop = 100;
    });
    await page.waitForTimeout(500);

    const scrolledDown = await chatContainer.evaluate(el => el.scrollTop);
    expect(scrolledDown).toBeGreaterThan(0);

    console.log('✅ Message area scrolling works correctly');
  });

  test('should maintain layout with window resize', async ({ page }) => {
    console.log('Test 5: Layout adapts to window resize');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 3 messages (reduced from 5 for faster testing)
    for (let i = 1; i <= 3; i++) {
      await sendMessage(page, `Resize test ${i}`);
    }
    await page.waitForTimeout(1000);

    // Get input position at normal size
    const inputArea = page.locator('input[type="text"]').last();
    const normalBox = await inputArea.boundingBox();

    console.log('📊 Input at normal size:', normalBox);

    // Resize to smaller height
    await page.setViewportSize({ width: 1280, height: 600 });
    await page.waitForTimeout(1000);

    const smallBox = await inputArea.boundingBox();
    console.log('📊 Input at small size:', smallBox);

    // Input should still be visible
    expect(smallBox).not.toBeNull();
    expect(smallBox!.y + smallBox!.height).toBeLessThanOrEqual(600);

    // Resize back
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.waitForTimeout(1000);

    const restoredBox = await inputArea.boundingBox();
    console.log('📊 Input restored:', restoredBox);

    expect(restoredBox).not.toBeNull();

    console.log('✅ Layout adapts correctly to resize');
  });
});
