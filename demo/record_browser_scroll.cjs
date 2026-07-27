const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // ═══════════════════════════════════════════════════════════
  // PART 1 (0-90s): Live browser recording with REAL scrolling
  // ═══════════════════════════════════════════════════════════
  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  // Scroll through each section smoothly, pausing to show details
  // Hero section (0-15s)
  await page.waitForTimeout(12000);

  // Scroll to metrics strip (15-22s)
  await page.evaluate(() => document.querySelector('.stats-strip')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(7000);

  // Scroll to architecture (22-30s)
  await page.evaluate(() => document.querySelector('.section-rule')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(8000);

  // Scroll to features/lineage (30-45s)
  await page.evaluate(() => document.querySelector('#lineage')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(15000);

  // Scroll to lineage artifacts (45-60s)
  await page.evaluate(() => document.querySelector('.lineage')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(15000);

  // Scroll to security audit (60-75s)
  await page.evaluate(() => document.querySelector('.security-audit')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(15000);

  // Scroll to docs (75-90s)
  await page.evaluate(() => document.querySelector('.docs')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(15000);

  await context.close();
  await browser.close();
  console.log('Part 1 browser recording complete');
})();
