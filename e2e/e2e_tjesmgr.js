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
    await page.screenshot({ path: 'tjesmgr_01_agent.png' });

    // 3. Enter query that works in CLI test
    console.log('3. Entering query: tjesmgr에 대해서 알려줘');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('tjesmgr에 대해서 알려줘');
    await textarea.press('Enter');

    // 4. Wait and capture progress
    console.log('4. Waiting for response...');
    for (let i = 1; i <= 8; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `tjesmgr_response_${i * 5}s.png` });
      console.log(`   Screenshot: tjesmgr_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 5. Full page screenshot
    await page.screenshot({ path: 'tjesmgr_final.png', fullPage: true });
    console.log('   Screenshot: tjesmgr_final.png');

    console.log('\n✅ E2E TJESMGR Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'tjesmgr_error.png' });
  } finally {
    await browser.close();
  }
})();
