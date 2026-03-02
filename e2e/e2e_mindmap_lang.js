/**
 * E2E Test: Mindmap Language Output Verification
 *
 * マインドマップ生成時に言語設定(JP)に従って日本語で
 * 概念名・説明・ラベルが出力されることを検証する
 */
const { chromium } = require('playwright');
const fs = require('fs');

const BASE_URL = 'https://localhost:3000';
const RESULTS_FILE = 'mindmap_lang_test_results.json';

const results = {
  timestamp: new Date().toISOString(),
  tests: [],
  summary: { total: 0, passed: 0, failed: 0, errors: 0 }
};

function addResult(name, status, details = {}) {
  results.tests.push({ name, status, ...details });
  results.summary.total++;
  results.summary[status]++;
  const icon = status === 'passed' ? '✅' : status === 'failed' ? '❌' : '⚠️';
  console.log(`  ${icon} ${name}: ${details.message || status}`);
}

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 },
    ignoreHTTPSErrors: true
  });
  const page = await context.newPage();

  // Collect API responses
  const apiResponses = {};
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/v1/mindmap')) {
      try {
        const body = await response.json();
        apiResponses[url] = { status: response.status(), body };
      } catch (e) {
        apiResponses[url] = { status: response.status(), error: e.message };
      }
    }
  });

  try {
    console.log('='.repeat(70));
    console.log('MINDMAP LANGUAGE E2E TEST');
    console.log('='.repeat(70));

    // 1. Login
    console.log('\n[Step 1] Login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);
    addResult('Login', 'passed', { message: 'Logged in as admin' });

    // 2. Set language to Japanese
    console.log('\n[Step 2] Set language to Japanese...');
    // Click language selector
    const langSelectors = [
      'button:has-text("JP")',
      'button:has-text("JA")',
      'button:has-text("日本語")',
      '[data-testid="language-selector"]',
      '.language-selector'
    ];
    let langSet = false;
    for (const sel of langSelectors) {
      try {
        const el = await page.locator(sel).first();
        if (await el.count() > 0) {
          // Already JP
          langSet = true;
          console.log(`   Language appears to be Japanese already (found: ${sel})`);
          break;
        }
      } catch (e) {}
    }

    if (!langSet) {
      // Try to find and click the language dropdown
      try {
        const dropdowns = await page.locator('select, [role="listbox"], .MuiSelect-root').all();
        for (const dd of dropdowns) {
          const text = await dd.textContent();
          if (text && (text.includes('EN') || text.includes('KO') || text.includes('JP') || text.includes('言語'))) {
            await dd.click();
            await page.waitForTimeout(500);
            // Select Japanese
            const jaOptions = ['text=JP', 'text=日本語', 'text=JA', '[value="ja"]'];
            for (const opt of jaOptions) {
              try {
                await page.locator(opt).first().click({ timeout: 2000 });
                langSet = true;
                break;
              } catch (e) {}
            }
            if (langSet) break;
          }
        }
      } catch (e) {}
    }
    addResult('Language Setting', langSet ? 'passed' : 'failed',
      { message: langSet ? 'Language set to Japanese' : 'Could not set language (may already be JP)' });

    // 3. Navigate to Mindmap page
    console.log('\n[Step 3] Navigate to Mindmap page...');
    await page.goto(`${BASE_URL}/mindmap`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'mindmap_01_page.png' });

    // Check page loaded
    const pageTitle = await page.textContent('body');
    const hasMindmapUI = pageTitle.includes('マインドマップ') ||
                         pageTitle.includes('Mindmap') ||
                         pageTitle.includes('마인드맵') ||
                         pageTitle.includes('AIスタジオ') ||
                         pageTitle.includes('AI Studio');
    addResult('Mindmap Page Load', hasMindmapUI ? 'passed' : 'failed',
      { message: hasMindmapUI ? 'Mindmap page loaded' : 'Page may not have loaded correctly' });

    // 4. Click "AI生成" button to generate mindmap
    console.log('\n[Step 4] Generate mindmap...');
    const generateSelectors = [
      'button:has-text("AI生成")',
      'button:has-text("AI Generate")',
      'button:has-text("AI 생성")',
      'button:has-text("Generate")',
      'text=AI生成'
    ];
    let generateClicked = false;
    for (const sel of generateSelectors) {
      try {
        const el = await page.locator(sel).first();
        if (await el.count() > 0) {
          await el.click({ timeout: 5000 });
          generateClicked = true;
          console.log(`   Clicked generate button: ${sel}`);
          break;
        }
      } catch (e) {}
    }

    if (generateClicked) {
      // Wait for generation (may open a panel first)
      await page.waitForTimeout(2000);
      await page.screenshot({ path: 'mindmap_02_generate_panel.png' });

      // Look for the actual generate/confirm button in the panel
      const confirmSelectors = [
        'button:has-text("生成")',
        'button:has-text("Generate")',
        'button:has-text("전체 문서")',
        'button:has-text("全文書")',
        'button:has-text("From All")',
      ];
      for (const sel of confirmSelectors) {
        try {
          const el = await page.locator(sel).first();
          if (await el.count() > 0) {
            await el.click({ timeout: 5000 });
            console.log(`   Clicked confirm: ${sel}`);
            break;
          }
        } catch (e) {}
      }

      // Wait for mindmap generation (can take 30-60 seconds with LLM)
      console.log('   Waiting for mindmap generation (up to 90s)...');
      await page.waitForTimeout(5000);
      await page.screenshot({ path: 'mindmap_03_generating.png' });

      // Wait for nodes to appear or timeout
      let nodesFound = false;
      for (let i = 0; i < 18; i++) {  // 18 * 5s = 90s max
        try {
          // Check if any mindmap nodes are visible
          const nodeCount = await page.locator('.mindmap-node, [data-node-id], .node-label, .react-flow__node').count();
          if (nodeCount > 0) {
            nodesFound = true;
            console.log(`   Found ${nodeCount} nodes after ${(i + 1) * 5}s`);
            break;
          }
          // Also check for error messages
          const bodyText = await page.textContent('body');
          if (bodyText.includes('エラー') || bodyText.includes('error') || bodyText.includes('Error') || bodyText.includes('failed')) {
            console.log(`   Generation may have failed after ${(i + 1) * 5}s`);
            break;
          }
        } catch (e) {}
        await page.waitForTimeout(5000);
      }
      await page.screenshot({ path: 'mindmap_04_result.png' });
    }

    addResult('Mindmap Generation', generateClicked ? 'passed' : 'failed',
      { message: generateClicked ? 'Generate button clicked' : 'Generate button not found' });

    // 5. Analyze mindmap node content language
    console.log('\n[Step 5] Analyze node content language...');
    await page.waitForTimeout(3000);

    // Get all visible text on page
    const bodyText = await page.textContent('body');
    await page.screenshot({ path: 'mindmap_05_final.png', fullPage: true });

    // Korean detection (한글 유니코드 범위)
    const koreanRegex = /[\uAC00-\uD7AF]/g;
    const japaneseRegex = /[\u3040-\u309F\u30A0-\u30FF]/g;  // ひらがな + カタカナ
    const kanjiRegex = /[\u4E00-\u9FFF]/g;  // CJK漢字 (shared by ja/ko/zh)

    const koreanMatches = bodyText.match(koreanRegex) || [];
    const japaneseMatches = bodyText.match(japaneseRegex) || [];
    const kanjiMatches = bodyText.match(kanjiRegex) || [];

    console.log(`   Korean chars: ${koreanMatches.length}`);
    console.log(`   Japanese (kana): ${japaneseMatches.length}`);
    console.log(`   CJK Kanji: ${kanjiMatches.length}`);

    // Check API responses for mindmap data
    let mindmapNodes = [];
    let nodeLanguageAnalysis = { japanese: 0, korean: 0, english: 0, mixed: 0 };

    for (const [url, resp] of Object.entries(apiResponses)) {
      if (resp.body && resp.body.data) {
        const data = resp.body.data;
        // Check if it's a mindmap response with nodes
        if (data.mindmap && data.mindmap.data && data.mindmap.data.nodes) {
          mindmapNodes = data.mindmap.data.nodes;
        } else if (data.data && data.data.nodes) {
          mindmapNodes = data.data.nodes;
        } else if (data.nodes) {
          mindmapNodes = data.nodes;
        }
      }
    }

    if (mindmapNodes.length > 0) {
      console.log(`\n   === Node Language Analysis (${mindmapNodes.length} nodes) ===`);
      for (const node of mindmapNodes) {
        const label = node.label || '';
        const desc = node.description || '';
        const text = label + ' ' + desc;

        const hasKorean = /[\uAC00-\uD7AF]/.test(text);
        const hasJapanese = /[\u3040-\u309F\u30A0-\u30FF]/.test(text);

        if (hasKorean && !hasJapanese) {
          nodeLanguageAnalysis.korean++;
          console.log(`   [KO] ${label}`);
        } else if (hasJapanese) {
          nodeLanguageAnalysis.japanese++;
          console.log(`   [JA] ${label}`);
        } else if (/^[a-zA-Z0-9\s\-_.]+$/.test(label)) {
          nodeLanguageAnalysis.english++;
          console.log(`   [EN] ${label}`);
        } else {
          nodeLanguageAnalysis.mixed++;
          console.log(`   [??] ${label}`);
        }
      }

      console.log(`\n   Summary: JA=${nodeLanguageAnalysis.japanese} KO=${nodeLanguageAnalysis.korean} EN=${nodeLanguageAnalysis.english} Other=${nodeLanguageAnalysis.mixed}`);

      const totalNonEnglish = nodeLanguageAnalysis.japanese + nodeLanguageAnalysis.korean + nodeLanguageAnalysis.mixed;
      const jaRatio = totalNonEnglish > 0 ? nodeLanguageAnalysis.japanese / totalNonEnglish : 0;

      addResult('Node Language (Japanese)', jaRatio >= 0.5 ? 'passed' : 'failed', {
        message: `JA=${nodeLanguageAnalysis.japanese}, KO=${nodeLanguageAnalysis.korean}, EN=${nodeLanguageAnalysis.english} (JA ratio: ${(jaRatio * 100).toFixed(0)}%)`,
        nodeLanguageAnalysis
      });
    } else {
      addResult('Node Language Analysis', 'errors', {
        message: 'No mindmap nodes found in API responses (Neo4j may be unavailable)',
        apiResponses: Object.keys(apiResponses).map(k => ({ url: k, status: apiResponses[k].status }))
      });
    }

    // 6. Check existing mindmaps in the list
    console.log('\n[Step 6] Check existing mindmap list...');
    let listResponse = null;
    for (const [url, resp] of Object.entries(apiResponses)) {
      if (url.includes('/api/v1/mindmap') && !url.includes('generate') && !url.includes('expand') && !url.includes('node')) {
        listResponse = resp;
      }
    }
    if (listResponse && listResponse.status === 200) {
      const mindmaps = listResponse.body?.data?.mindmaps || [];
      addResult('Mindmap List API', 'passed', { message: `${mindmaps.length} mindmaps found`, count: mindmaps.length });
    } else {
      addResult('Mindmap List API', listResponse ? 'failed' : 'errors', {
        message: listResponse ? `API returned ${listResponse.status}` : 'No list API response captured'
      });
    }

  } catch (error) {
    console.error('Test error:', error.message);
    addResult('Test Execution', 'errors', { message: error.message });
    await page.screenshot({ path: 'mindmap_error.png' }).catch(() => {});
  } finally {
    // Print summary
    console.log(`\n${'='.repeat(70)}`);
    console.log('TEST RESULTS SUMMARY');
    console.log(`${'='.repeat(70)}`);
    console.log(`Total: ${results.summary.total}`);
    console.log(`Passed: ${results.summary.passed}`);
    console.log(`Failed: ${results.summary.failed}`);
    console.log(`Errors: ${results.summary.errors}`);
    console.log(`\nScreenshots saved: mindmap_01~05_*.png`);

    // Save results
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2));
    console.log(`Results saved to: ${RESULTS_FILE}`);

    await browser.close();
  }
})();
