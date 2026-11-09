// Renders HTML files listed in a JSON manifest [{html, png, width, height}] to PNG.
// Usage: node render.js manifest.json
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage();
  for (const job of jobs) {
    await page.setViewportSize({ width: job.width, height: job.height });
    await page.setContent(fs.readFileSync(job.html, 'utf8'), { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.png });
  }
  await browser.close();
  console.log(`rendered ${jobs.length} images`);
})();
