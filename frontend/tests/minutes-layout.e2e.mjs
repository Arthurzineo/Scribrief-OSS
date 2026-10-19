import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = await chromium.launch({ executablePath: chrome, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 800 }, ignoreHTTPSErrors: true });
  await page.route('**/api/v1/**', (route) => {
    const url = route.request().url();
    let data = {};
    if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
    else if (url.match(/\/meetings\/1\/minutes\/$/)) data = {
      version: 1, resumo_executivo: 'Resumo',
      topicos: [{ titulo: 'Pauta', comentario: 'Teste.' }], decisoes: [],
      tarefas: [{ descricao: 'Providenciar café', responsavel: 'Bruno', prazo: '21/10/2026' }],
      participantes: ['Ana', 'Bruno'], revisor: null, revisado_em: null,
    };
    else if (url.match(/\/meetings\/1\/speakers\/$/)) data = { version: 1, falantes: [{ falante_id: 'A', nome: 'Ana' }] };
    else if (url.match(/\/meetings\/1\/transcription\/$/)) data = {
      version: 1, falantes: { A: 'Ana' },
      segmentos: [{ id: 1, falante_id: 'A', inicio: 0, fim: 10, texto: 'Bom dia' }],
    };
    else if (url.match(/\/meetings\/1\/$/)) data = {
      id: '1', title: 'Reunião', meeting_date: '2026-10-09',
      status: 'ata_pronta', minutes_version: 1, audio_available: false,
    };
    else if (url.match(/\/meetings\//)) data = { count: 1, results: [] };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto(process.env.E2E_BASE_URL || 'https://127.0.0.1:18574/reunioes/1/ata', { waitUntil: 'networkidle' });
  const overflow = await page.locator('.tbl-wrap').count()
    ? await page.locator('.tbl-wrap').evaluate((element) => element.scrollWidth - element.clientWidth)
    : 0;
  assert.equal(overflow, 0, `Tabela de tarefas exige rolagem horizontal de ${overflow}px.`);
  const task = page.locator('.doc__task').first();
  await task.waitFor();
  const metrics = await task.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    scrollWidth: element.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    right: element.getBoundingClientRect().right,
  }));
  assert.ok(metrics.scrollWidth <= metrics.width + 1, `Campos da tarefa extrapolam: ${JSON.stringify(metrics)}`);
  assert.ok(metrics.right <= metrics.viewportWidth, `Tarefa ultrapassa a tela: ${JSON.stringify(metrics)}`);
  await task.getByLabel('Tarefa/ação').fill('Providenciar café e água');
  await task.getByLabel('Responsável').fill('Bruno');
  await task.getByLabel('Prazo').fill('21/10/2026');
  const remove = task.getByRole('button', { name: 'Remover tarefa' });
  assert.ok(await remove.isVisible());
  const box = await remove.boundingBox();
  assert.ok(box.x >= 0 && box.x + box.width <= metrics.viewportWidth);
  const fields = await task.locator('.doc__task-fields').boundingBox();
  assert.ok(box.y >= fields.y + fields.height, 'Remover tarefa sobrepõe os campos de edição.');
  console.log('Layout móvel da tarefa: campos e remoção acessíveis sem rolagem horizontal.');
} finally {
  await browser.close();
}
