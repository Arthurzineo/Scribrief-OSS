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
    const admin = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
    await admin.goto('https://127.0.0.2:18675/admin/login/', { waitUntil: 'networkidle' });
    await admin.getByLabel('Usuário').fill('pt_admin');
    await admin.getByLabel('Senha').fill(values.PENTEST_ADMIN_PASSWORD);
    await admin.getByRole('button', { name: 'Entrar' }).click();
    await admin.getByRole('heading', { name: 'Administração', exact: true }).waitFor();
    await admin.getByRole('tab', { name: 'IA por setor' }).click();
    await admin.getByLabel('Setor para configurar').selectOption({ label: 'Engenharia de teste' });
    await admin.getByRole('heading', { name: 'Credencial de IA do setor' }).waitFor();
    await admin.getByRole('button', { name: 'Instruções da IA' }).click();
    await admin.getByRole('heading', { name: 'Instruções da IA do setor' }).waitFor();
    await admin.getByRole('tab', { name: 'Setores' }).click();
    await admin.getByRole('button', { name: 'Configurar IA' }).first().click();
    await admin.getByRole('heading', { name: 'Credencial de IA do setor' }).waitFor();
    await admin.close();
  }

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true });
  await page.goto('https://127.0.0.2:18674/login/', { waitUntil: 'networkidle' });
  await page.getByLabel('Usuário').fill('pt_owner');
  await page.getByLabel('Senha').fill(values.PENTEST_OWNER_PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.locator('.side').waitFor();
  const result = await page.evaluate(() => {
    const side = document.querySelector('.side');
    const button = side.querySelector('.at-btn');
    const title = side.querySelector('.side__item-title');
    if (title) title.textContent = 'Título muito longo '.repeat(30);
    return {
      hasTitle: Boolean(title),
      buttonHeight: button.getBoundingClientRect().height,
      sideOverflow: side.scrollWidth - side.clientWidth,
      titleOverflow: title ? title.scrollWidth - title.clientWidth : 0,
      ellipsis: title ? getComputedStyle(title).textOverflow : '',
    };
  });
  assert.equal(result.hasTitle, true);
  assert.ok(result.buttonHeight <= 36, `button height ${result.buttonHeight}`);
  assert.ok(result.sideOverflow <= 1, `sidebar horizontal overflow ${result.sideOverflow}`);
  assert.ok(result.titleOverflow > 0 && result.ellipsis === 'ellipsis', JSON.stringify(result));
  await page.close();
  console.log('PASS admin IA discoverability and meeting sidebar desktop/mobile');
} finally {
  await browser.close();
}
