const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,  // Headless mode for automation
    args: ['--no-sandbox']
  });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 }
  });
  const page = await context.newPage();

  try {
    // 1. Login
    console.log('1. Logging in...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);

    // 2. Navigate directly to RAG chat page
    console.log('2. Opening RAG chat...');
    await page.goto('http://localhost:3000/chat', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'e2e2_01_chat_page.png' });
    console.log('   Screenshot: e2e2_01_chat_page.png');

    // 3. Look for RAG agent selector or chat input
    console.log('3. Looking for chat interface...');

    // Try to find and click RAG mode if available
    const ragButton = await page.locator('button:has-text("RAG"), [data-agent="rag"], .agent-selector:has-text("RAG")').first();
    if (await ragButton.count() > 0) {
      await ragButton.click();
      await page.waitForTimeout(1000);
    }

    // 4. Find chat textarea and enter query
    console.log('4. Entering query...');
    const chatInput = await page.locator('textarea').first();
    await chatInput.click();
    await chatInput.fill('tjesmgr 커맨드 옵션 목록');
    await page.screenshot({ path: 'e2e2_02_query_entered.png' });

    // 5. Submit query
    console.log('5. Submitting query...');
    // Try send button first
    const sendButton = await page.locator('button[type="submit"], button:has(svg), button.send-button').last();
    if (await sendButton.count() > 0) {
      await sendButton.click();
    } else {
      await chatInput.press('Enter');
    }

    // 6. Wait for response
    console.log('6. Waiting for response (30 seconds)...');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'e2e2_03_loading.png' });

    // Wait for typing indicator to disappear or response to appear
    await page.waitForTimeout(25000);
    await page.screenshot({ path: 'e2e2_04_response.png' });
    console.log('   Screenshot: e2e2_04_response.png');

    // 7. Click on chat tab if in sources view
    const chatTab = await page.locator('button:has-text("チャット"), [data-tab="chat"], .tab:has-text("Chat")').first();
    if (await chatTab.count() > 0) {
      await chatTab.click();
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: 'e2e2_05_chat_tab.png' });
    console.log('   Screenshot: e2e2_05_chat_tab.png');

    // 8. Full page screenshot
    await page.screenshot({ path: 'e2e2_06_full.png', fullPage: true });
    console.log('   Screenshot: e2e2_06_full.png (full page)');

    console.log('\n✅ E2E Test completed!');

    // Keep browser open for 10 seconds for manual inspection
    console.log('Browser will close in 10 seconds...');
    await page.waitForTimeout(10000);

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'e2e2_error.png' });
  } finally {
    await browser.close();
  }
})();
