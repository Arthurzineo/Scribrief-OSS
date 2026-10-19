import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';
try {
  const page = await browser.newPage({
    viewport: { width: 390, height: 800 }, ignoreHTTPSErrors: true,
  });
  page.setDefaultTimeout(5000);
  let completed = 2;
  await page.route('**/api/v1/**', (route) => {
    const url = route.request().url();
    let data = {};
    if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
    else if (url.match(/\/meetings\/1\/progress\/$/)) data = {
      stage: completed === 5 ? 'finalizando' : 'transcrevendo',
      completed_chunks: completed, total_chunks: 5, percent: completed === 5 ? 99 : 40,
    };
    else if (url.match(/\/meetings\/1\/$/)) data = {
      id: '1', title: 'Reunião longa', status: 'transcrevendo',
      audio_available: false,
    };
    else if (url.match(/\/meetings\/$/)) data = { count: 1, results: [] };
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'Ver progresso' }).click();
  await page.getByText('2 de 5 blocos concluídos · 40%').waitFor();
  assert.equal(await page.getByRole('progressbar', { name: 'Blocos transcritos' }).getAttribute('value'), '40');
  completed = 5;
  await page.getByText('Todos os blocos foram transcritos. Finalizando…').waitFor({ timeout: 6000 });
  await page.getByText('5 de 5 blocos concluídos · 99%').waitFor();
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    false,
  );
  console.log('Progresso da transcrição: blocos, porcentagem e atualização validados.');
} finally {
  await browser.close();
}
