const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  try {
    // 1. Login
    console.log('1. Logging in...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);

    // 2. Navigate to AI Agent page via sidebar
    console.log('2. Navigating to AI Agent page...');
    // Click on "AIエージェント" in sidebar
    await page.click('text=AIエージェント');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'e2e3_01_agent_page.png' });
    console.log('   Screenshot: e2e3_01_agent_page.png');

    // 3. Select RAG agent if needed
    console.log('3. Selecting RAG agent...');
    const ragSelector = await page.locator('text=RAG, button:has-text("RAG")').first();
    if (await ragSelector.count() > 0) {
      await ragSelector.click();
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: 'e2e3_02_rag_selected.png' });

    // 4. Find chat input and enter query
    console.log('4. Entering query...');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('tjesmgr 커맨드 옵션 목록');
    await page.screenshot({ path: 'e2e3_03_query_entered.png' });

    // 5. Submit
    console.log('5. Submitting query...');
    await textarea.press('Enter');

    // 6. Wait and capture
    console.log('6. Waiting for response...');
    for (let i = 1; i <= 6; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `e2e3_response_${i * 5}s.png` });
      console.log(`   Screenshot: e2e3_response_${i * 5}s.png`);
    }

    // 7. Try to expand/scroll the response
    await page.evaluate(() => {
      const chatContainer = document.querySelector('[class*="chat"], [class*="message"], [class*="response"]');
      if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
    });
    await page.screenshot({ path: 'e2e3_final.png', fullPage: true });
    console.log('   Screenshot: e2e3_final.png');

    console.log('\n✅ Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'e2e3_error.png' });
  } finally {
    await browser.close();
  }
})();
