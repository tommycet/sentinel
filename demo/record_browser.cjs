const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: '/tmp/demo_recordings',
      size: { width: 1280, height: 720 }
    }
  });
  const page = await context.newPage();

  console.log('Navigating to landing page...');
  await page.goto('http://localhost:8090', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(3000); // hero hold

  // Smooth scroll through entire page
  const totalHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  console.log(`Page height: ${totalHeight}px`);

  const scrollStep = 8;
  const scrollDelay = 40;
  const steps = Math.ceil(totalHeight / scrollStep);

  for (let i = 0; i < steps; i++) {
    await page.evaluate((y) => window.scrollTo(0, y), i * scrollStep);
    await page.waitForTimeout(scrollDelay);
  }

  console.log('Reached bottom. Holding...');
  await page.waitForTimeout(3000);

  // Scroll back up smoothly
  for (let i = steps; i >= 0; i--) {
    await page.evaluate((y) => window.scrollTo(0, y), i * scrollStep);
    await page.waitForTimeout(20);
  }

  console.log('Back at top. Final hold.');
  await page.waitForTimeout(3000);

  await page.close();
  await context.close();
  await browser.close();

  // Find the recorded video
  const fs = require('fs');
  const files = fs.readdirSync('/tmp/demo_recordings').filter(f => f.endsWith('.webm'));
  console.log('Recorded videos:', files);
  if (files.length > 0) {
    const src = path.join('/tmp/demo_recordings', files[files.length - 1]);
    const dst = '/root/signoz-sentinel/demo/videos/sentinel_demo_raw.webm';
    fs.copyFileSync(src, dst);
    console.log(`Copied to ${dst} (${fs.statSync(dst).size} bytes)`);
  }
})();
