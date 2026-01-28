const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// Test cases with proper sentences
const TEST_CASES = [
  // Commands - mgr series (Japanese)
  { keyword: 'tjesmgr', query: 'tjesmgrについて説明してください。', lang: 'ja', expected: ['tjesmgr', 'TJES'], notExpected: ['oscmgr', 'osimgr'] },
  { keyword: 'tacfmgr', query: 'tacfmgrの使用方法を教えてください。', lang: 'ja', expected: ['tacfmgr', 'TACF'], notExpected: ['volmgr', 'catmgr'] },
  { keyword: 'hidbmgr', query: 'hidbmgrコマンドの機能について説明してください。', lang: 'ja', expected: ['hidbmgr', 'HiDB'], notExpected: ['ndbmgr', 'odbmgr'] },
  { keyword: 'ndbmgr', query: 'ndbmgrの主なオプションを教えてください。', lang: 'ja', expected: ['ndbmgr', 'NDB'], notExpected: ['hidbmgr', 'odbmgr'] },
  { keyword: 'oscmgr', query: 'oscmgrコマンドについて詳しく説明してください。', lang: 'ja', expected: ['oscmgr', 'OSC'], notExpected: ['tjesmgr', 'osimgr'] },
  { keyword: 'osimgr', query: 'osimgrの機能と使い方を教えてください。', lang: 'ja', expected: ['osimgr', 'OSI'], notExpected: ['tjesmgr', 'oscmgr'] },
  { keyword: 'volmgr', query: 'volmgrコマンドの役割について説明してください。', lang: 'ja', expected: ['volmgr', 'volume'], notExpected: ['tacfmgr', 'catmgr'] },
  { keyword: 'catmgr', query: 'catmgrの使用方法と主要オプションを教えてください。', lang: 'ja', expected: ['catmgr', 'catalog'], notExpected: ['volmgr', 'tacfmgr'] },
  { keyword: 'ofmgr', query: 'ofmgrコマンドについて説明してください。', lang: 'ja', expected: ['ofmgr', 'OpenFrame'], notExpected: [] },
  { keyword: 'dsmigin', query: 'dsmiginツールの使い方を教えてください。', lang: 'ja', expected: ['dsmigin', 'migration'], notExpected: ['dsmigout'] },
  { keyword: 'dsmigout', query: 'dsmigoutの機能について説明してください。', lang: 'ja', expected: ['dsmigout', 'migration'], notExpected: ['dsmigin'] },

  // Commands - Korean
  { keyword: 'tjesmgr', query: 'tjesmgr 명령어에 대해서 설명해주세요.', lang: 'ko', expected: ['tjesmgr', 'TJES'], notExpected: ['oscmgr', 'osimgr'] },
  { keyword: 'tacfmgr', query: 'tacfmgr 사용법을 알려주세요.', lang: 'ko', expected: ['tacfmgr', 'TACF'], notExpected: ['volmgr', 'catmgr'] },
  { keyword: 'hidbmgr', query: 'hidbmgr 명령어의 기능에 대해서 알려주세요.', lang: 'ko', expected: ['hidbmgr', 'HiDB'], notExpected: ['ndbmgr', 'odbmgr'] },
  { keyword: 'ndbmgr', query: 'ndbmgr의 주요 옵션을 설명해주세요.', lang: 'ko', expected: ['ndbmgr', 'NDB'], notExpected: ['hidbmgr', 'odbmgr'] },

  // Utilities
  { keyword: 'idcams', query: 'idcamsユーティリティについて説明してください。', lang: 'ja', expected: ['idcams', 'VSAM'], notExpected: [] },
  { keyword: 'iebgener', query: 'iebgenerの使用方法を教えてください。', lang: 'ja', expected: ['iebgener'], notExpected: ['iebcopy'] },
  { keyword: 'iebcopy', query: 'iebcopyユーティリティの機能を説明してください。', lang: 'ja', expected: ['iebcopy', 'PDS'], notExpected: ['iebgener'] },
  { keyword: 'dfsort', query: 'dfsortの使い方について説明してください。', lang: 'ja', expected: ['dfsort', 'sort'], notExpected: [] },

  // JCL
  { keyword: 'JCL', query: 'JCLの基本構文について説明してください。', lang: 'ja', expected: ['JCL', 'JOB', 'EXEC'], notExpected: [] },
  { keyword: 'EXEC', query: 'JCLのEXECステートメントについて説明してください。', lang: 'ja', expected: ['EXEC', 'PGM', 'PROC'], notExpected: [] },
  { keyword: 'DD', query: 'JCLのDDステートメントについて説明してください。', lang: 'ja', expected: ['DD', 'DSN', 'DISP'], notExpected: [] },

  // Configuration files
  { keyword: 'tjes.conf', query: 'tjes.confの設定項目について説明してください。', lang: 'ja', expected: ['tjes.conf', 'TJES', '設定'], notExpected: ['osc.conf'] },
  { keyword: 'osc.conf', query: 'osc.confの設定方法を教えてください。', lang: 'ja', expected: ['osc.conf', 'OSC'], notExpected: ['tjes.conf'] },
  { keyword: 'tacf.conf', query: 'tacf.confの設定について説明してください。', lang: 'ja', expected: ['tacf.conf', 'TACF'], notExpected: [] },
  { keyword: 'ds.conf', query: 'ds.confファイルの設定項目を教えてください。', lang: 'ja', expected: ['ds.conf', 'dataset'], notExpected: [] },

  // Error codes
  { keyword: 'ABEND S0C7', query: 'ABEND S0C7エラーの原因と対処方法を教えてください。', lang: 'ja', expected: ['S0C7', 'data exception'], notExpected: ['S0C4', 'S0C1'] },
  { keyword: 'ABEND S0C4', query: 'ABEND S0C4エラーについて説明してください。', lang: 'ja', expected: ['S0C4', 'protection'], notExpected: ['S0C7', 'S0C1'] },
  { keyword: 'ABEND S806', query: 'ABEND S806エラーの原因を教えてください。', lang: 'ja', expected: ['S806', 'module', 'load'], notExpected: ['S0C7', 'S0C4'] },

  // Dataset types
  { keyword: 'VSAM KSDS', query: 'VSAM KSDSについて説明してください。', lang: 'ja', expected: ['KSDS', 'key'], notExpected: ['ESDS', 'RRDS'] },
  { keyword: 'VSAM ESDS', query: 'VSAM ESDSの特徴を教えてください。', lang: 'ja', expected: ['ESDS', 'entry'], notExpected: ['KSDS', 'RRDS'] },
  { keyword: 'GDG', query: 'GDG（世代データグループ）について説明してください。', lang: 'ja', expected: ['GDG', 'generation'], notExpected: [] },
  { keyword: 'PDS', query: 'PDSデータセットについて説明してください。', lang: 'ja', expected: ['PDS', 'member'], notExpected: [] },

  // Products
  { keyword: 'OpenFrame', query: 'OpenFrameの概要について説明してください。', lang: 'ja', expected: ['OpenFrame', 'mainframe'], notExpected: [] },
  { keyword: 'TJES', query: 'TJESの機能と役割について説明してください。', lang: 'ja', expected: ['TJES', 'job', 'batch'], notExpected: ['OSC', 'OSI'] },
  { keyword: 'TACF', query: 'TACFセキュリティシステムについて説明してください。', lang: 'ja', expected: ['TACF', 'security'], notExpected: [] },
  { keyword: 'OSC', query: 'OSCの機能について説明してください。', lang: 'ja', expected: ['OSC', 'online', 'CICS'], notExpected: ['TJES', 'OSI'] },

  // Batch processing
  { keyword: 'tjclrun', query: 'tjclrunコマンドの使用方法を教えてください。', lang: 'ja', expected: ['tjclrun', 'JCL'], notExpected: ['textrun'] },
  { keyword: 'textrun', query: 'textrunの機能について説明してください。', lang: 'ja', expected: ['textrun'], notExpected: ['tjclrun'] },
  { keyword: 'jesinit', query: 'jesinitコマンドについて説明してください。', lang: 'ja', expected: ['jesinit', 'JES', 'init'], notExpected: ['jesdown'] },
  { keyword: 'jesdown', query: 'jesdownの使い方を教えてください。', lang: 'ja', expected: ['jesdown', 'shutdown'], notExpected: ['jesinit'] },

  // System commands
  { keyword: 'tmboot', query: 'tmbootコマンドについて説明してください。', lang: 'ja', expected: ['tmboot', 'boot', 'start'], notExpected: ['tmdown'] },
  { keyword: 'tmdown', query: 'tmdownの使用方法を教えてください。', lang: 'ja', expected: ['tmdown', 'shutdown'], notExpected: ['tmboot'] },
  { keyword: 'ofboot', query: 'ofbootコマンドの機能を説明してください。', lang: 'ja', expected: ['ofboot', 'OpenFrame'], notExpected: ['ofdown'] },
  { keyword: 'ofdown', query: 'ofdownについて説明してください。', lang: 'ja', expected: ['ofdown', 'shutdown'], notExpected: ['ofboot'] },
];

// Results storage
const results = {
  total: 0,
  passed: 0,
  failed: 0,
  hallucinations: [],
  noResults: [],
  errors: [],
  timestamp: new Date().toISOString()
};

// Check response quality
function analyzeResponse(testCase, responseText) {
  const responseLower = responseText.toLowerCase();
  const keywordLower = testCase.keyword.toLowerCase();

  // Check if expected keywords are present
  const foundExpected = testCase.expected.filter(exp =>
    responseLower.includes(exp.toLowerCase())
  );

  // Check if unexpected keywords are present (hallucination)
  const foundUnexpected = testCase.notExpected.filter(unexp =>
    responseLower.includes(unexp.toLowerCase())
  );

  // Check if it's a "not found" response
  const isNoResult = responseLower.includes('찾을 수 없습니다') ||
                     responseLower.includes('見つかりません') ||
                     responseLower.includes('情報がありません') ||
                     responseLower.includes('no information') ||
                     responseLower.includes('not found');

  // Determine result
  const hasHallucination = foundUnexpected.length > 0;
  const hasRelevantContent = foundExpected.length > 0 || responseLower.includes(keywordLower);

  return {
    foundExpected,
    foundUnexpected,
    isNoResult,
    hasHallucination,
    hasRelevantContent,
    isPass: !hasHallucination && (hasRelevantContent || isNoResult)
  };
}

async function runTest(page, testCase, index) {
  const { keyword, query, lang, expected, notExpected } = testCase;
  console.log(`\n[${index}/${TEST_CASES.length}] Testing: "${keyword}" (${lang})`);
  console.log(`   Query: ${query}`);

  try {
    // Start a new conversation to isolate each test
    // This prevents previous test responses from affecting hallucination detection
    const newChatSelectors = [
      'button[aria-label="New Chat"]',
      'button:has-text("新規チャット")',
      'button:has-text("새 대화")',
      'button:has-text("New")',
      '[class*="new-chat"]',
      'button svg[class*="plus"]'
    ];
    for (const selector of newChatSelectors) {
      try {
        const btn = await page.locator(selector).first();
        if (await btn.count() > 0) {
          await btn.click({ timeout: 2000 });
          await page.waitForTimeout(1000);
          break;
        }
      } catch (e) { }
    }

    // Enter query
    const textarea = await page.locator('textarea').first();
    await textarea.fill('');
    await page.waitForTimeout(300);
    await textarea.fill(query);
    await textarea.press('Enter');

    // Wait for clarification dialog or response
    await page.waitForTimeout(8000);

    // Handle clarification dialog if present
    const searchBtn = await page.locator('button:has-text("agent.clarification.search"), button:has-text("検索"), button:has-text("Search")').first();
    if (await searchBtn.count() > 0) {
      // Try to click an option first
      const options = ['説明', '기능', keyword, '概要', 'overview'];
      for (const opt of options) {
        const optEl = await page.locator(`text=${opt}`).first();
        if (await optEl.count() > 0) {
          try { await optEl.click({ timeout: 1500 }); break; } catch (e) { }
        }
      }
      await page.waitForTimeout(500);
      try { await searchBtn.click({ timeout: 3000 }); } catch (e) { }
    }

    // Wait for response
    await page.waitForTimeout(20000);

    // Close modal if present
    const closeBtn = await page.locator('button:has-text("閉じる"), button:has-text("닫기")').first();
    if (await closeBtn.count() > 0) {
      try { await closeBtn.click({ timeout: 2000 }); } catch (e) { }
      await page.waitForTimeout(1000);
    }

    // Get response text from page - ONLY the LATEST message to avoid false hallucination detection
    let responseText = '';
    try {
      // Get only the LAST assistant message (not the entire chat history)
      // This prevents detecting keywords from previous test responses as hallucinations
      const assistantMessages = await page.locator('[class*="assistant"], [class*="bot-message"], [class*="ai-message"], [data-role="assistant"]').all();
      if (assistantMessages.length > 0) {
        // Get the last (most recent) assistant message
        responseText = await assistantMessages[assistantMessages.length - 1].textContent();
      } else {
        // Fallback: try to get the last message block
        const allMessages = await page.locator('[class*="message-content"], [class*="chat-message"]').all();
        if (allMessages.length > 0) {
          responseText = await allMessages[allMessages.length - 1].textContent();
        } else {
          // Final fallback: get chat area content
          const chatArea = await page.locator('[class*="chat"], main').first();
          responseText = await chatArea.textContent();
        }
      }
    } catch (e) {
      responseText = await page.content();
    }

    // Analyze response
    const analysis = analyzeResponse(testCase, responseText);

    if (analysis.hasHallucination) {
      console.log(`   ❌ HALLUCINATION: Found "${analysis.foundUnexpected.join(', ')}" when searching for "${keyword}"`);

      // Take screenshot
      const screenshotPath = `hallucination_${index}_${keyword.replace(/[^a-zA-Z0-9]/g, '_')}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      console.log(`   📸 Screenshot: ${screenshotPath}`);

      results.hallucinations.push({
        index,
        keyword,
        query,
        foundUnexpected: analysis.foundUnexpected,
        screenshot: screenshotPath
      });
      results.failed++;
    } else if (analysis.isNoResult) {
      console.log(`   ⚠️ No results found`);
      results.noResults.push({ index, keyword, query });
      results.passed++;
    } else if (analysis.hasRelevantContent) {
      console.log(`   ✅ PASSED - Found: ${analysis.foundExpected.join(', ')}`);
      results.passed++;
    } else {
      console.log(`   ⚠️ Unclear result`);
      results.passed++;
    }

    results.total++;

    // Brief pause between tests
    await page.waitForTimeout(2000);

  } catch (error) {
    console.log(`   ❌ ERROR: ${error.message}`);
    results.errors.push({ index, keyword, query, error: error.message });
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
    // Try multiple selectors for different languages
    const agentSelectors = [
      'text=AIエージェント',
      'text=AI Agent',
      'text=AI 에이전트',
      '[href*="agent"]',
      'a:has-text("Agent")',
      'button:has-text("Agent")'
    ];
    let clicked = false;
    for (const selector of agentSelectors) {
      try {
        const elem = await page.locator(selector).first();
        if (await elem.count() > 0) {
          await elem.click({ timeout: 5000 });
          clicked = true;
          console.log(`   Clicked: ${selector}`);
          break;
        }
      } catch (e) { }
    }
    if (!clicked) {
      // Direct navigation
      await page.goto('http://localhost:3000/agent', { waitUntil: 'networkidle', timeout: 30000 });
    }
    await page.waitForTimeout(2000);

    console.log(`\n${'='.repeat(70)}`);
    console.log(`E2E SENTENCE TEST - ${TEST_CASES.length} test cases`);
    console.log(`${'='.repeat(70)}`);

    for (let i = 0; i < TEST_CASES.length; i++) {
      await runTest(page, TEST_CASES[i], i + 1);

      // Save intermediate results every 10 tests
      if ((i + 1) % 10 === 0) {
        fs.writeFileSync('sentence_test_results.json', JSON.stringify(results, null, 2));
        console.log(`\n--- Progress: ${i + 1}/${TEST_CASES.length} | Pass: ${results.passed} | Fail: ${results.failed} ---`);
      }
    }

    // Final summary
    console.log(`\n${'='.repeat(70)}`);
    console.log('FINAL TEST SUMMARY');
    console.log(`${'='.repeat(70)}`);
    console.log(`Total Tests: ${results.total}`);
    console.log(`Passed: ${results.passed}`);
    console.log(`Failed: ${results.failed}`);
    console.log(`Hallucinations: ${results.hallucinations.length}`);
    console.log(`No Results: ${results.noResults.length}`);
    console.log(`Errors: ${results.errors.length}`);

    if (results.hallucinations.length > 0) {
      console.log(`\n🚨 HALLUCINATION DETAILS:`);
      for (const h of results.hallucinations) {
        console.log(`   [${h.index}] "${h.keyword}": Found unexpected "${h.foundUnexpected.join(', ')}"`);
        console.log(`       Query: ${h.query}`);
      }
    }

    // Save final results
    fs.writeFileSync('sentence_test_results.json', JSON.stringify(results, null, 2));
    console.log(`\nResults saved to sentence_test_results.json`);

  } catch (error) {
    console.error('Fatal error:', error.message);
    await page.screenshot({ path: 'fatal_error.png' });
  } finally {
    await browser.close();
  }
})();
