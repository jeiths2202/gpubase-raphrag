/**
 * IMS SSO Connection E2E Test
 * Tests the frontend IMS SSO connection UI flow
 */

import { test, expect } from '@playwright/test';

test.describe('IMS SSO Connection', () => {
  test.setTimeout(60000); // 60 seconds timeout per test

  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto('http://localhost:3000/login');

    // Wait for login form to be ready
    await page.waitForSelector('input[type="text"]', { timeout: 10000 });
    await page.waitForSelector('input[type="password"]');

    // Login with user credentials
    await page.fill('input[type="text"]', 'edelweise@naver.com');
    await page.fill('input[type="password"]', 'SecureTest123!');
    await page.click('button.btn-primary');

    // Wait for navigation to complete (either dashboard or knowledge page)
    await page.waitForURL(/\/(dashboard|knowledge)/, { timeout: 15000 });

    // If on dashboard, navigate to Knowledge App
    if (page.url().includes('/dashboard')) {
      await page.click('text=Knowledge Management');
      await page.waitForURL('**/knowledge', { timeout: 10000 });
    }
  });

  test('should display IMS Knowledge Service tab', async ({ page }) => {
    // Click on IMS Knowledge Service tab (Korean text)
    await page.click('text=IMS 지식 서비스');

    // Verify header is displayed (Korean text)
    await expect(page.locator('h2:has-text("AI Agent를 사용한 IMS 지식 서비스")')).toBeVisible();
  });

  test('should show IMS connection form', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Verify connection form elements (Korean text)
    await expect(page.locator('text=IMS 시스템 연결')).toBeVisible();
    await expect(page.locator('label:has-text("IMS URL")')).toBeVisible();
    await expect(page.locator('input[placeholder*="ims.company.com"]')).toBeVisible();
    await expect(page.locator('button:has-text("SSO로 연결")')).toBeVisible();
  });

  test('should validate empty URL input', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Clear the URL input (if pre-filled)
    const urlInput = page.locator('input[placeholder*="ims.company.com"]');
    await urlInput.clear();

    // Click connect button
    await page.click('button:has-text("SSO로 연결")');

    // Verify error message (Korean text)
    await expect(page.locator('text=URL을 입력해주세요')).toBeVisible();
  });

  test('should show connection error when Chrome is running', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Enter IMS URL
    const urlInput = page.locator('input[placeholder*="ims.company.com"]');
    await urlInput.fill('https://ims.tmaxsoft.com');

    // Click connect button
    await page.click('button:has-text("SSO로 연결")');

    // Wait for error message (Korean - Chrome database locked error or connection failed)
    await expect(page.locator('text=/Cookie database is locked|IMS 시스템 연결에 실패했습니다/i')).toBeVisible({ timeout: 15000 });
  });

  test('should disable connect button while connecting', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Enter IMS URL
    const urlInput = page.locator('input[placeholder*="ims.company.com"]');
    await urlInput.fill('https://ims.tmaxsoft.com');

    // Click connect button
    const connectButton = page.locator('button:has-text("SSO로 연결")');
    await connectButton.click();

    // Verify button changes to "연결 중..." and is disabled
    await expect(page.locator('button:has-text("연결 중...")')).toBeDisabled();
  });

  test('should not show chat UI when not connected', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Verify chat UI is not visible (Korean text)
    await expect(page.locator('text=AI 지식 생성 챗')).not.toBeVisible();
    await expect(page.locator('input[placeholder*="질문을 입력하세요"]')).not.toBeVisible();
  });

  test('should make API request to backend on connect', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Set up request interception
    const requestPromise = page.waitForRequest(request =>
      request.url().includes('/api/v1/ims-sso/connect') &&
      request.method() === 'POST'
    );

    // Enter IMS URL
    const urlInput = page.locator('input[placeholder*="ims.company.com"]');
    await urlInput.fill('https://ims.tmaxsoft.com');

    // Click connect button
    await page.click('button:has-text("SSO로 연결")');

    // Wait for request
    const request = await requestPromise;

    // Verify request payload
    const postData = request.postDataJSON();
    expect(postData).toHaveProperty('ims_url', 'https://ims.tmaxsoft.com');
    expect(postData).toHaveProperty('chrome_profile', 'Default');
  });

  test('should display connection status after API response', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Set up response interception
    await page.route('**/api/v1/ims-sso/connect', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            session_id: 'test-session-123',
            ims_url: 'https://ims.tmaxsoft.com',
            user_info: { name: 'Test User', email: 'test@example.com' }
          }
        })
      });
    });

    // Enter IMS URL
    const urlInput = page.locator('input[placeholder*="ims.company.com"]');
    await urlInput.fill('https://ims.tmaxsoft.com');

    // Click connect button
    await page.click('button:has-text("SSO로 연결")');

    // Verify connection success (Korean text)
    await expect(page.locator('text=✓ 연결됨')).toBeVisible();
    await expect(page.locator('button:has-text("연결 해제")')).toBeVisible();
    // Verify URL is displayed in connection status (first occurrence)
    await expect(page.locator('div:has-text("https://ims.tmaxsoft.com")').first()).toBeVisible();
  });

  test('should show chat UI after successful connection', async ({ page }) => {
    // Click on IMS Knowledge Service tab
    await page.click('text=IMS 지식 서비스');

    // Mock successful connection
    await page.route('**/api/v1/ims-sso/connect', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            session_id: 'test-session-123',
            ims_url: 'https://ims.tmaxsoft.com',
            user_info: { name: 'Test User' }
          }
        })
      });
    });

    // Connect
    await page.fill('input[placeholder*="ims.company.com"]', 'https://ims.tmaxsoft.com');
    await page.click('button:has-text("SSO로 연결")');

    // Wait for connection (Korean text)
    await expect(page.locator('text=✓ 연결됨')).toBeVisible();

    // Verify chat UI is now visible (Korean text)
    await expect(page.locator('text=AI 지식 생성 챗')).toBeVisible();
    await expect(page.locator('input[placeholder*="질문을 입력하세요"]')).toBeVisible();
    await expect(page.locator('button:has-text("전송")')).toBeVisible();
  });
});
