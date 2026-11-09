// Renders HTML files listed in a JSON manifest
// [{html, png, width, height, scale?, transparent?}] to PNG.
// Usage: node render.js manifest.json
const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  const contexts = {};
  for (const job of jobs) {
    const scale = job.scale || 1;
    const key = `${job.width}x${job.height}@${scale}`;
    if (!contexts[key]) {
      const ctx = await browser.newContext({
        viewport: { width: job.width, height: job.height },
        deviceScaleFactor: scale,
      });
      contexts[key] = await ctx.newPage();
    }
    const page = contexts[key];
    await page.setContent(fs.readFileSync(job.html, 'utf8'), { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: job.png, omitBackground: !!job.transparent });
  }
  await browser.close();
  console.log(`rendered ${jobs.length} images`);
})();
