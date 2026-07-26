const { chromium } = require('playwright');

const SCENES = [
  { name: '01-hero',       url: 'http://localhost:8090',                     dur: 8000,  scroll: 0 },
  { name: '02-stats',      url: 'http://localhost:8090#stats',               dur: 7000,  scroll: 0 },
  { name: '03-arch',       url: 'http://localhost:8090#arch',                dur: 8000,  scroll: 0 },
  { name: '04-features',   url: 'http://localhost:8090#lineage',             dur: 9000,  scroll: 0 },
  { name: '05-docs',       url: 'http://localhost:8090#docs',                dur: 10000, scroll: 0 },
  { name: '06-footer',     url: 'http://localhost:8090',                     dur: 5000,  scroll: 0 },
];

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: '/root/signoz-sentinel/demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);

  console.log('Opening page...');
  await page.goto('http://localhost:8090', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  for (const scene of SCENES) {
    console.log(`Recording: ${scene.name}`);
    if (scene.scroll > 0) {
      await page.evaluate((s) => window.scrollTo({ top: s, behavior: 'instant' }), scene.scroll);
    }
    await page.waitForTimeout(scene.dur);
  }

  await page.close();
  await context.close();
  await browser.close();
  console.log('Recording complete');
})();
