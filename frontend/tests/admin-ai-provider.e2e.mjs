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
    await page.getByRole('tab', { name: 'Setores' }).click();
    await page.getByLabel('Cota mensal de mídia por usuário (minutos)').waitFor();
    await page.getByRole('button', { name: 'Configurar IA' }).first().click();
    await page.getByRole('heading', { name: 'Credencial de IA do setor' }).waitFor();
    await page.getByRole('button', { name: 'Instruções da IA' }).click();
    await page.getByRole('heading', { name: 'Instruções da IA do setor' }).waitFor();
    await page.getByLabel('Operação').selectOption('correction');
    await page.getByLabel('Instruções enviadas à IA').waitFor();
    page.on('dialog', (dialog) => dialog.accept());
    if (await page.getByRole('button', { name: 'Restaurar padrão' }).count()) {
      await page.getByLabel('Confirme sua senha de administrador').last().fill(values.PENTEST_ADMIN_PASSWORD);
      await page.getByRole('button', { name: 'Restaurar padrão' }).click();
      await page.getByText('Prompt padrão restaurado.').waitFor();
    }
    await page.getByText('Padrão do sistema').waitFor();
    await page.getByText(/não aceita instruções de sistema/).waitFor();
    if (width === 1440) {
      await page.getByLabel('Instruções enviadas à IA').fill('Sugira somente correções pontuais claramente sustentadas pelo contexto.');
      await page.getByLabel('Confirme sua senha de administrador').last().fill(values.PENTEST_ADMIN_PASSWORD);
      await page.getByRole('button', { name: 'Salvar prompt' }).click();
      await page.getByText('Prompt setorial salvo.').waitFor();
      await page.getByLabel('Confirme sua senha de administrador').last().fill(values.PENTEST_ADMIN_PASSWORD);
      await page.getByRole('button', { name: 'Restaurar padrão' }).click();
      await page.getByText('Prompt padrão restaurado.').waitFor();
    }
    await page.getByRole('button', { name: 'Chave de API' }).click();
    await page.getByLabel('Provedor').selectOption('openai');
    await page.getByText(/Configurada · versão/).waitFor();
    assert.deepEqual(errors, []);
    await page.screenshot({ path: resolve(root, `pentest/results/admin-ai-provider-${width}.png`), fullPage: true });
    await page.close();
  }
  console.log('PASS clone AI provider admin browser desktop/mobile');
} finally {
  await browser.close();
}
