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
    console.log('3. Entering query: tacfmgr에 대해서 알려줘');
    const textarea = await page.locator('textarea').first();
    await textarea.fill('tacfmgr에 대해서 알려줘');
    await textarea.press('Enter');

    // 4. Wait for clarification dialog
    console.log('4. Waiting for clarification dialog...');
    await page.waitForTimeout(10000);
    await page.screenshot({ path: 'tacfmgr_01_dialog.png' });

    // 5. Click on first option
    console.log('5. Selecting option...');
    const optionTexts = ['설명', 'tacfmgr', '명령어', '기능'];
    let clicked = false;
    for (const optText of optionTexts) {
      const opt = await page.locator(`text=${optText}`).first();
      if (await opt.count() > 0) {
        await opt.click();
        console.log(`   Clicked option: ${optText}`);
        clicked = true;
        break;
      }
    }
    if (!clicked) {
      const anyCard = await page.locator('div[class*="cursor-pointer"]').first();
      if (await anyCard.count() > 0) {
        await anyCard.click();
        console.log('   Clicked first card');
      }
    }

    await page.waitForTimeout(1000);

    // 6. Click search button
    console.log('6. Clicking search button...');
    const searchBtn = await page.locator('button:has-text("agent.clarification.search"), button:has-text("검색"), button:has-text("Search")').first();
    if (await searchBtn.count() > 0) {
      await page.waitForTimeout(500);
      try {
        await searchBtn.click({ timeout: 5000 });
        console.log('   Clicked search button');
      } catch (e) {
        console.log('   Search button click failed');
      }
    }

    // 7. Wait for response
    console.log('7. Waiting for response...');
    for (let i = 1; i <= 8; i++) {
      await page.waitForTimeout(5000);
      await page.screenshot({ path: `tacfmgr_response_${i * 5}s.png` });
      console.log(`   Screenshot: tacfmgr_response_${i * 5}s.png (${i * 5}s)`);
    }

    // 8. Close modal if present
    console.log('8. Closing modal...');
    const closeBtn = await page.locator('button:has-text("閉じる"), button:has-text("閉")').first();
    if (await closeBtn.count() > 0) {
      await closeBtn.click();
      await page.waitForTimeout(2000);
    }

    // 9. Final screenshot
    await page.screenshot({ path: 'tacfmgr_final.png', fullPage: true });
    console.log('   Screenshot: tacfmgr_final.png');

    // 10. Scroll down to see full response
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'tacfmgr_scrolled.png', fullPage: true });
    console.log('   Screenshot: tacfmgr_scrolled.png');

    console.log('\n✅ E2E tacfmgr Test completed!');

  } catch (error) {
    console.error('❌ Error:', error.message);
    await page.screenshot({ path: 'tacfmgr_error.png' });
  } finally {
    await browser.close();
  }
})();
