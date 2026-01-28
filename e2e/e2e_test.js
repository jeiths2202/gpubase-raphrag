const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  try {
    console.log('1. Navigating to login page...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'e2e_01_login_page.png' });
    console.log('   Screenshot: e2e_01_login_page.png');

    console.log('2. Logging in...');
    // Fill login form
    await page.fill('input[type="text"], input[name="username"], input[placeholder*="ID"], input[placeholder*="아이디"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.screenshot({ path: 'e2e_02_login_filled.png' });

    // Click login button
    await page.click('button[type="submit"], button:has-text("로그인"), button:has-text("Login")');
    await page.waitForURL('**/chat**', { timeout: 15000 }).catch(() => {
      console.log('   Note: URL did not change to /chat, continuing...');
    });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'e2e_03_after_login.png' });
    console.log('   Screenshot: e2e_03_after_login.png');

    console.log('3. Navigating to chat page...');
    // Try to go to chat page directly if not already there
    if (!page.url().includes('/chat')) {
      await page.goto('http://localhost:3000/chat', { waitUntil: 'networkidle', timeout: 15000 });
    }
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'e2e_04_chat_page.png' });
    console.log('   Screenshot: e2e_04_chat_page.png');

    console.log('4. Sending test query...');
    // Find and fill the chat input
    const chatInput = await page.locator('textarea, input[type="text"]').last();
    await chatInput.fill('tjesmgr 커맨드 옵션 목록');
    await page.screenshot({ path: 'e2e_05_query_entered.png' });

    // Submit the query (press Enter or click send button)
    await chatInput.press('Enter');
    console.log('   Query sent, waiting for response...');

    // Wait for response (look for loading indicators to appear and disappear)
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'e2e_06_waiting_response.png' });

    // Wait more for the full response
    await page.waitForTimeout(15000);
    await page.screenshot({ path: 'e2e_07_final_response.png' });
    console.log('   Screenshot: e2e_07_final_response.png');

    // Scroll down to see full response
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'e2e_08_scrolled.png', fullPage: true });
    console.log('   Screenshot: e2e_08_scrolled.png (full page)');

    console.log('\n✅ E2E Test completed successfully!');
    console.log('Check the e2e_*.png files for screenshots.');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'e2e_error.png' });
    console.log('   Error screenshot saved: e2e_error.png');
  } finally {
    await browser.close();
  }
})();
