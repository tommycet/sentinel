const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: '/tmp/demo_recordings', size: { width: 1280, height: 720 } }
  });
  const page = await context.newPage();
  await page.goto('http://localhost:8090', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(5000); // hero hold 5s

  // Slow scroll down through entire page (~5 min total recording)
  const totalHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  const scrollStep = 4;
  const scrollDelay = 80;
  const steps = Math.ceil(totalHeight / scrollStep);
  for (let i = 0; i < steps; i++) {
    await page.evaluate((y) => window.scrollTo(0, y), i * scrollStep);
    await page.waitForTimeout(scrollDelay);
  }

  await page.waitForTimeout(5000); // bottom hold 5s
  // Slow scroll back up
  for (let i = steps; i >= 0; i--) {
    await page.evaluate((y) => window.scrollTo(0, y), i * scrollStep);
    await page.waitForTimeout(30);
  }
  await page.waitForTimeout(3000);

  await page.close();
  await context.close();
  await browser.close();

  const files = fs.readdirSync('/tmp/demo_recordings').filter(f => f.endsWith('.webm'));
  const src = path.join('/tmp/demo_recordings', files[files.length - 1]);
  fs.copyFileSync(src, '/root/signoz-sentinel/demo/videos/sentinel_demo_raw.webm');
  console.log('Recording done:', fs.statSync('/root/signoz-sentinel/demo/videos/sentinel_demo_raw.webm').size, 'bytes');
})();
