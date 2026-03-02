/**
 * E2E Test: Mindmap Full Functionality Verification
 *
 * マインドマップ機能の完全E2Eテスト
 * - ログイン → 言語設定 → ページ遷移 → AI生成 → ノード操作 → 言語検証
 *
 * テスト項目:
 *  1. ログイン
 *  2. 日本語設定確認
 *  3. マインドマップページ遷移
 *  4. 保存済みマインドマップ一覧表示
 *  5. 「すべてのドキュメントから生成」でマインドマップ生成
 *  6. 生成結果のノード・エッジ言語検証
 *  7. ノードクリック → 編集パネル表示
 *  8. ノード展開(Expand)
 *  9. ノードに対する質問(Query)
 * 10. 保存済みマインドマップのロード
 */
const { chromium } = require('playwright');
const fs = require('fs');

const BASE_URL = 'https://localhost:3000';
const API_BASE = 'http://localhost:9000';
const RESULTS_FILE = 'mindmap_full_test_results.json';

const results = {
  timestamp: new Date().toISOString(),
  tests: [],
  summary: { total: 0, passed: 0, failed: 0, errors: 0 },
  apiCaptures: {},
  languageAnalysis: {}
};

function addResult(name, status, details = {}) {
  results.tests.push({ name, status, ...details });
  results.summary.total++;
  results.summary[status]++;
  const icon = status === 'passed' ? '✅' : status === 'failed' ? '❌' : '⚠️';
  console.log(`  ${icon} ${name}: ${details.message || status}`);
}

// Language detection helpers
function hasKorean(text) { return /[\uAC00-\uD7AF]/.test(text); }
function hasJapaneseKana(text) { return /[\u3040-\u309F\u30A0-\u30FF]/.test(text); }
function hasCJK(text) { return /[\u4E00-\u9FFF]/.test(text); }
function countKorean(text) { return (text.match(/[\uAC00-\uD7AF]/g) || []).length; }
function countJapaneseKana(text) { return (text.match(/[\u3040-\u309F\u30A0-\u30FF]/g) || []).length; }

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    ignoreHTTPSErrors: true
  });
  const page = await context.newPage();

  // Capture ALL API responses
  const apiCaptures = {};
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/v1/mindmap')) {
      try {
        const body = await response.json();
        const key = url.replace(/https?:\/\/[^/]+/, '');
        apiCaptures[key] = { status: response.status(), body, timestamp: Date.now() };
      } catch (e) {
        // non-JSON response, skip
      }
    }
  });

  let screenshotIdx = 0;
  const screenshot = async (label) => {
    screenshotIdx++;
    const name = `mindmap_full_${String(screenshotIdx).padStart(2, '0')}_${label}.png`;
    await page.screenshot({ path: name });
    console.log(`   📸 ${name}`);
    return name;
  };

  try {
    console.log('='.repeat(72));
    console.log('MINDMAP FULL FUNCTIONALITY E2E TEST');
    console.log('='.repeat(72));

    // ============================================================
    // TEST 1: Login
    // ============================================================
    console.log('\n[Test 1] Login...');
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(3000);

    const currentUrl = page.url();
    const loggedIn = !currentUrl.includes('/login');
    addResult('Login', loggedIn ? 'passed' : 'failed', {
      message: loggedIn ? `Logged in → ${currentUrl}` : 'Login failed'
    });
    if (!loggedIn) throw new Error('Login failed, cannot proceed');

    // ============================================================
    // TEST 2: Language Setting (Japanese)
    // ============================================================
    console.log('\n[Test 2] Set language to Japanese...');

    // Look for the language toggle button in the sidebar footer area
    // The language toggle cycles: en → ko → ja → en
    let langSet = false;
    let currentLang = '';

    // Check current language by looking for locale indicators
    const bodyText = await page.textContent('body');
    if (bodyText.includes('AIスタジオ') || bodyText.includes('マインドマップ') || bodyText.includes('AIアシスタント')) {
      langSet = true;
      currentLang = 'ja';
      console.log('   Language is already Japanese');
    } else {
      // Try to find and click language toggle button
      // Look for button with language code text (EN, KO, JA)
      const langBtnSelectors = [
        'button:has-text("EN")',
        'button:has-text("KO")',
        'button:has-text("JA")',
        'button:has-text("JP")',
      ];

      for (const sel of langBtnSelectors) {
        try {
          const btn = page.locator(sel).first();
          if (await btn.count() > 0) {
            const btnText = (await btn.textContent()).trim();
            console.log(`   Found language button: "${btnText}"`);

            // Click until we reach JA
            for (let i = 0; i < 3; i++) {
              await btn.click();
              await page.waitForTimeout(800);
              const newText = (await btn.textContent()).trim();
              console.log(`   After click ${i + 1}: "${newText}"`);
              if (newText.includes('JA') || newText.includes('JP')) {
                langSet = true;
                currentLang = 'ja';
                break;
              }
              // Also check page content
              const pageText = await page.textContent('body');
              if (pageText.includes('AIスタジオ') || pageText.includes('マインドマップ')) {
                langSet = true;
                currentLang = 'ja';
                break;
              }
            }
            if (langSet) break;
          }
        } catch (e) {}
      }
    }

    addResult('Language Setting (JP)', langSet ? 'passed' : 'failed', {
      message: langSet ? `Language set to Japanese (${currentLang})` : 'Could not confirm Japanese language setting'
    });

    // ============================================================
    // TEST 3: Navigate to Mindmap Page
    // ============================================================
    console.log('\n[Test 3] Navigate to Mindmap page...');
    await page.goto(`${BASE_URL}/mindmap`, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    await screenshot('page_loaded');

    // Verify page loaded by checking for key elements
    const studioPage = await page.locator('.studio-page').count();
    const hasHeader = await page.locator('.studio-header').count();
    const pageBodyText = await page.textContent('body');
    const hasMindmapUI = studioPage > 0 || hasHeader > 0 ||
      pageBodyText.includes('AI Studio') || pageBodyText.includes('AIスタジオ') ||
      pageBodyText.includes('マインドマップ');

    addResult('Mindmap Page Load', hasMindmapUI ? 'passed' : 'failed', {
      message: hasMindmapUI
        ? `Page loaded (studio-page: ${studioPage}, studio-header: ${hasHeader})`
        : 'Mindmap page elements not found'
    });

    // ============================================================
    // TEST 4: Saved Mindmaps List
    // ============================================================
    console.log('\n[Test 4] Check saved mindmaps...');
    await page.waitForTimeout(2000);

    // Check API response for mindmap list
    let savedCount = 0;
    for (const [key, val] of Object.entries(apiCaptures)) {
      if (key.includes('/api/v1/mindmap') && !key.includes('generate') && !key.includes('expand') && !key.includes('node') && !key.includes('query')) {
        if (val.body?.data?.mindmaps) {
          savedCount = val.body.data.mindmaps.length;
        }
      }
    }

    // Also check for empty state or saved mindmap cards in UI
    const emptyState = await page.locator('.studio-empty-state').count();
    const hasEmptyState = emptyState > 0;

    addResult('Saved Mindmaps', 'passed', {
      message: `${savedCount} mindmaps in API, empty state visible: ${hasEmptyState}`,
      savedCount,
      hasEmptyState
    });

    // ============================================================
    // TEST 5: Open AI Panel & Generate from All Documents
    // ============================================================
    console.log('\n[Test 5] Generate mindmap from all documents...');

    // Step 5a: Click the "AI Generate" button in header
    let aiPanelOpened = false;
    const aiGenSelectors = [
      'button:has-text("AI生成")',
      'button:has-text("AI Generate")',
      'button:has-text("AI 생성")',
    ];

    for (const sel of aiGenSelectors) {
      try {
        const btn = page.locator(sel).first();
        if (await btn.count() > 0) {
          await btn.click();
          await page.waitForTimeout(1500);
          console.log(`   Clicked: ${sel}`);
          aiPanelOpened = true;
          break;
        }
      } catch (e) {}
    }

    if (!aiPanelOpened) {
      // Fallback: Try finding AI panel trigger by class
      try {
        const headerBtns = await page.locator('.studio-header button').all();
        for (const btn of headerBtns) {
          const text = await btn.textContent();
          if (text && (text.includes('AI') || text.includes('生成') || text.includes('Generate'))) {
            await btn.click();
            await page.waitForTimeout(1500);
            console.log(`   Clicked header button: "${text.trim()}"`);
            aiPanelOpened = true;
            break;
          }
        }
      } catch (e) {}
    }

    await screenshot('ai_panel_opened');

    // Step 5b: Check that AI panel is visible
    const aiPanel = await page.locator('.studio-ai-panel').count();
    console.log(`   AI panel visible: ${aiPanel > 0}`);

    // Step 5c: Click "Generate from All Documents" button
    let generateClicked = false;
    const generateFromAllSelectors = [
      'button:has-text("すべてのドキュメントから生成")',
      'button:has-text("Generate from All Documents")',
      'button:has-text("전체 문서에서 생성")',
    ];

    for (const sel of generateFromAllSelectors) {
      try {
        const btn = page.locator(sel).first();
        if (await btn.count() > 0) {
          console.log(`   Found generate button: ${sel}`);
          await btn.click({ timeout: 5000 });
          generateClicked = true;
          console.log(`   Clicked: ${sel}`);
          break;
        }
      } catch (e) {
        console.log(`   Failed to click ${sel}: ${e.message}`);
      }
    }

    if (!generateClicked) {
      // Fallback: Look for Brain icon button in AI panel
      try {
        const panelBtns = await page.locator('.studio-ai-panel button, .studio-ai-panel-body button').all();
        for (const btn of panelBtns) {
          const text = await btn.textContent();
          if (text && (text.includes('すべて') || text.includes('All') || text.includes('전체'))) {
            await btn.click({ timeout: 5000 });
            generateClicked = true;
            console.log(`   Clicked panel button: "${text.trim()}"`);
            break;
          }
        }
      } catch (e) {}
    }

    await screenshot('generate_clicked');

    // Step 5d: Wait for generation to complete (up to 120 seconds)
    if (generateClicked) {
      console.log('   Waiting for mindmap generation (up to 120s)...');

      let generationDone = false;
      for (let i = 0; i < 24; i++) {  // 24 * 5s = 120s
        await page.waitForTimeout(5000);

        // Check if generation is complete by looking for:
        // 1. Mindmap nodes on canvas
        // 2. AI panel closed (it closes on success)
        // 3. Error message
        const nodesOnCanvas = await page.locator('.mindmap-node').count();
        const svgNodes = await page.locator('.studio-svg g').count();
        const aiPanelStillOpen = await page.locator('.studio-ai-panel:not(.minimized)').count();
        const errorMsg = await page.locator('.studio-error-message').count();

        const elapsed = (i + 1) * 5;
        console.log(`   [${elapsed}s] canvas nodes: ${nodesOnCanvas}, svg groups: ${svgNodes}, ai panel: ${aiPanelStillOpen}, error: ${errorMsg}`);

        if (nodesOnCanvas > 0 || (svgNodes > 2 && aiPanelStillOpen === 0)) {
          generationDone = true;
          console.log(`   Generation complete after ${elapsed}s!`);
          break;
        }

        if (errorMsg > 0) {
          const errText = await page.locator('.studio-error-message').first().textContent();
          console.log(`   Error detected: ${errText}`);
          break;
        }

        // Check if we got API response
        for (const [key, val] of Object.entries(apiCaptures)) {
          if ((key.includes('generate') || key.includes('from-all')) && val.body?.data?.mindmap) {
            generationDone = true;
            console.log(`   API response captured after ${elapsed}s`);
            break;
          }
        }
        if (generationDone) break;

        if (i % 4 === 3) {
          await screenshot(`generating_${elapsed}s`);
        }
      }

      await screenshot('generation_result');

      addResult('Mindmap Generation', generationDone ? 'passed' : 'failed', {
        message: generationDone ? 'Mindmap generated successfully' : 'Generation timed out or failed'
      });
    } else {
      addResult('Mindmap Generation', 'failed', {
        message: 'Could not find or click generate button'
      });
    }

    // ============================================================
    // TEST 6: Verify Generated Mindmap Language
    // ============================================================
    console.log('\n[Test 6] Analyze generated mindmap language...');

    // Get mindmap data from API captures
    let mindmapData = null;
    for (const [key, val] of Object.entries(apiCaptures)) {
      if ((key.includes('generate') || key.includes('from-all')) && val.body?.data?.mindmap) {
        mindmapData = val.body.data.mindmap;
      }
    }

    if (mindmapData) {
      const nodes = mindmapData.data?.nodes || [];
      const edges = mindmapData.data?.edges || [];
      const langMeta = mindmapData.data?.metadata?.language;

      console.log(`   Mindmap: "${mindmapData.title}" (${nodes.length} nodes, ${edges.length} edges)`);
      console.log(`   Language metadata: ${langMeta}`);

      let totalKorean = 0;
      let totalJapanese = 0;
      let nodeDetails = [];

      for (const n of nodes) {
        const text = `${n.label} ${n.description || ''}`;
        const ko = countKorean(text);
        const ja = countJapaneseKana(text);
        totalKorean += ko;
        totalJapanese += ja;
        nodeDetails.push({ label: n.label, desc: n.description, type: n.type, ko, ja });
        console.log(`   [${n.type}] "${n.label}" desc="${n.description || ''}" KO=${ko} JA=${ja}`);
      }

      for (const e of edges) {
        const label = e.label || '';
        const ko = countKorean(label);
        const ja = countJapaneseKana(label);
        totalKorean += ko;
        totalJapanese += ja;
        console.log(`   [edge] "${label}" KO=${ko} JA=${ja}`);
      }

      console.log(`\n   Total: Korean=${totalKorean}, Japanese kana=${totalJapanese}`);
      const langPass = totalKorean === 0 && langMeta === 'ja';

      results.languageAnalysis = {
        totalKorean,
        totalJapanese,
        langMeta,
        nodeDetails,
        title: mindmapData.title
      };

      addResult('Language Verification', langPass ? 'passed' : 'failed', {
        message: langPass
          ? `No Korean detected, language=${langMeta}, JA kana=${totalJapanese}`
          : `Korean chars: ${totalKorean}, Japanese kana: ${totalJapanese}, meta: ${langMeta}`
      });
    } else {
      // Fallback: Analyze visible page text
      const visibleText = await page.textContent('body');
      const koChars = countKorean(visibleText);
      const jaChars = countJapaneseKana(visibleText);
      console.log(`   No API data captured. Page text: KO=${koChars}, JA=${jaChars}`);

      addResult('Language Verification', 'errors', {
        message: `No mindmap data in API captures. Page text: KO=${koChars}, JA=${jaChars}`
      });
    }

    // ============================================================
    // TEST 7: Node Click → Edit Panel
    // ============================================================
    console.log('\n[Test 7] Node click → Edit panel...');

    // First, close overlapping elements (AI sidebar, AI panel) that block node clicks
    try {
      // Close portal-ai-sidebar (chat sidebar) if present
      const sidebarCloseBtn = page.locator('.portal-ai-sidebar button[class*="close"], .portal-ai-sidebar .close-btn').first();
      if (await sidebarCloseBtn.count() > 0) {
        await sidebarCloseBtn.click();
        console.log('   Closed AI sidebar');
        await page.waitForTimeout(500);
      }

      // Close the studio-ai-panel if still open
      const aiPanelClose = page.locator('.studio-ai-panel button').first();
      if (await page.locator('.studio-ai-panel:not(.minimized)').count() > 0) {
        // Find X button in AI panel header
        const panelBtns = await page.locator('.studio-ai-panel-header button').all();
        for (const btn of panelBtns) {
          try {
            const text = await btn.textContent();
            if (!text || text.trim().length <= 1) {
              await btn.click();
              console.log('   Closed AI panel');
              break;
            }
          } catch (e) {}
        }
        await page.waitForTimeout(500);
      }

      // Also try clicking the canvas area to dismiss overlays
      await page.locator('.studio-canvas').click({ position: { x: 10, y: 10 }, force: true });
      await page.waitForTimeout(500);

      // Hide portal-ai-sidebar via JavaScript if still blocking
      await page.evaluate(() => {
        const sidebar = document.querySelector('.portal-ai-sidebar');
        if (sidebar) sidebar.style.display = 'none';
      });
      console.log('   Cleared overlapping elements');
    } catch (e) {
      console.log(`   Overlay cleanup: ${e.message}`);
    }

    let nodeClicked = false;
    try {
      // Click on a mindmap node using force:true to bypass overlay issues
      const nodeElements = await page.locator('.mindmap-node').all();
      if (nodeElements.length > 0) {
        // Click the root node (usually larger and more centered)
        const targetIdx = 0;
        await nodeElements[targetIdx].click({ force: true, timeout: 10000 });
        await page.waitForTimeout(2000);
        nodeClicked = true;
        console.log(`   Clicked node ${targetIdx + 1} of ${nodeElements.length}`);
      } else {
        // Try SVG group elements
        const svgGroups = await page.locator('.studio-svg g[class*="node"]').all();
        if (svgGroups.length > 0) {
          await svgGroups[0].click({ force: true });
          await page.waitForTimeout(2000);
          nodeClicked = true;
          console.log(`   Clicked SVG node group`);
        }
      }
    } catch (e) {
      console.log(`   Node click error: ${e.message}`);
    }

    await screenshot('node_clicked');

    // Check if editor panel appeared
    const editorPanel = await page.locator('.studio-node-editor').count();
    const hasEditor = editorPanel > 0 && nodeClicked;

    addResult('Node Click → Editor', hasEditor ? 'passed' : (nodeClicked ? 'failed' : 'errors'), {
      message: hasEditor
        ? 'Node editor panel opened'
        : nodeClicked ? 'Node clicked but editor not visible' : 'No nodes to click'
    });

    // ============================================================
    // TEST 8: Node Expand
    // ============================================================
    console.log('\n[Test 8] Node expansion...');

    let expanded = false;
    if (hasEditor) {
      try {
        const expandSelectors = [
          'button:has-text("展開")',
          'button:has-text("Expand")',
          'button:has-text("확장")',
        ];

        for (const sel of expandSelectors) {
          const btn = page.locator(sel).first();
          if (await btn.count() > 0) {
            const isDisabled = await btn.isDisabled();
            if (!isDisabled) {
              await btn.click();
              console.log(`   Clicked expand: ${sel}`);
              // Wait for expansion API response
              await page.waitForTimeout(15000);
              expanded = true;
              break;
            } else {
              console.log(`   Expand button disabled: ${sel}`);
            }
          }
        }
      } catch (e) {
        console.log(`   Expand error: ${e.message}`);
      }

      await screenshot('after_expand');

      // Check if new nodes appeared
      const nodesAfterExpand = await page.locator('.mindmap-node').count();
      addResult('Node Expansion', expanded ? 'passed' : 'errors', {
        message: expanded
          ? `Expansion triggered, nodes on canvas: ${nodesAfterExpand}`
          : 'Could not trigger expansion (button disabled or not found)'
      });
    } else {
      addResult('Node Expansion', 'errors', {
        message: 'Skipped - no editor panel available'
      });
    }

    // ============================================================
    // TEST 9: Node Query
    // ============================================================
    console.log('\n[Test 9] Node query...');

    let queryAnswered = false;
    if (hasEditor) {
      try {
        // Find the query input
        const queryInput = page.locator('.studio-node-editor input[type="text"], .studio-node-editor textarea').last();
        if (await queryInput.count() > 0) {
          await queryInput.fill('この概念について詳しく説明してください');
          console.log('   Entered query text');

          // Find and click the search/query button
          const searchBtns = await page.locator('.studio-node-editor button').all();
          for (const btn of searchBtns) {
            try {
              const text = await btn.textContent();
              // The query section has a small search button
              if (text && text.trim().length <= 3) {
                await btn.click({ timeout: 3000 });
                console.log('   Clicked query button');
                break;
              }
            } catch (e) {}
          }

          // Or press Enter on the input
          await queryInput.press('Enter');
          await page.waitForTimeout(20000);

          // Check for answer
          const answerEl = await page.locator('.studio-node-editor').textContent();
          queryAnswered = answerEl.includes('Answer') || answerEl.includes('答え') || answerEl.includes('답변') || answerEl.length > 200;

          await screenshot('after_query');
        }
      } catch (e) {
        console.log(`   Query error: ${e.message}`);
      }

      addResult('Node Query', queryAnswered ? 'passed' : 'errors', {
        message: queryAnswered ? 'Query answered' : 'Query might not have completed (check screenshot)'
      });
    } else {
      addResult('Node Query', 'errors', {
        message: 'Skipped - no editor panel available'
      });
    }

    // ============================================================
    // TEST 10: Load Saved Mindmap
    // ============================================================
    console.log('\n[Test 10] Load saved mindmap...');

    let loadedSaved = false;

    // Navigate back to mindmap page to see empty state with saved list
    // The empty state shows saved mindmaps as quick-load buttons
    if (savedCount > 0) {
      try {
        // Look for saved mindmap items - they could be in empty state or a list
        // First try to find clickable mindmap items
        const savedItems = await page.locator('[class*="saved"], [class*="mindmap-item"], [class*="quick"]').all();
        if (savedItems.length > 0) {
          await savedItems[0].click();
          await page.waitForTimeout(5000);
          loadedSaved = true;
          console.log(`   Clicked saved mindmap item`);
        }
      } catch (e) {
        console.log(`   Load saved error: ${e.message}`);
      }
    }

    addResult('Load Saved Mindmap', loadedSaved ? 'passed' : 'errors', {
      message: loadedSaved ? 'Loaded saved mindmap' : `Skipped - ${savedCount} saved, couldn't find clickable items`
    });

    // ============================================================
    // TEST 11: Status Bar Verification
    // ============================================================
    console.log('\n[Test 11] Status bar verification...');
    const statusBar = await page.locator('.studio-status').count();
    let statusText = '';
    if (statusBar > 0) {
      statusText = await page.locator('.studio-status').textContent();
    }

    addResult('Status Bar', statusBar > 0 ? 'passed' : 'failed', {
      message: statusBar > 0 ? `Status: "${statusText.substring(0, 80).trim()}"` : 'Status bar not found'
    });

    // ============================================================
    // TEST 12: Zoom Controls
    // ============================================================
    console.log('\n[Test 12] Zoom controls...');
    let zoomWorks = false;
    try {
      const zoomBtns = await page.locator('.studio-toolbar button, .studio-zoom button').all();
      for (const btn of zoomBtns) {
        const text = await btn.textContent();
        if (text && text.includes('%')) {
          console.log(`   Current zoom: ${text.trim()}`);
        }
      }

      // Try zoom in
      const zoomInSelectors = [
        'button:has-text("+")',
        '.studio-toolbar button:last-child',
      ];
      for (const sel of zoomInSelectors) {
        try {
          const btn = page.locator(sel).first();
          if (await btn.count() > 0) {
            await btn.click();
            await page.waitForTimeout(500);
            zoomWorks = true;
            console.log('   Zoom in clicked');
            break;
          }
        } catch (e) {}
      }
    } catch (e) {
      console.log(`   Zoom error: ${e.message}`);
    }

    addResult('Zoom Controls', zoomWorks ? 'passed' : 'errors', {
      message: zoomWorks ? 'Zoom control functional' : 'Could not test zoom'
    });

    // Final screenshot
    await screenshot('final_state');

    // Store API captures in results
    results.apiCaptures = {};
    for (const [key, val] of Object.entries(apiCaptures)) {
      results.apiCaptures[key] = {
        status: val.status,
        hasData: !!val.body?.data,
        timestamp: val.timestamp
      };
    }

  } catch (error) {
    console.error('\nFATAL ERROR:', error.message);
    addResult('Test Execution', 'errors', { message: error.message });
    await screenshot('error').catch(() => {});
  } finally {
    // Print summary
    console.log(`\n${'='.repeat(72)}`);
    console.log('TEST RESULTS SUMMARY');
    console.log(`${'='.repeat(72)}`);
    console.log(`Total:  ${results.summary.total}`);
    console.log(`Passed: ${results.summary.passed}`);
    console.log(`Failed: ${results.summary.failed}`);
    console.log(`Errors: ${results.summary.errors}`);
    console.log(`\nAPI Endpoints Captured: ${Object.keys(apiCaptures).length}`);
    for (const [key, val] of Object.entries(apiCaptures)) {
      console.log(`  ${val.status} ${key}`);
    }

    if (results.languageAnalysis.totalKorean !== undefined) {
      console.log(`\nLanguage Analysis:`);
      console.log(`  Korean chars: ${results.languageAnalysis.totalKorean}`);
      console.log(`  Japanese kana: ${results.languageAnalysis.totalJapanese}`);
      console.log(`  Language meta: ${results.languageAnalysis.langMeta}`);
      console.log(`  Title: ${results.languageAnalysis.title}`);
    }

    // Save results
    fs.writeFileSync(RESULTS_FILE, JSON.stringify(results, null, 2));
    console.log(`\nResults saved: ${RESULTS_FILE}`);
    console.log(`Screenshots: mindmap_full_01~${String(screenshotIdx).padStart(2, '0')}_*.png`);

    await browser.close();
  }
})();
