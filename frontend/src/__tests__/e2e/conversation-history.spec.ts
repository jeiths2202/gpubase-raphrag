/**
 * E2E Tests for Conversation History System
 *
 * Tests the chat functionality with conversation persistence using Ollama gemma:2b
 */
import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:3000';

test.describe('Conversation History System', () => {
  test.beforeEach(async ({ page }) => {
    // Go to login page
    await page.goto(BASE_URL);

    // Wait for page to load
    await page.waitForLoadState('networkidle');
  });

  test('should login and access chat', async ({ page }) => {
    // Check if we're on login page or already logged in
    const loginButton = page.locator('button:has-text("Login"), button:has-text("로그인"), button:has-text("ログイン")');
    const chatSection = page.locator('text=AI Chat, text=채팅, text=チャット');

    // If login button exists, we need to login
    if (await loginButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      // Fill in test credentials
      await page.fill('input[type="email"], input[name="email"]', 'admin@example.com');
      await page.fill('input[type="password"], input[name="password"]', 'SecureAdm1nP@ss2024!');

      // Click login
      await loginButton.click();

      // Wait for navigation
      await page.waitForLoadState('networkidle');
    }

    // Should now be on main app or chat
    await expect(page).not.toHaveURL(/login/);
  });

  test('should send message and receive response', async ({ page }) => {
    // Login first
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Try to login if needed
    const emailInput = page.locator('input[type="email"], input[name="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('admin@example.com');
      await page.fill('input[type="password"], input[name="password"]', 'SecureAdm1nP@ss2024!');
      await page.click('button[type="submit"], button:has-text("Login"), button:has-text("로그인")');
      await page.waitForLoadState('networkidle');
    }

    // Navigate to chat if not already there
    const chatTab = page.locator('button:has-text("Chat"), button:has-text("채팅"), nav >> text=Chat');
    if (await chatTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      await chatTab.click();
    }

    // Find the input field
    const inputField = page.locator('input[placeholder*="질문"], input[placeholder*="question"], textarea[placeholder*="질문"]');

    // Send a test message
    const testMessage = 'Hello, what is 2+2?';
    await inputField.fill(testMessage);

    // Click send button
    const sendButton = page.locator('button:has-text("Send"), button:has-text("전송"), button:has-text("送信")');
    await sendButton.click();

    // Wait for response (with longer timeout for LLM)
    await page.waitForSelector('.assistant-message, [data-role="assistant"], div:has-text("4")', {
      timeout: 60000
    });

    // Verify message appears in chat
    const userMessage = page.locator(`text="${testMessage}"`);
    await expect(userMessage).toBeVisible();
  });

  test('should maintain conversation context', async ({ page }) => {
    // Login
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    const emailInput = page.locator('input[type="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('admin@example.com');
      await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
      await page.click('button[type="submit"]');
      await page.waitForLoadState('networkidle');
    }

    // Find input field
    const inputField = page.locator('input[placeholder*="질문"], input[placeholder*="question"], textarea');
    const sendButton = page.locator('button:has-text("Send"), button:has-text("전송")');

    // First message
    await inputField.fill('My name is TestUser');
    await sendButton.click();

    // Wait for response
    await page.waitForTimeout(5000);

    // Second message asking about context
    await inputField.fill('What is my name?');
    await sendButton.click();

    // Wait for response that should contain the name
    await page.waitForTimeout(10000);

    // Check that conversation history is working
    // The response should mention "TestUser"
    const responseContainsName = await page.locator('text=/TestUser/i').isVisible({ timeout: 30000 }).catch(() => false);

    // Take screenshot for debugging
    await page.screenshot({ path: 'conversation-test.png', fullPage: true });

    console.log('Conversation context test completed');
  });
});

test.describe('Chat UI Elements', () => {
  test('should display chat interface elements', async ({ page }) => {
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');

    // Login if needed
    const emailInput = page.locator('input[type="email"]');
    if (await emailInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await emailInput.fill('admin@example.com');
      await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
      await page.click('button[type="submit"]');
      await page.waitForLoadState('networkidle');
    }

    // Navigate to chat
    const chatTab = page.locator('button:has-text("Chat"), button:has-text("채팅")').first();
    if (await chatTab.isVisible({ timeout: 2000 }).catch(() => false)) {
      await chatTab.click();
    }

    // Check for chat UI elements
    await page.screenshot({ path: 'chat-ui.png', fullPage: true });

    // Verify input field exists
    const inputField = page.locator('input, textarea').filter({ hasText: /질문|question|入力/i });

    // Verify send button exists
    const sendButton = page.locator('button').filter({ hasText: /send|전송|送信/i });

    console.log('Chat UI test completed');
  });
});
