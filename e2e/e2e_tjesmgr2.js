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
    console.log('3. Entering query: tjesmgr에 대해서 알려줘');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('tjesmgr에 대해서 알려줘');
    await textarea.press('Enter');

    // 4. Wait for clarification dialog
    console.log('4. Waiting for clarification dialog...');
    await page.waitForTimeout(8000);
    await page.screenshot({ path: 'tjesmgr2_01_dialog.png' });

    // 5. Click first option (설명)
    console.log('5. Clicking first option (설명)...');
    const firstOption = await page.locator('text=설명').first();
    if (await firstOption.count() > 0) {
      await firstOption.click();
      console.log('   Clicked 설명 option');
    }
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'tjesmgr2_02_selected.png' });

    // 6. Click search button (agent.clarification.search)
    console.log('6. Clicking search button...');
    const searchBtn = await page.locator('text=agent.clarification.search').first();
    if (await searchBtn.count() > 0) {
      await searchBtn.click();
      console.log('   Clicked search button');
    }

    // 7. Wait for response
    console.log('7. Waiting for response...');
    for (let i = 1; i <= 8; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `tjesmgr2_response_${i * 5}s.png` });
      console.log(`   Screenshot: tjesmgr2_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 8. Full page screenshot
    await page.screenshot({ path: 'tjesmgr2_final.png', fullPage: true });
    console.log('   Screenshot: tjesmgr2_final.png');

    console.log('\n✅ E2E TJESMGR2 Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'tjesmgr2_error.png' });
  } finally {
    await browser.close();
  }
})();
