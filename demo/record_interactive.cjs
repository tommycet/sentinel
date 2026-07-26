const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // Navigate to frontend (real data, no Hermes branding)
  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Click the hero link
  await page.waitForSelector('a[href="#lineage"]');
  await page.click('a[href="#lineage"]');
  await page.waitForTimeout(2000);

  // Click the docs link
  await page.waitForSelector('a[href="#docs"]');
  await page.click('a[href="#docs"]');
  await page.waitForTimeout(3000);

  await page.screenshot({ path: 'demo/videos/interactive_final.png' });
  await context.close();
  await browser.close();
  console.log('Interactive recording done');
})();
