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
    await page.screenshot({ path: 'e2e5_01_dialog.png' });

    // 5. Click first option card in the dialog (TJESMGR option)
    console.log('5. Clicking TJESMGR option card...');
    // Use more specific selector - click the first card/option div in the dialog
    const optionCard = await page.locator('div[class*="option"], div[class*="card"], div[class*="choice"]').first();
    if (await optionCard.count() > 0) {
      await optionCard.click();
      console.log('   Clicked option card');
    } else {
      // Try clicking based on text content more specifically
      await page.click('text="TJESMGR 명령어 옵션 목록"');
      console.log('   Clicked by text');
    }

    // 6. Wait for response
    console.log('6. Waiting for response (30s)...');
    await page.waitForTimeout(10000);
    await page.screenshot({ path: 'e2e5_02_processing.png' });

    await page.waitForTimeout(20000);
    await page.screenshot({ path: 'e2e5_03_response.png' });
    console.log('   Screenshot: e2e5_03_response.png');

    // 7. Scroll to see full response
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'e2e5_04_scrolled.png', fullPage: true });
    console.log('   Screenshot: e2e5_04_scrolled.png');

    console.log('\n✅ Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'e2e5_error.png' });
  } finally {
    await browser.close();
  }
})();
