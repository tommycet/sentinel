const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Scroll down slowly through the entire page
  for (let i = 0; i < 20; i++) {
    await page.evaluate(`window.scrollBy(0, 200)`);
    await page.waitForTimeout(800);
  }

  // Click lineage link
  try {
    await page.waitForSelector('a[href="#lineage"]', { timeout: 5000 });
    await page.click('a[href="#lineage"]');
    await page.waitForTimeout(3000);
  } catch (e) { /* nav may not have this link */ }

  // Click docs link
  try {
    await page.waitForSelector('a[href="#docs"]', { timeout: 5000 });
    await page.click('a[href="#docs"]');
    await page.waitForTimeout(3000);
  } catch (e) { /* skip */ }

  // Scroll back to top
  await page.evaluate('window.scrollTo(0, 0)');
  await page.waitForTimeout(3000);

  await context.close();
  await browser.close();
  console.log('Long interactive recording done');
})();
