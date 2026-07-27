const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'demo/videos', size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();

  await page.goto('http://localhost:8090/lineage_terminal.html', { waitUntil: 'networkidle' }).catch(async () => {
    await page.goto('file:///root/signoz-sentinel/demo/lineage_terminal.html', { waitUntil: 'networkidle' });
  });

  // Wait for full content scroll (user can scroll through)
  await page.waitForTimeout(90000);

  // Scroll through the AgentLineage section to show full content
  await page.evaluate('window.scrollTo({top: 0, behavior: "auto"})');
  await page.waitForTimeout(2000);

  await page.evaluate('document.querySelector(".section")?.scrollIntoView({behavior: "auto"})');
  await page.waitForTimeout(10000);

  await page.evaluate('window.scrollTo({top: 600, behavior: "auto"})');
  await page.waitForTimeout(5000);

  await page.evaluate('window.scrollTo({top: 1200, behavior: "auto"})');
  await page.waitForTimeout(5000);

  await page.evaluate('window.scrollTo({top: 1800, behavior: "auto"})');
  await page.waitForTimeout(5000);

  await context.close();
  await browser.close();
  console.log('AgentLineage scroll demo complete');
})();
