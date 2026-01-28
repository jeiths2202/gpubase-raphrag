const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Load keywords
const keywordsData = JSON.parse(fs.readFileSync(path.join(__dirname, 'keywords.json'), 'utf-8'));
const keywords = keywordsData.keywords;

// Results storage
const results = {
  total: 0,
  passed: 0,
  failed: 0,
  hallucinations: [],
  errors: [],
  timestamp: new Date().toISOString()
};

// Known similar product patterns that should NOT appear together
const SIMILAR_PRODUCTS = {
  'hidbmgr': ['ndbmgr', 'odbmgr'],
  'ndbmgr': ['hidbmgr', 'odbmgr'],
  'tacfmgr': ['volmgr', 'catmgr'],
  'volmgr': ['tacfmgr', 'catmgr'],
  'tjesmgr': ['oscmgr', 'osimgr'],
  'oscmgr': ['tjesmgr', 'osimgr'],
  'osimgr': ['tjesmgr', 'oscmgr'],
};

// Check for hallucination
function checkHallucination(keyword, responseText) {
  const keywordLower = keyword.toLowerCase();
  const responseLower = responseText.toLowerCase();

  // Check if response contains the keyword
  const containsKeyword = responseLower.includes(keywordLower);

  // Check for similar but different products
  const similarProducts = SIMILAR_PRODUCTS[keywordLower] || [];
  const foundSimilar = [];

  for (const similar of similarProducts) {
    if (responseLower.includes(similar) && !responseLower.includes(keywordLower)) {
      foundSimilar.push(similar);
    }
  }

  // Check for completely unrelated content
  // If searching for a *mgr command, the response should mention it
  const isMgrCommand = keywordLower.endsWith('mgr');
  const responseHasOtherMgr = responseLower.match(/\b[a-z]+mgr\b/g) || [];
  const otherMgrCommands = responseHasOtherMgr.filter(m => m !== keywordLower);

  return {
    containsKeyword,
    foundSimilar,
    otherMgrCommands: isMgrCommand ? otherMgrCommands : [],
    isHallucination: foundSimilar.length > 0 || (isMgrCommand && otherMgrCommands.length > 0 && !containsKeyword)
  };
}

async function runTest(page, keyword, index) {
  console.log(`\n[${index}/${keywords.length}] Testing: "${keyword}"`);

  try {
    // Clear previous chat if possible
    const clearBtn = await page.locator('text=履歴をクリア').first();
    if (await clearBtn.count() > 0) {
      try {
        await clearBtn.click({ timeout: 2000 });
        await page.waitForTimeout(1000);
      } catch (e) { }
    }

    // Enter query
    const textarea = await page.locator('textarea').first();
    await textarea.fill(`${keyword}에 대해서 알려줘`);
    await textarea.press('Enter');

    // Wait for clarification dialog or direct response
    await page.waitForTimeout(8000);

    // Check for clarification dialog and handle
    const clarificationBtn = await page.locator('button:has-text("agent.clarification.search"), button:has-text("검색")').first();
    if (await clarificationBtn.count() > 0) {
      // Try to click first option
      const optionTexts = ['설명', keyword, '명령어', '기능'];
      for (const optText of optionTexts) {
        const opt = await page.locator(`text=${optText}`).first();
        if (await opt.count() > 0) {
          try {
            await opt.click({ timeout: 2000 });
            break;
          } catch (e) { }
        }
      }
      await page.waitForTimeout(500);

      // Click search button
      try {
        await clarificationBtn.click({ timeout: 3000 });
      } catch (e) { }
    }

    // Wait for response
    await page.waitForTimeout(15000);

    // Close modal if present
    const closeBtn = await page.locator('button:has-text("閉じる")').first();
    if (await closeBtn.count() > 0) {
      try {
        await closeBtn.click({ timeout: 2000 });
        await page.waitForTimeout(1000);
      } catch (e) { }
    }

    // Get response text
    const responseElements = await page.locator('.prose, [class*="markdown"], [class*="response"], [class*="answer"]').all();
    let responseText = '';
    for (const el of responseElements) {
      try {
        responseText += await el.textContent() + '\n';
      } catch (e) { }
    }

    // Also get text from the main content area
    try {
      const mainContent = await page.locator('main, [class*="chat"], [class*="message"]').first();
      if (await mainContent.count() > 0) {
        responseText += await mainContent.textContent();
      }
    } catch (e) { }

    // Check for hallucination
    const hallucinationCheck = checkHallucination(keyword, responseText);

    if (hallucinationCheck.isHallucination) {
      console.log(`  ❌ HALLUCINATION DETECTED!`);
      if (hallucinationCheck.foundSimilar.length > 0) {
        console.log(`     Found similar products: ${hallucinationCheck.foundSimilar.join(', ')}`);
      }
      if (hallucinationCheck.otherMgrCommands.length > 0) {
        console.log(`     Found other *mgr commands: ${hallucinationCheck.otherMgrCommands.join(', ')}`);
      }

      // Take screenshot
      const screenshotPath = `hallucination_${index}_${keyword.replace(/[^a-zA-Z0-9]/g, '_')}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log(`     Screenshot: ${screenshotPath}`);

      results.hallucinations.push({
        index,
        keyword,
        foundSimilar: hallucinationCheck.foundSimilar,
        otherMgrCommands: hallucinationCheck.otherMgrCommands,
        screenshot: screenshotPath
      });
      results.failed++;
    } else if (!hallucinationCheck.containsKeyword && responseText.includes('찾을 수 없습니다')) {
      console.log(`  ⚠️ No results found`);
      results.passed++; // Not a hallucination, just no data
    } else {
      console.log(`  ✅ PASSED`);
      results.passed++;
    }

    results.total++;

  } catch (error) {
    console.log(`  ❌ ERROR: ${error.message}`);
    results.errors.push({ index, keyword, error: error.message });
    results.failed++;
    results.total++;
  }
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  try {
    // Login
    console.log('Logging in...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);

    // Navigate to AI Agent page
    console.log('Navigating to AI Agent page...');
    await page.click('text=AIエージェント');
    await page.waitForTimeout(2000);

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Starting E2E Keyword Tests - ${keywords.length} keywords`);
    console.log(`${'='.repeat(60)}`);

    // Test first 50 keywords (for initial run)
    const testKeywords = keywords.slice(0, 50);

    for (let i = 0; i < testKeywords.length; i++) {
      await runTest(page, testKeywords[i], i + 1);

      // Save intermediate results every 10 tests
      if ((i + 1) % 10 === 0) {
        fs.writeFileSync('test_results.json', JSON.stringify(results, null, 2));
        console.log(`\n--- Progress: ${i + 1}/${testKeywords.length} ---`);
      }
    }

    // Final summary
    console.log(`\n${'='.repeat(60)}`);
    console.log('TEST SUMMARY');
    console.log(`${'='.repeat(60)}`);
    console.log(`Total: ${results.total}`);
    console.log(`Passed: ${results.passed}`);
    console.log(`Failed: ${results.failed}`);
    console.log(`Hallucinations: ${results.hallucinations.length}`);
    console.log(`Errors: ${results.errors.length}`);

    if (results.hallucinations.length > 0) {
      console.log(`\nHallucination Details:`);
      for (const h of results.hallucinations) {
        console.log(`  - [${h.index}] "${h.keyword}": found ${h.foundSimilar.join(', ') || h.otherMgrCommands.join(', ')}`);
      }
    }

    // Save final results
    fs.writeFileSync('test_results.json', JSON.stringify(results, null, 2));
    console.log(`\nResults saved to test_results.json`);

  } catch (error) {
    console.error('Fatal error:', error.message);
    await page.screenshot({ path: 'fatal_error.png' });
  } finally {
    await browser.close();
  }
})();
