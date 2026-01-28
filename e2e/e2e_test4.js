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
    await page.waitForTimeout(8000);
    await page.screenshot({ path: 'e2e4_01_clarification.png' });
    console.log('   Screenshot: e2e4_01_clarification.png');

    // 5. Click on TJESMGR option
    console.log('5. Selecting TJESMGR option...');
    const tjesmgrOption = await page.locator('text=TJESMGR').first();
    if (await tjesmgrOption.count() > 0) {
      await tjesmgrOption.click();
      console.log('   Clicked TJESMGR option');
    } else {
      // Try clicking "agent.clarification.search" button
      const searchBtn = await page.locator('text=agent.clarification.search, button:has-text("search")').first();
      if (await searchBtn.count() > 0) {
        await searchBtn.click();
        console.log('   Clicked search button');
      }
    }

    // 6. Wait for response
    console.log('6. Waiting for response...');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'e2e4_02_processing.png' });

    await page.waitForTimeout(15000);
    await page.screenshot({ path: 'e2e4_03_response.png' });
    console.log('   Screenshot: e2e4_03_response.png');

    await page.waitForTimeout(10000);
    await page.screenshot({ path: 'e2e4_04_final.png', fullPage: true });
    console.log('   Screenshot: e2e4_04_final.png');

    console.log('\n✅ Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'e2e4_error.png' });
  } finally {
    await browser.close();
  }
})();
