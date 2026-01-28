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
    await page.screenshot({ path: 'verify_01_login.png' });
    console.log('   Screenshot: verify_01_login.png');

    // 2. Navigate to AI Agent page
    console.log('2. Navigating to AI Agent page...');
    await page.click('text=AIエージェント');
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'verify_02_agent.png' });
    console.log('   Screenshot: verify_02_agent.png');

    // 3. Enter a simple query that should return results directly
    console.log('3. Entering query...');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('OpenFrame 설치 방법');
    await textarea.press('Enter');

    // 4. Wait for clarification or response
    console.log('4. Waiting for response...');
    await page.waitForTimeout(8000);
    await page.screenshot({ path: 'verify_03_response.png' });
    console.log('   Screenshot: verify_03_response.png');

    // 5. Check if clarification dialog appeared
    const clarificationDialog = await page.locator('text=agent.clarification.search, text=검색, text=Search').first();
    if (await clarificationDialog.count() > 0) {
      console.log('5. Clarification dialog detected, clicking first option...');

      // Click the first option card (whatever it is)
      const firstOption = await page.locator('[class*="option"], [class*="card"], [class*="cursor-pointer"]').first();
      if (await firstOption.count() > 0) {
        await firstOption.click();
        await page.waitForTimeout(500);
      }

      // Click search/proceed button
      const searchBtn = await page.locator('button:has-text("검색"), button:has-text("Search"), text=agent.clarification.search').first();
      if (await searchBtn.count() > 0) {
        await searchBtn.click();
        console.log('   Clicked search button');
      }
    }

    // 6. Wait for final response
    console.log('6. Waiting for final response...');
    for (let i = 1; i <= 6; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `verify_response_${i * 5}s.png` });
      console.log(`   Screenshot: verify_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 7. Full page screenshot
    await page.screenshot({ path: 'verify_final.png', fullPage: true });
    console.log('   Screenshot: verify_final.png');

    console.log('\n✅ E2E Verification Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'verify_error.png' });
  } finally {
    await browser.close();
  }
})();
