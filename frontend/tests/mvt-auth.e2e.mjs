import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const userSession = process.env.E2E_USER_SESSION;
const adminSession = process.env.E2E_ADMIN_SESSION;
if (!userSession || !adminSession) throw new Error('E2E_USER_SESSION and E2E_ADMIN_SESSION required');

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const failures = [];
try {
  const publicBase = 'https://127.0.0.1:18574';
  const publicPage = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 1440, height: 900 } });
  publicPage.on('pageerror', (error) => failures.push(error.message));
  await publicPage.context().addCookies([{ name: 'sessionid', value: userSession, url: publicBase, secure: true }]);
  assert.equal((await publicPage.goto(publicBase, { waitUntil: 'networkidle' })).status(), 200);
  await publicPage.getByRole('heading', { name: 'Reuniões' }).waitFor();
  assert.equal(await publicPage.locator('[data-mvt="1"]').count(), 1);
  const navigation = publicPage.waitForNavigation();
  await publicPage.getByRole('button', { name: 'Nova reunião' }).click();
  assert.equal((await navigation).status(), 200);
  await publicPage.getByRole('heading', { name: 'Nova reunião' }).waitFor();
  await publicPage.getByText('Confirmo que os participantes consentiram', { exact: false }).waitFor();
  await publicPage.goto(publicBase, { waitUntil: 'networkidle' });
  const meetingLink = publicPage.locator('nav.side .side__item').first();
  if (await meetingLink.count()) {
    const meetingNavigation = publicPage.waitForNavigation();
    await meetingLink.click();
    assert.equal((await meetingNavigation).status(), 200);
    assert.equal(await publicPage.locator('[data-mvt="1"]').count(), 1);
    await publicPage.locator('main .t-page').first().waitFor();
  }
  assert.equal((await publicPage.goto(`${publicBase}/conta/`, { waitUntil: 'networkidle' })).status(), 200);
  await publicPage.getByRole('heading', { name: 'Conta' }).waitFor();
  await publicPage.close();

  const mobilePage = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 900 } });
  mobilePage.on('pageerror', (error) => failures.push(error.message));
  await mobilePage.context().addCookies([{ name: 'sessionid', value: userSession, url: publicBase, secure: true }]);
  assert.equal((await mobilePage.goto(publicBase, { waitUntil: 'networkidle' })).status(), 200);
  await mobilePage.getByRole('button', { name: 'Abrir menu' }).click();
  assert.equal(await mobilePage.locator('nav.side').evaluate((node) => node.classList.contains('side--open')), true);
  await mobilePage.mouse.click(380, 450); // outside the 85vw drawer, on its scrim
  assert.equal(await mobilePage.locator('nav.side').evaluate((node) => node.classList.contains('side--open')), false);
  assert.equal(await mobilePage.locator('body').evaluate((body) => body.scrollWidth <= innerWidth + 1), true);
  await mobilePage.close();

  const adminBase = 'https://127.0.0.1:18575';
  const adminPage = await browser.newPage({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 900 } });
  adminPage.on('pageerror', (error) => failures.push(error.message));
  await adminPage.context().addCookies([{ name: 'sessionid', value: adminSession, url: adminBase, secure: true }]);
  assert.equal((await adminPage.goto(`${adminBase}/admin/`, { waitUntil: 'networkidle' })).status(), 200);
  await adminPage.getByRole('heading', { name: 'Administração' }).waitFor();
  await adminPage.getByRole('tab', { name: 'Usuários' }).click();
  await adminPage.getByRole('heading', { name: 'Usuários' }).waitFor();
  assert.equal(await adminPage.locator('body').evaluate((body) => body.scrollWidth <= innerWidth + 1), true);
  await adminPage.close();
  assert.deepEqual(failures, []);
  console.log('MVT authenticated browser smoke passed: public/admin and document navigation.');
} finally { await browser.close(); }
