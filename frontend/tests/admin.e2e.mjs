import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const password = process.env.E2E_ADMIN_PASSWORD;
if (!password) throw new Error('Set E2E_ADMIN_PASSWORD for the local admin smoke test.');
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_ADMIN_BASE_URL || 'https://127.0.0.1:18575';
const failures = [];
try {
  await mkdir('.artifacts', { recursive: true });
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
    page.on('pageerror', (error) => failures.push(error.message));
    await page.goto(`${base}/admin/login`, { waitUntil: 'networkidle' });
    await page.getByLabel('Usuário').fill(process.env.E2E_ADMIN_USERNAME || 'admin_local');
    await page.getByLabel('Senha').fill(password);
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.getByRole('heading', { name: 'Administração' }).waitFor();
    await page.getByRole('tab', { name: 'Usuários' }).click();
    await page.getByRole('heading', { name: 'Usuários' }).waitFor();
    await page.getByRole('tab', { name: 'Custos e uso' }).click();
    await page.getByRole('heading', { name: 'Uso da OpenAI' }).waitFor();
    await page.getByRole('tab', { name: 'Execuções' }).click();
    await page.getByText('Processadores de tarefas respondendo:').waitFor();
    await page.getByRole('tab', { name: 'Auditoria' }).click();
    await page.getByRole('heading', { name: 'Auditoria' }).waitFor();
    await page.getByRole('tab', { name: 'Minha senha' }).click();
    await page.getByRole('heading', { name: 'Alterar minha senha' }).waitFor();
    await page.screenshot({ path: `.artifacts/admin-${width}.png`, fullPage: true });
    assert.equal(await page.locator('body').evaluate((body) => body.scrollWidth <= innerWidth + 1), true);
    await page.close();
  }
  assert.deepEqual(failures, []);
  console.log('Admin browser smoke passed at 1440px and 390px.');
} finally {
  await browser.close();
}
