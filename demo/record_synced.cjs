const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });

  // ═════════════════════════════════════════════════════
  // SECTION 1: HERO (0s - 15s) — "Sentinel: closed-loop..."
  // ═════════════════════════════════════════════════════
  console.log('Starting hero section...');
  await page.waitForTimeout(15000);

  // ═════════════════════════════════════════════════════
  // SECTION 2: CAPABILITIES (15s - 38s) — "here are the key capabilities..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling to capabilities...');
  await page.evaluate(() => document.querySelector('#lineage')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(23000);

  // ═════════════════════════════════════════════════════
  // SECTION 3: ARCHITECTURE (38s - 60s) — "This is the architecture..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling to architecture...');
  await page.evaluate(() => document.querySelector('.section-rule')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(22000);

  // ═════════════════════════════════════════════════════
  // SECTION 4: LINEAGE ARTIFACTS (60s - 80s) — "cross-agent contamination..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling to lineage artifacts...');
  await page.evaluate(() => document.querySelector('.lineage')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(20000);

  // ═════════════════════════════════════════════════════
  // SECTION 5: SECURITY AUDIT (80s - 105s) — "security audit grid..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling to security audit...');
  await page.evaluate(() => document.querySelector('.security-audit')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(25000);

  // ═════════════════════════════════════════════════════
  // SECTION 6: DOCS (105s - 135s) — "Documentation..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling to docs...');
  await page.evaluate(() => document.querySelector('.docs')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(25000);

  // ═════════════════════════════════════════════════════
  // SECTION 7: BACK TO TOP (135s - 139s) — "Sentinel works globally..."
  // ═════════════════════════════════════════════════════
  console.log('Scrolling back to top...');
  await page.evaluate('window.scrollTo({top: 0, behavior: "smooth"})');
  await page.waitForTimeout(4000);

  await context.close();
  await browser.close();
  console.log('Synced interactive recording complete');
})();
