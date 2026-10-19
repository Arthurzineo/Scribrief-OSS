import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const values = Object.fromEntries((await readFile(resolve(root, 'pentest/.env'), 'utf8'))
  .split(/\r?\n/).filter((line) => line && !line.startsWith('#'))
  .map((line) => line.split(/=(.*)/s).slice(0, 2)));
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.2:18674';

try {
  for (const width of [390, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 800 }, ignoreHTTPSErrors: true });
    await page.goto(`${base}/login/`, { waitUntil: 'networkidle' });
    await page.getByLabel('Usuário').fill('pt_owner');
    await page.getByLabel('Senha').fill(values.PENTEST_OWNER_PASSWORD);
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.getByRole('heading', { name: 'Reuniões', exact: true }).waitFor();
    const meetings = await page.evaluate(async () =>
      fetch('/api/v1/meetings/', { credentials: 'same-origin' }).then((response) => response.json()));
    const id = meetings.results.find((row) => row.title === 'PENTEST — privada')?.id;
    assert.ok(id, 'clone fixture missing');
    const state = {
      meetingStatus: 'ata_pronta', mapStatus: 'ready', mapRequests: 0,
      map: { centro: 'Planejamento do encontro', ramos: [
        { titulo: 'Logística', pontos: ['Café aprovado', 'Prazo 21/10'] },
        { titulo: 'Custos', pontos: ['Orçamento revisado', '<img src=x onerror=alert(1)>'] },
      ] },
    };
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('**/api/v1/**', (route) => {
      const url = route.request().url();
      let data = {};
      if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
      else if (url.includes(`/meetings/${id}/mind-map/`)) {
        if (route.request().method() === 'POST') {
          state.mapRequests += 1;
          state.mapStatus = 'ready';
          data = { status: 'generating' };
        } else data = {
          status: state.mapStatus, version: 1,
          mapa: state.mapStatus === 'ready' ? state.map : null,
        };
      } else if (url.includes(`/meetings/${id}/minutes/`)) data = {
        version: 1, resumo_executivo: 'Parágrafo longo da ata que não deve aparecer no mapa.',
        topicos: [{ titulo: 'Logística', comentario: 'Detalhes extensos sobre o café.' }],
        decisoes: [], tarefas: [], participantes: [], revisor: null, revisado_em: null,
      };
      else if (url.includes(`/meetings/${id}/speakers/`)) data = {
        version: 1, falantes: [{ falante_id: 'A', nome: 'Ana' }],
      };
      else if (url.includes(`/meetings/${id}/transcription/`)) data = {
        version: 1, falantes: { A: 'Ana' },
        segmentos: [{ id: 1, falante_id: 'A', inicio: 0, fim: 10, texto: 'Bom dia' }],
      };
      else if (url.endsWith(`/meetings/${id}/`)) data = {
        id, title: 'Reunião de teste', meeting_date: '2026-10-09',
        status: state.meetingStatus, minutes_version: 1, audio_available: false, can_edit: true,
      };
      else if (url.match(/\/meetings\//)) data = { count: 0, results: [] };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${base}/reunioes/${id}/mapa/`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: 'Planejamento do encontro' }).waitFor();
    assert.equal(await page.locator('.mind-map__branch').count(), 2);
    assert.equal(await page.locator('.mind-map__card').count(), 4);
    assert.equal(await page.getByText('Parágrafo longo da ata que não deve aparecer no mapa.').count(), 0);
    assert.equal(await page.locator('.mind-map__card img').count(), 0);
    assert.ok(await page.locator('.mind-map__card').getByText('<img src=x onerror=alert(1)>').isVisible());
    const geometry = await page.evaluate(() => {
      const viewport = document.querySelector('.mind-map__viewport');
      const canvas = document.querySelector('.mind-map__canvas');
      const branches = [...document.querySelectorAll('.mind-map__branch')];
      return {
        viewportWidth: viewport.clientWidth, scrollWidth: viewport.scrollWidth,
        canvasWidth: canvas.getBoundingClientRect().width,
        branchOverlap: branches[0].getBoundingClientRect().right > branches[1].getBoundingClientRect().left,
      };
    });
    assert.ok(geometry.canvasWidth >= 1120, JSON.stringify(geometry));
    assert.equal(geometry.branchOverlap, false, JSON.stringify(geometry));
    if (width === 390) assert.ok(geometry.scrollWidth > geometry.viewportWidth, JSON.stringify(geometry));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    for (const [format, signature] of [['PNG', '89504e470d0a1a0a'], ['PDF', '255044462d']]) {
      const downloadPromise = page.waitForEvent('download');
      await page.getByRole('button', { name: `Baixar ${format}` }).click();
      const download = await downloadPromise;
      const bytes = await readFile(await download.path());
      assert.equal(bytes.subarray(0, signature.length / 2).toString('hex'), signature);
      if (format === 'PNG') assert.equal(bytes.readUInt32BE(16), 1120);
    }
    await page.getByRole('button', { name: 'Gerar novamente' }).click();
    await page.getByRole('heading', { name: 'Planejamento do encontro' }).waitFor({ timeout: 10000 });
    assert.equal(state.mapRequests, 1);
    state.meetingStatus = 'transcrito';
    await page.reload({ waitUntil: 'networkidle' });
    assert.ok(await page.getByText(/Ainda não há ata/).isVisible());
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Mapa compacto: conteúdo, exportação, regeneração e segurança validados.');
} finally {
  await browser.close();
}
