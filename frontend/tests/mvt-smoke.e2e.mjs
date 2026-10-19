import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = await chromium.launch({ executablePath: chrome, headless: true });
const failures = [];
try {
  for (const width of [1440, 390]) {
    for (const [base, path] of [
      ['https://127.0.0.1:18574', '/login/'],
      ['https://127.0.0.1:18575', '/admin/login/'],
    ]) {
      const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
      page.on('pageerror', (error) => failures.push(error.message));
      const response = await page.goto(`${base}${path}`, { waitUntil: 'networkidle' });
      assert.equal(response.status(), 200);
      await page.getByRole('heading', { name: 'Scribrief' }).waitFor();
      assert.equal(await page.locator('[data-mvt="1"]').count(), 1);
      assert.equal(await page.locator('body').evaluate((body) => body.scrollWidth <= innerWidth + 1), true);
      await page.close();
    }
  }
  const page = await browser.newPage({ ignoreHTTPSErrors: true });
  assert.equal((await page.goto('https://127.0.0.1:18574/admin/')).status(), 404);
  assert.equal((await page.goto('https://127.0.0.1:18574/api/admin/')).status(), 404);
  await page.close();
  assert.deepEqual(failures, []);
  console.log('MVT browser smoke passed: public/admin, desktop/mobile, admin isolation.');
} finally {
  await browser.close();
}
