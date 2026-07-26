const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  // Navigate to the live site
  await page.goto('http://localhost:8090/', { waitUntil: 'networkidle' });
  await page.waitForTimeout(4000);

  // 1. Hero section - show the circuit diagram
  await page.screenshot({ path: 'demo/videos/step1_hero.png' });

  // 2. Click "See lineage" link
  await page.waitForSelector('a[href="#lineage"]');
  await page.click('a[href="#lineage"]');
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'demo/videos/step2_lineage.png' });

  // 3. Scroll down to architecture section
  await page.evaluate(() => document.querySelector('.section-rule')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'demo/videos/step3_arch.png' });

  // 4. Scroll to lineage artifacts
  await page.evaluate(() => document.querySelector('.lineage')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'demo/videos/step4_artifacts.png' });

  // 5. Scroll to security audit
  await page.evaluate(() => document.querySelector('.security-audit')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'demo/videos/step5_security.png' });

  // 6. Scroll to docs
  await page.evaluate(() => document.querySelector('.docs')?.scrollIntoView({behavior: 'smooth'}));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: 'demo/videos/step6_docs.png' });

  // 7. Scroll back to top
  await page.evaluate('window.scrollTo({top: 0, behavior: "smooth"})');
  await page.waitForTimeout(3000);

  await context.close();
  await browser.close();
  console.log('Interactive demo recording complete');
})();
