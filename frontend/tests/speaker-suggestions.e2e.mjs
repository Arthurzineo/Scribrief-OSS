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
  let mergePayload = null;
  await page.route('**/api/v1/**', (route) => {
    const url = route.request().url();
    let data = {};
    if (url.includes('/session/')) data = { user: { name: 'Ana', username: 'ana' } };
    else if (url.match(/\/meetings\/1\/speakers\/$/)) data = {
      version: 1, falantes: [
        { falante_id: 'A', nome: 'Ana' },
        { falante_id: 'B', nome: 'Bruno' },
        { falante_id: 'C', nome: 'Carla' },
      ],
    };
    else if (url.match(/\/meetings\/1\/transcription\/$/)) data = {
      version: 1, falantes: { A: 'Ana', B: 'Bruno', C: 'Carla' },
      segmentos: ['A', 'B', 'C'].map((code, index) => ({
        id: index + 1, falante_id: code, inicio: index * 10,
        fim: index * 10 + 4, texto: `Fala ${code}`,
      })),
    };
    else if (url.match(/\/meetings\/1\/speaker-suggestions\/$/)) data = route.request().method() === 'POST'
      ? { status: 'ready', remaining: 1, groups: [['A', 'B', 'C']], caution: true,
        sample_times: { A: [0, 2], B: [10, 12], C: [20, 22] } }
      : { status: 'none', remaining: 2, groups: [], caution: false, sample_times: {} };
    else if (url.match(/\/meetings\/1\/speaker-suggestions\/dismiss\/$/)) data = {
      status: 'dismissed', remaining: 1, groups: [], caution: false, sample_times: {},
    };
    else if (url.match(/\/meetings\/1\/speakers\/merge-batch\/$/)) {
      mergePayload = route.request().postDataJSON();
      data = { version: 2 };
    } else if (url.match(/\/meetings\/1\/$/)) data = {
      id: '1', title: 'Reunião de teste', status: 'transcrito',
      transcription_version: mergePayload ? 2 : 1, audio_available: true,
    };
    else if (url.match(/\/meetings\/1\/audio\/$/)) {
      return route.fulfill({ status: 404, body: '' });
    }
    else if (url.match(/\/meetings\/$/)) data = { count: 1, results: [] };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
  });
  await page.goto(`${base}/reunioes/1`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: 'IA sugere uniões' }).click();
  await page.getByText('A IA deu o mesmo rótulo a todas as amostras.').waitFor();
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
    false,
  );
  const confirm = page.getByRole('button', { name: 'Confirmar e unir selecionados' });
  assert.equal(await confirm.isDisabled(), true);
  await page.getByRole('checkbox', { name: 'Ana (A)' }).check();
  await page.getByRole('checkbox', { name: 'Bruno (B)' }).check();
  assert.equal(await confirm.isEnabled(), true);
  await confirm.click();
  await page.getByRole('dialog', { name: 'Confirmar união sugerida?' })
    .getByRole('button', { name: 'Confirmar e unir' }).click();
  await page.getByText('Falantes unidos após sua confirmação.').waitFor();
  assert.deepEqual(mergePayload, { sources: ['B'], target: 'A', version: 1 });
  console.log('Sugestão de falantes: revisão humana e união seletiva verificadas.');
  await page.close();
} finally {
  await browser.close();
}
