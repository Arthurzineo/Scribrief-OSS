import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';

async function check(width, role) {
  const page = await browser.newPage({ viewport: { width, height: 800 }, ignoreHTTPSErrors: true });
  const writes = [];
  let shared = role !== 'owner';
  try {
    await page.route('**/api/v1/**', (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (method !== 'GET') writes.push(`${method} ${new URL(url).pathname}`);
      let data = {};
      let status = 200;
      if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
      else if (url.match(/\/meetings\/1\/sharing\/$/)) {
        shared = route.request().postDataJSON().shared_with_sector;
        data = { shared_with_sector: shared, access_version: 2 };
      } else if (url.match(/\/meetings\/1\/transcription\/$/)) data = {
        version: 1, falantes: { A: 'Ana' },
        segmentos: [{ id: 1, falante_id: 'A', inicio: 0, fim: 5, texto: 'Pauta de teste.' }],
      };
      else if (url.match(/\/meetings\/1\/speakers\/$/)) data = {
        version: 1, falantes: [{ falante_id: 'A', nome: 'Ana' }],
      };
      else if (url.match(/\/meetings\/1\/minutes\/$/)) data = {
        version: 1, resumo_executivo: 'Resumo', topicos: [{ titulo: 'Pauta', comentario: 'Discussão.' }],
        decisoes: [], tarefas: [], participantes: ['Ana'],
      };
      else if (url.match(/\/meetings\/1\/mind-map\/$/)) data = {
        centro: 'Pauta', ramos: [{ titulo: 'Tema', pontos: ['Decisão'] }], status: 'ready',
      };
      else if (url.match(/\/sector-members\/$/)) data = { members: [{ id: 1, name: 'Ana' }, { id: 2, name: 'Bruno' }] };
      else if (url.match(/\/meetings\/1\/$/)) {
        if (role === 'other' || (role === 'colleague' && !shared)) status = 404;
        else data = {
          id: '1', title: 'Reunião compartilhada', meeting_date: '2026-10-09', status: 'ata_pronta',
          audio_available: false, can_edit: role === 'owner', owner_name: 'Ana', owner_id: 1,
          shared_with_sector: shared, access_version: shared ? 2 : 1,
        };
      } else if (url.match(/\/meetings\/$/)) data = { count: 0, results: [] };
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
    if (role === 'other') {
      await page.getByText('Reunião não encontrada.').waitFor();
      return;
    }
    await page.getByRole('heading', { name: 'Reunião compartilhada' }).waitFor();
    if (role === 'owner') {
      assert.equal(await page.getByRole('button', { name: 'Permitir leitura ao setor' }).count(), 1);
      await page.getByRole('button', { name: 'Permitir leitura ao setor' }).click();
      await page.getByRole('button', { name: 'Revogar acesso do setor' }).waitFor();
      assert.ok(writes.some((item) => item.endsWith('/meetings/1/sharing/')));
      assert.equal(await page.getByRole('button', { name: 'Excluir reunião' }).count(), 1);
    } else {
      await page.getByText('Somente o dono pode editar ou excluir.').waitFor();
      for (const forbidden of ['Editar nome da reunião', 'Excluir reunião', 'Gerar ata', 'IA ajuda a corrigir a transcrição']) {
        assert.equal(await page.getByRole('button', { name: forbidden }).count(), 0, `${width}px ${forbidden}`);
      }
      assert.equal(await page.getByRole('button', { name: 'Baixar transcrição' }).count(), 1);
      await page.getByRole('tab', { name: 'Ata' }).click();
      await page.getByText('Ata compartilhada em modo leitura.').waitFor();
      assert.equal(await page.getByRole('button', { name: 'Marcar ata como revisada' }).count(), 0);
      assert.equal(await page.getByRole('button', { name: 'Baixar', exact: true }).count(), 1);
      await page.getByRole('tab', { name: 'Mapa mental' }).click();
      assert.equal(writes.length, 0, `viewer ${width}px não pode enviar mutação`);
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
  } finally { await page.close(); }
}

try {
  for (const width of [1440, 390]) {
    for (const role of ['owner', 'colleague', 'other']) await check(width, role);
  }
  console.log('Partilha: dono, colega e outro setor em desktop/móvel.');
} finally { await browser.close(); }
