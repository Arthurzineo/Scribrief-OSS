import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';
const segments = Array.from({ length: 100 }, (_, i) => ({
  id: i + 1, falante_id: ['A', 'B', 'C'][i % 3], inicio: i * 10, fim: i * 10 + 8,
  texto: `Fala de teste ${i + 1}: texto suficientemente longo para ocupar a coluna de leitura.`,
}));

try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 800 }, ignoreHTTPSErrors: true });
    let title = 'Reunião de teste';
    let mergePayload = null;
    await page.route('**/api/v1/**', (route) => {
      const url = route.request().url();
      let data = {};
      if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
      else if (url.match(/\/meetings\/1\/speakers\/$/)) data = {
        version: 1, falantes: [{ falante_id: 'A', nome: 'Ana' }, { falante_id: 'B', nome: 'Bruno' }, { falante_id: 'C', nome: 'Carla' }],
      };
      else if (url.match(/\/meetings\/1\/transcription\/$/)) data = {
        version: 1, falantes: { A: 'Ana', B: 'Bruno', C: 'Carla' }, segmentos: segments,
      };
      else if (url.match(/\/meetings\/1\/speakers\/merge-batch\/$/)) {
        mergePayload = route.request().postDataJSON();
        data = { version: 2 };
      }
      else if (url.match(/\/meetings\/1\/$/)) data = {
        id: '1', title: route.request().method() === 'PATCH' ? (title = route.request().postDataJSON().title) : title,
        meeting_date: '2026-10-09',
        status: 'transcrito', audio_available: false,
      };
      else if (url.match(/\/meetings\//)) data = { count: 1, results: [] };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: 'Falantes' }).waitFor();
    const read = page.locator('.mt__read');
    const before = await read.evaluate((element) => ({
      scrollHeight: element.scrollHeight, clientHeight: element.clientHeight,
      scrollTop: element.scrollTop, pageScroll: window.scrollY,
    }));
    assert.ok(before.scrollHeight > before.clientHeight, `${width}px: falas devem ter rolagem interna`);
    await read.evaluate((element) => element.scrollTo({ top: 500, behavior: 'instant' }));
    const after = await read.evaluate((element) => ({
      scrollTop: element.scrollTop, pageScroll: window.scrollY,
    }));
    assert.ok(after.scrollTop > before.scrollTop, `${width}px: a lista não rolou`);
    assert.equal(after.pageScroll, before.pageScroll, `${width}px: a página rolou junto`);
    assert.equal(await page.locator('.mt__panel').count(), 2);
    assert.equal(await page.locator('.mt__panel').first().getByRole('button', { name: 'Gerar ata' }).count(), 0);
    assert.equal(await page.locator('.mt__panel--actions').getByRole('button', { name: 'Gerar ata' }).count(), 1);
    assert.ok(await page.locator('.mt__player').isVisible());
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    await page.getByRole('checkbox', { name: 'Selecionar Ana' }).check();
    await page.getByRole('checkbox', { name: 'Selecionar Bruno' }).check();
    await page.getByRole('checkbox', { name: 'Selecionar Carla' }).check();
    assert.equal(await page.getByRole('button', { name: 'Unir com outro falante' }).count(), 0);
    assert.equal(await page.locator('.mt__panel--merge').count(), 1);
    assert.equal(await page.locator('.mt__panel').first().locator('.mt__batch-merge').count(), 0);
    await page.getByLabel('Manter como').selectOption('C');
    await page.getByRole('button', { name: 'Unir selecionados' }).click();
    await page.getByRole('dialog', { name: 'Unir falantes selecionados?' }).getByRole('button', { name: 'Unir falantes' }).click();
    await page.getByText('Falantes selecionados unidos.').waitFor();
    assert.deepEqual(mergePayload, { sources: ['A', 'B'], target: 'C', version: 1 });
    await page.getByRole('button', { name: 'Editar nome da reunião' }).click();
    await page.getByLabel('Nome da reunião').fill('Nome atualizado');
    await page.getByRole('button', { name: 'Salvar' }).click();
    await page.getByRole('heading', { name: 'Nome atualizado' }).waitFor();
    await page.close();
  }
  console.log('Transcrição: rolagem interna e painéis separados em desktop e móvel.');
} finally {
  await browser.close();
}
