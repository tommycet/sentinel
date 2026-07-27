const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // Navigate to the single page containing all three scenes
  // The page has a built-in JS scroll controller that pans through content
  // in sync with narration timing.
  await page.goto('http://localhost:8090/scenes.html', { waitUntil: 'networkidle' }).catch(async () => {
    await page.goto('file:///root/signoz-sentinel/demo/scenes.html', { waitUntil: 'networkidle' });
  });

  // Wait for the scroll script to complete (165s of content)
  // The landing page iframe may fail if tunnel is down, so use localhost:8090
  await page.waitForTimeout(175000);

  await context.close();
  await browser.close();
  console.log('Scenes recording complete');
})();