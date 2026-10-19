import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const values = Object.fromEntries((await readFile(resolve(root, 'pentest/.env'), 'utf8')).split(/\r?\n/)
  .filter((line) => line && !line.startsWith('#')).map((line) => line.split(/=(.*)/s).slice(0, 2)));
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  headless: true,
});
try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('https://127.0.0.2:18675/admin/login/', { waitUntil: 'networkidle' });
    await page.getByLabel('Usuário').fill('pt_admin');
    await page.getByLabel('Senha').fill(values.PENTEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.getByRole('heading', { name: 'Administração', exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Saúde do sistema' }).click();
    await page.getByRole('heading', { name: 'Saúde da instalação' }).waitFor();
    await page.getByRole('cell', { name: 'PostgreSQL' }).waitFor();
    await page.getByText('Uso e custos — histórico da instalação').waitFor();
    assert.deepEqual(errors, []);
    await page.screenshot({ path: resolve(root, `pentest/results/admin-health-${width}.png`), fullPage: true });
    await page.close();
  }
  console.log('PASS clone Health browser desktop/mobile');
} finally {
  await browser.close();
}
