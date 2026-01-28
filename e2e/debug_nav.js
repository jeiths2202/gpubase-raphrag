const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();

  try {
    // Step 1: Login
    console.log('1. Going to login page...');
    await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'debug_01_login.png' });
    
    console.log('2. Filling credentials...');
    await page.fill('input[type="text"]', 'admin');
    await page.fill('input[type="password"]', 'SecureAdm1nP@ss2024!');
    await page.screenshot({ path: 'debug_02_filled.png' });
    
    console.log('3. Clicking submit...');
    await page.click('button[type="submit"]');
    await page.waitForTimeout(5000);
    await page.screenshot({ path: 'debug_03_after_login.png' });
    
    console.log('4. Current URL:', page.url());
    
    // Step 2: Try to navigate
    console.log('5. Looking for AI Agent link...');
    const links = await page.locator('a, button').all();
    console.log('Found links/buttons:', links.length);
    
    // Print all link texts
    for (let i = 0; i < Math.min(links.length, 20); i++) {
      try {
        const text = await links[i].textContent();
        if (text && text.trim()) {
          console.log(`   Link ${i}: "${text.trim().substring(0, 50)}"`);
        }
      } catch (e) {}
    }
    
    // Try different navigation approaches
    const agentSelectors = [
      'text=AIエージェント',
      'text=AI Agent',
      'text=AI 에이전트',
      '[href*="agent"]',
      'a:has-text("Agent")'
    ];
    
    for (const selector of agentSelectors) {
      const count = await page.locator(selector).count();
      console.log(`   Selector "${selector}": ${count} matches`);
    }
    
    // Navigate directly
    console.log('6. Navigating directly to /agent...');
    await page.goto('http://localhost:3000/agent', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: 'debug_04_agent_page.png' });
    
    console.log('7. Current URL:', page.url());
    
    // Check for textarea
    const textarea = await page.locator('textarea').count();
    console.log('8. Textarea count:', textarea);
    
    // Check for any input
    const inputs = await page.locator('input, textarea').all();
    console.log('9. Input elements:', inputs.length);
    for (let i = 0; i < inputs.length; i++) {
      try {
        const tag = await inputs[i].evaluate(el => el.tagName);
        const type = await inputs[i].getAttribute('type');
        const placeholder = await inputs[i].getAttribute('placeholder');
        console.log(`   Input ${i}: ${tag} type=${type} placeholder="${placeholder}"`);
      } catch (e) {}
    }
    
    console.log('Debug completed!');
    
  } catch (error) {
    console.error('Error:', error.message);
    await page.screenshot({ path: 'debug_error.png' });
  } finally {
    await browser.close();
  }
})();
