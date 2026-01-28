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
    console.log('3. Entering query: hidbmgr에 대해서 알려줘');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('hidbmgr에 대해서 알려줘');
    await textarea.press('Enter');

    // 4. Wait for clarification dialog or direct response
    console.log('4. Waiting for response...');
    await page.waitForTimeout(8000);
    await page.screenshot({ path: 'hidbmgr_01_initial.png' });

    // 5. Check for clarification dialog and handle if present
    const clarificationDialog = await page.locator('text=agent.clarification.search').first();
    if (await clarificationDialog.count() > 0) {
      console.log('5. Clarification dialog detected, clicking first option...');
      const firstOption = await page.locator('[class*="option"], [class*="card"]').first();
      if (await firstOption.count() > 0) {
        await firstOption.click();
      }
      await page.waitForTimeout(500);
      await clarificationDialog.click();
      console.log('   Clicked search button');
    }

    // 6. Wait for search and response
    console.log('6. Waiting for response...');
    for (let i = 1; i <= 6; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `hidbmgr_response_${i * 5}s.png` });
      console.log(`   Screenshot: hidbmgr_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 7. Try to close modal if present
    console.log('7. Closing modal if present...');
    const closeBtn = await page.locator('text=閉じる, button:has-text("閉")').first();
    if (await closeBtn.count() > 0) {
      await closeBtn.click();
      await page.waitForTimeout(2000);
    }

    // 8. Final screenshots
    await page.screenshot({ path: 'hidbmgr_final.png', fullPage: true });
    console.log('   Screenshot: hidbmgr_final.png');

    // 9. Scroll down to see full response
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'hidbmgr_scrolled.png', fullPage: true });
    console.log('   Screenshot: hidbmgr_scrolled.png');

    console.log('\n✅ E2E hidbmgr Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'hidbmgr_error.png' });
  } finally {
    await browser.close();
  }
})();
