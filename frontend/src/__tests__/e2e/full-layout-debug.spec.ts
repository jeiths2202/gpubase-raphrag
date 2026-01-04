import { test } from '@playwright/test';

test('full layout hierarchy debug', async ({ page }) => {
  // Login
  await page.goto('http://localhost:3000');
  await page.fill('input[type="text"]', 'edelweise@naver.com');
  await page.fill('input[type="password"]', 'SecureTest123!');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/knowledge', { timeout: 15000 });
  await page.waitForTimeout(3000);

  // Inspect full hierarchy
  const inspectElement = async (selector: string, name: string) => {
    const element = page.locator(selector);
    const count = await element.count();
    if (count === 0) {
      console.log(`${name}: NOT FOUND`);
      return;
    }

    const box = await element.boundingBox();
    const styles = await element.evaluate(el => {
      const s = window.getComputedStyle(el);
      return {
        display: s.display,
        flexDirection: s.flexDirection,
        width: s.width,
        height: s.height,
        flex: s.flex,
        overflow: s.overflow
      };
    });

    console.log(`\n${name}:`);
    console.log('  Box:', box);
    console.log('  Styles:', styles);
  };

  await inspectElement('.knowledge-app', 'knowledge-app');
  await inspectElement('.knowledge-content', 'knowledge-content');
  await inspectElement('.knowledge-sidebar', 'knowledge-sidebar');
  await inspectElement('.knowledge-main', 'knowledge-main');
  await inspectElement('[style*="flex: 1"]', 'ChatTab (flex:1)');
  await inspectElement('.chat-message-list', 'chat-message-list');

  // Take screenshot
  await page.screenshot({ path: 'full-layout-debug.png', fullPage: true });
});
