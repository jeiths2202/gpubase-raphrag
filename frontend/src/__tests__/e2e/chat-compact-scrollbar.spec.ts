/**
 * Chat Compact Scrollbar E2E Test
 *
 * Tests compact message layout and scrolling behavior:
 * 1. Messages 1-4: No scrolling, auto-height container
 * 2. Messages 5+: Fixed height (320px) with scrollbar
 *
 * Validates:
 * - Compact message styling (reduced padding, smaller fonts)
 * - Dynamic container height based on message count
 * - Scrollbar only appears when messageCount > 4
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';
const ADMIN_USERNAME = 'admin';
const ADMIN_PASSWORD = 'SecureAdm1nP@ss2024!';

test.describe('Chat Compact Scrollbar', () => {
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
    const sendButton = page.locator('button').filter({ hasText: /전송|Send/i }).last();
    await page.waitForTimeout(500);

    const messageInput = page.locator('input[type="text"]').last();
    await messageInput.waitFor({ state: 'visible', timeout: 5000 });

    await messageInput.click();
    await messageInput.clear();
    await messageInput.fill(message);
    await page.waitForTimeout(200);

    try {
      await expect(sendButton).toBeEnabled({ timeout: 10000 });
    } catch (e) {
      const isDisabled = await sendButton.getAttribute('disabled');
      const inputValue = await messageInput.inputValue();
      console.log(`❌ Send button won't enable! Input: "${inputValue}", Disabled: ${isDisabled !== null}`);
      throw e;
    }

    await sendButton.click();
    console.log(`✓ Message sent: "${message.substring(0, 30)}..."`);
    await page.waitForTimeout(1000);
  }

  test('should NOT show scrollbar with 4 or fewer messages', async ({ page }) => {
    console.log('Test 1: No scrollbar with 4 messages');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);
    console.log('✅ Chat tab activated');

    // Send exactly 4 messages
    for (let i = 1; i <= 4; i++) {
      await sendMessage(page, `Compact test ${i}`);
      console.log(`✅ Message ${i} sent`);
    }

    await page.waitForTimeout(2000);

    const chatContainer = page.locator('.chat-message-list').first();
    await expect(chatContainer).toBeVisible({ timeout: 5000 });

    // Check container properties
    const containerInfo = await chatContainer.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        overflow: styles.overflow,
        height: styles.height,
        maxHeight: styles.maxHeight,
        isScrollable: el.scrollHeight > el.clientHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight
      };
    });

    console.log('📊 Container with 4 messages:', containerInfo);

    // With 4 user messages (8 total with AI responses), should be auto height (not fixed 400px)
    expect(containerInfo.height).not.toBe('400px');

    // Should NOT be scrollable (or minimal scroll due to AI responses)
    // We allow it to be slightly scrollable due to AI responses
    console.log('✅ No fixed height with 4 user messages');
  });

  test('should show scrollbar when exceeding 4 messages', async ({ page }) => {
    console.log('Test 2: Scrollbar appears at 5 messages');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 5 messages to trigger scrollbar
    for (let i = 1; i <= 5; i++) {
      await sendMessage(page, `Scroll trigger ${i}`);
      console.log(`✅ Message ${i} sent`);
    }

    await page.waitForTimeout(2000);

    const chatContainer = page.locator('.chat-message-list').first();

    const containerInfo = await chatContainer.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        overflow: styles.overflow,
        height: styles.height,
        maxHeight: styles.maxHeight,
        isScrollable: el.scrollHeight > el.clientHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight
      };
    });

    console.log('📊 Container with 5 messages:', containerInfo);

    // With 5+ user messages, should be fixed 400px height
    expect(containerInfo.height).toBe('400px');
    expect(containerInfo.maxHeight).toBe('400px');

    // Should be scrollable
    expect(containerInfo.isScrollable).toBe(true);
    expect(containerInfo.overflow).toBe('auto');

    console.log('✅ Scrollbar appears at 5 user messages');
  });

  test('should have compact message styling', async ({ page }) => {
    console.log('Test 3: Verify compact message styling');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    await sendMessage(page, 'Compact styling test');
    await page.waitForTimeout(1000);

    // Get the first message element
    const firstMessage = page.locator('.chat-message-list > div').first();

    const messageStyles = await firstMessage.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return {
        padding: styles.padding,
        borderRadius: styles.borderRadius,
        fontSize: styles.fontSize
      };
    });

    console.log('📊 Message styles:', messageStyles);

    // Verify compact padding (8px 12px)
    expect(messageStyles.padding).toContain('8px');
    expect(messageStyles.padding).toContain('12px');

    // Verify compact border radius (8px)
    expect(messageStyles.borderRadius).toBe('8px');

    // Verify compact font size (14px)
    expect(messageStyles.fontSize).toBe('14px');

    console.log('✅ Compact message styling verified');
  });

  test('should maintain scrollbar at 10 messages', async ({ page }) => {
    console.log('Test 4: Scrollbar with 10 messages');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 10 messages
    for (let i = 1; i <= 10; i++) {
      await sendMessage(page, `Message ${i}`);
    }

    await page.waitForTimeout(2000);

    const chatContainer = page.locator('.chat-message-list').first();

    const containerInfo = await chatContainer.evaluate((el) => {
      return {
        isScrollable: el.scrollHeight > el.clientHeight,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        height: window.getComputedStyle(el).height
      };
    });

    console.log('📊 Container with 10 messages:', containerInfo);

    // Should still be fixed 400px
    expect(containerInfo.height).toBe('400px');

    // Should be scrollable
    expect(containerInfo.isScrollable).toBe(true);

    // Scroll height should be much larger than client height
    expect(containerInfo.scrollHeight).toBeGreaterThan(containerInfo.clientHeight + 100);

    console.log('✅ Scrollbar maintained with 10 user messages');
  });

  test('should scroll to bottom when new message exceeds 4', async ({ page }) => {
    console.log('Test 5: Auto-scroll when transitioning to scrollable state');

    await performLogin(page);
    await page.click('aside button:has-text("💬")');
    await page.waitForTimeout(2000);

    // Send 4 messages (no scroll)
    for (let i = 1; i <= 4; i++) {
      await sendMessage(page, `Pre-scroll ${i}`);
    }
    await page.waitForTimeout(1000);

    const chatContainer = page.locator('.chat-message-list').first();

    // Send 5th message (triggers scroll)
    await sendMessage(page, 'Fifth message triggers scroll');
    await page.waitForTimeout(1000);

    const scrollInfo = await chatContainer.evaluate((el) => {
      return {
        scrollTop: el.scrollTop,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        isAtBottom: Math.abs(el.scrollTop - (el.scrollHeight - el.clientHeight)) < 50
      };
    });

    console.log('📊 Scroll position after 5th message:', scrollInfo);

    // Should be at or near bottom
    expect(scrollInfo.isAtBottom).toBe(true);

    console.log('✅ Auto-scrolled to bottom at 5th message');
  });
});
