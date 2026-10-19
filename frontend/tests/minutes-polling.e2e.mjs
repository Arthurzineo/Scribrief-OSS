import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';

try {
  const page = await browser.newPage({ ignoreHTTPSErrors: true });
  // MVT protects the document before API interception. Serve the built SPA shell
  // for this isolated UI test; JS/CSS still come from the target web server.
  const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8');
  await page.route('**/reunioes/1/ata', (route) => route.fulfill({
    status: 200, contentType: 'text/html', body: html,
  }));
  const calls = { detail: 0, status: 0, transcript: 0, speakers: 0, minutes: 0 };
  const state = { status: 'gerando_ata', minutesStuck: false, errorCode: '' };
  const transcriptSegments = Array.from({ length: 1200 }, (_, index) => ({
    id: index + 1, falante_id: 'A', inicio: index * 2, fim: index * 2 + 1,
    texto: `Linha ${index + 1}: falamos do prazo da reunião e dos próximos passos.`,
  }));
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/v1/**', (route) => {
    const url = route.request().url();
    let data = {};
    if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
    else if (url.match(/\/meetings\/1\/status\/$/)) {
      calls.status += 1;
      data = { status: state.status, minutes_stuck: state.minutesStuck,
        error_code: state.errorCode, error_message: state.errorCode ? 'Falha de teste.' : '' };
    } else if (url.match(/\/meetings\/1\/transcription\/$/)) {
      calls.transcript += 1;
      data = { version: 1, falantes: { A: 'Ana' }, segmentos: transcriptSegments };
    } else if (url.match(/\/meetings\/1\/speakers\/$/)) {
      calls.speakers += 1;
      data = { falantes: [{ falante_id: 'A', nome: 'Ana' }] };
    } else if (url.match(/\/meetings\/1\/minutes\/$/)) {
      calls.minutes += 1;
      data = { version: 1, resumo_executivo: 'Prazo combinado.', topicos: [
        { titulo: 'Prazo', comentario: 'Equipe definiu a data.' },
      ], decisoes: [], tarefas: [], participantes: ['Ana'] };
    } else if (url.match(/\/meetings\/1\/$/)) {
      calls.detail += 1;
      data = { id: '1', title: 'Teste de polling', meeting_date: '2026-10-13',
        status: state.status, minutes_stuck: state.minutesStuck,
        error_code: state.errorCode, error_message: state.errorCode ? 'Falha de teste.' : '',
        minutes_version: 1, audio_available: false, can_edit: true };
    } else if (url.match(/\/meetings\/$/)) data = { count: 0, results: [] };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });

  await page.goto(`${base}/reunioes/1/ata`, { waitUntil: 'networkidle' });
  await page.getByText('Resumo, decisões e tarefas a partir da transcrição.').waitFor();
  const initial = { ...calls }; // StrictMode in development can mount and fetch twice.
  assert.ok(initial.detail >= 1);
  assert.equal(initial.transcript, initial.detail);
  await page.waitForTimeout(3700);
  assert.ok(calls.status >= 1, 'a geração deve consultar o endpoint leve de status');
  assert.equal(calls.detail, initial.detail, 'não repetir GET da reunião durante a geração');
  assert.equal(calls.transcript, initial.transcript, 'não baixar transcrição novamente durante a geração');
  assert.equal(calls.speakers, initial.speakers, 'não baixar falantes novamente durante a geração');
  assert.equal(calls.minutes, 0, 'ata ainda não pronta');

  state.status = 'ata_pronta';
  await page.getByText('Equipe definiu a data.').waitFor({ timeout: 7000 });
  assert.equal(calls.detail, initial.detail + 1, 'ao concluir, carregar a reunião uma vez');
  assert.equal(calls.transcript, initial.transcript + 1);
  assert.equal(calls.speakers, initial.speakers + 1);
  assert.equal(calls.minutes, 1);
  await page.waitForTimeout(3200);
  assert.equal(calls.status, 2, 'parar polling após a conclusão');

  // A rota leve também deve manter a detecção de jobs que ficaram travados.
  state.status = 'gerando_ata';
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByText('Resumo, decisões e tarefas a partir da transcrição.').waitFor();
  const beforeStuck = { ...calls };
  state.minutesStuck = true;
  await page.getByRole('button', { name: 'Tentar novamente' }).waitFor({ timeout: 7000 });
  assert.equal(calls.detail, beforeStuck.detail + 1);
  assert.equal(calls.transcript, beforeStuck.transcript + 1);
  const afterStuck = calls.status;
  await page.waitForTimeout(3200);
  assert.equal(calls.status, afterStuck, 'parar polling ao detectar ata travada');

  // Falha explícita do worker igualmente encerra o polling e mostra a mensagem.
  state.minutesStuck = false;
  state.status = 'gerando_ata';
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByText('Resumo, decisões e tarefas a partir da transcrição.').waitFor();
  state.status = 'erro';
  state.errorCode = 'minutes_failed';
  await page.getByText('Falha de teste.').waitFor({ timeout: 7000 });
  assert.ok(await page.getByRole('button', { name: 'Tentar novamente' }).isVisible());
  assert.deepEqual(errors, []);
  console.log('Polling da ata: status leve, conclusão, falha e job travado validados.');
} finally {
  await browser.close();
}
