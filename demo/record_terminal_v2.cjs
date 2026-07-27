const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // Navigate to the terminal demo HTML (typing animation runs automatically)
  await page.goto('http://localhost:8090/terminal_demo.html', { waitUntil: 'networkidle' }).catch(async () => {
    // If not served, use file:// protocol
    await page.goto('file:///root/signoz-sentinel/demo/terminal_demo.html', { waitUntil: 'networkidle' });
  });
  
  // Wait for typing animation to complete (~110 seconds)
  await page.waitForTimeout(115000);

  await context.close();
  await browser.close();
  console.log('Terminal demo video complete');
})();
