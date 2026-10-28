// Optional visual smoke check: node scripts/check-report.cjs [playwright-module-path]
// Uses an installed Edge in headless mode; no runtime dependency for the product.
const { chromium } = require(process.argv[2] || 'playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(pathToFileURL(path.resolve('artifacts/regression/report.html')).href);
    assert.match(await page.locator('body').innerText(), /SYNTHETIC FIXTURE/);
    assert.equal(await page.locator('article').count(), 1);
    assert.match(await page.locator('article').innerText(), /11.5/);
    await page.screenshot({ path: 'artifacts/regression/desktop.png', fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path: 'artifacts/regression/mobile.png', fullPage: true });
    await page.goto(pathToFileURL(path.resolve('artifacts/recovery/report.html')).href);
    assert.equal(await page.locator('article').count(), 0);
    assert.match(await page.locator('body').innerText(), /No eligible regressions/);
    assert.equal(errors.length, 0);
    console.log('PASS: desktop/mobile regression rendering, recovery rendering, no page errors or mobile horizontal overflow.');
  } finally {
    await browser.close();
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
