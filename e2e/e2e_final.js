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

    // 2. Navigate to AI Agent page
    console.log('2. Navigating to AI Agent page...');
    await page.click('text=AIエージェント');
    await page.waitForTimeout(2000);

    // 3. Enter query
    console.log('3. Entering query...');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('tjesmgr 커맨드 옵션 목록');
    await textarea.press('Enter');

    // 4. Wait for clarification dialog
    console.log('4. Waiting for clarification dialog...');
    await page.waitForTimeout(10000);
    await page.screenshot({ path: 'final_01_dialog.png' });
    console.log('   Screenshot: final_01_dialog.png');

    // 5. Click TJESMGR option, then search button
    console.log('5. Selecting option and clicking search...');
    // First click the TJESMGR option card
    await page.click('text="TJESMGR 명령어 옵션 목록"');
    await page.waitForTimeout(500);

    // Then click the search button
    await page.click('text=agent.clarification.search');
    console.log('   Clicked search button');

    // 6. Wait for search and response
    console.log('6. Waiting for response...');
    for (let i = 1; i <= 8; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `final_response_${i * 5}s.png` });
      console.log(`   Screenshot: final_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 7. Final full page screenshot
    await page.screenshot({ path: 'final_complete.png', fullPage: true });
    console.log('   Screenshot: final_complete.png');

    console.log('\n✅ E2E Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'final_error.png' });
  } finally {
    await browser.close();
  }
})();
