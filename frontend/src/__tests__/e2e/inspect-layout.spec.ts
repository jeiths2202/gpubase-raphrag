import { test } from '@playwright/test';

test('inspect layout styles', async ({ page }) => {
  // Login
  await page.goto('http://localhost:3000');
  await page.fill('input[type="text"]', 'edelweise@naver.com');
  await page.fill('input[type="password"]', 'SecureTest123!');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/knowledge', { timeout: 15000 });
  await page.waitForTimeout(3000);

  // Inspect main container
  const mainContainer = page.locator('.knowledge-main');
  const mainBox = await mainContainer.boundingBox();
  console.log('Main container bounding box:', mainBox);

  const mainStyles = await mainContainer.evaluate(el => {
    const styles = window.getComputedStyle(el);
    return {
      display: styles.display,
      width: styles.width,
      height: styles.height,
      overflow: styles.overflow,
      flex: styles.flex,
      padding: styles.padding
    };
  });
  console.log('Main container styles:', mainStyles);

  // Inspect chat message list
  const chatList = page.locator('.chat-message-list');
  const chatListCount = await chatList.count();
  console.log('Chat message list count:', chatListCount);

  if (chatListCount > 0) {
    const chatBox = await chatList.boundingBox();
    console.log('Chat list bounding box:', chatBox);

    const chatStyles = await chatList.evaluate(el => {
      const styles = window.getComputedStyle(el);
      return {
        display: styles.display,
        width: styles.width,
        height: styles.height,
        minHeight: styles.minHeight,
        flex: styles.flex,
        overflow: styles.overflow,
        visibility: styles.visibility,
        opacity: styles.opacity
      };
    });
    console.log('Chat list styles:', chatStyles);
  }

  // Check if ChatTab is rendered
  const chatTabMotion = page.locator('[style*="flex: 1"]').first();
  const chatTabCount = await chatTabMotion.count();
  console.log('ChatTab motion div count:', chatTabCount);

  if (chatTabCount > 0) {
    const chatTabBox = await chatTabMotion.boundingBox();
    console.log('ChatTab bounding box:', chatTabBox);

    const chatTabStyles = await chatTabMotion.evaluate(el => {
      const styles = window.getComputedStyle(el);
      return {
        display: styles.display,
        width: styles.width,
        height: styles.height,
        flex: styles.flex,
        overflow: styles.overflow
      };
    });
    console.log('ChatTab styles:', chatTabStyles);
  }

  // Take screenshot
  await page.screenshot({ path: 'layout-inspection.png', fullPage: true });
});
