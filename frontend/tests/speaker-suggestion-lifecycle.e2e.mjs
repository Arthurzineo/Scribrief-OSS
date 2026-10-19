import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 800 }, ignoreHTTPSErrors: true });
  let state = 'none';
  let uses = 0;
  let groups = [];
  let requests = 0;
  await page.route('**/api/v1/**', (route) => {
    const url = route.request().url();
    let data = {};
    if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
    else if (url.match(/\/meetings\/1\/speakers\/$/)) data = {
      version: 1, falantes: ['A', 'B', 'C'].map((code) => ({ falante_id: code, nome: code })),
    };
    else if (url.match(/\/meetings\/1\/transcription\/$/)) data = {
      version: 1, falantes: { A: 'A', B: 'B', C: 'C' },
      segmentos: ['A', 'B', 'C'].map((code, index) => ({
        id: index + 1, falante_id: code, inicio: index * 10, fim: index * 10 + 4,
        texto: `Fala ${code}`,
      })),
    };
    else if (url.match(/\/meetings\/1\/speaker-suggestions\/dismiss\/$/)) {
      groups = [];
      state = 'dismissed';
      data = { status: state, uses, remaining: 2 - uses, groups, caution: false, sample_times: {} };
    } else if (url.match(/\/meetings\/1\/speaker-suggestions\/$/)) {
      if (route.request().method() === 'POST') {
        uses += 1;
        requests += 1;
        state = 'processing';
      }
      data = { status: state, uses, remaining: 2 - uses, groups, caution: false, sample_times: {} };
    } else if (url.match(/\/meetings\/1\/$/)) data = {
      id: '1', title: 'Reunião de teste', status: 'transcrito',
      transcription_version: 1, audio_available: true,
    };
    else if (url.match(/\/meetings\/1\/audio\/$/)) return route.fulfill({ status: 404, body: '' });
    else if (url.match(/\/meetings\/$/)) data = { count: 1, results: [] };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
  await page.getByText('2 de 2 análises disponíveis nesta reunião.').waitFor();
  await page.getByRole('button', { name: 'IA sugere uniões' }).click();
  await page.getByText('A análise continua em segundo plano.').waitFor();
  await page.goto(`${base}/`, { waitUntil: 'networkidle' });
  state = 'ready';
  groups = [['A', 'B']];
  await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
  await page.getByRole('checkbox', { name: 'A (A)' }).waitFor();
  await page.getByText('1 de 2 análises disponíveis nesta reunião.').waitFor();
  await page.getByRole('button', { name: 'Ignorar' }).click();
  await page.getByText('Sugestão ignorada.').waitFor();
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.getByRole('checkbox', { name: 'A (A)' }).count(), 0);
  await page.getByRole('button', { name: 'IA sugere uniões' }).click();
  await page.getByText('0 de 2 análises disponíveis nesta reunião.').waitFor();
  assert.equal(await page.getByRole('button', { name: 'IA comparando vozes…' }).isDisabled(), true);
  assert.equal(requests, 2);
  console.log('Sugestões persistem ao navegar, rejeição persiste e quota aparece na interface.');
} finally {
  await browser.close();
}
