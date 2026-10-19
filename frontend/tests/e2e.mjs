import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const base = process.env.E2E_BASE_URL || 'https://127.0.0.1:18574';
const username = process.env.E2E_USERNAME;
const password = process.env.E2E_PASSWORD;
const chrome = process.env.CHROME_PATH;
if (!username || !password || !chrome) {
  throw new Error('Set E2E_USERNAME, E2E_PASSWORD and CHROME_PATH for the local browser smoke test.');
}

const browser = await chromium.launch({ executablePath: chrome, headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: true });
const failures = [];
page.on('pageerror', (error) => failures.push(error.message));
try {
  await mkdir('.artifacts', { recursive: true });
  await page.goto(base, { waitUntil: 'networkidle' });
  assert.equal(await page.title(), 'Entrar · Scribrief');
  await page.getByRole('heading', { name: 'Scribrief' }).waitFor();
  await page.getByLabel('Usuário').fill(username);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.getByRole('heading', { name: 'Reuniões' }).waitFor();
  const cookies = await page.context().cookies();
  assert.equal(cookies.find((cookie) => cookie.name === 'sessionid')?.secure, true);
  await page.getByRole('link', { name: 'Scribrief' }).first().waitFor();
  await page.screenshot({ path: '.artifacts/reunioes.png', fullPage: true });
  await page.locator('main .at-row').filter({ hasText: 'DEMO — reunião de exemplo' }).click();
  await page.getByRole('heading', { name: 'Falantes' }).waitFor();
  await page.getByRole('button', { name: 'Excluir reunião' }).click();
  await page.getByRole('dialog').getByText('A reunião, a transcrição, a ata e o áudio ficarão ocultos agora.', { exact: false }).waitFor();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancelar' }).click();
  assert.match(await page.locator('main').innerText(), /Vamos revisar o cronograma/);
  const firstSegment = page.locator('.at-utt__seg').first();
  const firstSegmentId = Number((await firstSegment.getAttribute('id')).split('-').at(-1));
  const originalSpeech = await firstSegment.locator('.at-utt__text').innerText();
  const suggestedSpeech = `${originalSpeech} [sugestão de teste]`;
  await page.route('**/correction-suggestions/**', (route) => route.fulfill({
    status: route.request().method() === 'POST' ? 202 : 200,
    json: route.request().method() === 'POST'
      ? { job_id: '00000000-0000-4000-8000-000000000001', status: 'processing' }
      : { job_id: '00000000-0000-4000-8000-000000000001', status: 'ready', version: 1, sugestoes: [{
      segmento_id: firstSegmentId, texto_original: originalSpeech,
      texto_sugerido: suggestedSpeech, motivo: 'Teste de interface.',
    }] },
  }));
  await page.getByRole('button', { name: 'IA ajuda a corrigir a transcrição' }).click();
  await page.getByText('Possível correção · confira ouvindo o áudio').waitFor();
  assert.equal(await firstSegment.locator('.at-utt__text').innerText(), originalSpeech);
  await firstSegment.getByRole('button', { name: 'Negar' }).click();
  assert.equal(await page.locator('.at-utt__suggestion').count(), 0);
  await page.getByRole('button', { name: 'IA ajuda a corrigir a transcrição' }).click();
  await page.route('**/transcription/', (route) => {
    if (route.request().method() === 'PATCH') return route.fulfill({ status: 200, json: {} });
    return route.continue();
  });
  const accepted = page.waitForRequest((request) => request.url().endsWith('/transcription/') && request.method() === 'PATCH');
  await firstSegment.getByRole('button', { name: 'Aceitar' }).click();
  assert.equal((await accepted).postDataJSON().segmentos[0].texto, suggestedSpeech);
  await page.getByText('Correção aceita e salva.').waitFor();
  await page.unroute('**/transcription/');
  await page.unroute('**/correction-suggestions/**');
  if (process.env.E2E_MUTATIONS === 'true') {
  const speaker = page.getByRole('textbox', { name: 'Nome do falante 1' });
  await speaker.fill('Ana QA');
  const renamed = page.waitForResponse((r) => r.url().includes('/speakers/A/') && r.request().method() === 'PATCH');
  await speaker.press('Tab');
  assert.equal((await renamed).status(), 200);
  await page.waitForTimeout(400);
  await speaker.fill('Ana');
  const restored = page.waitForResponse((r) => r.url().includes('/speakers/A/') && r.request().method() === 'PATCH');
  await speaker.press('Tab');
  assert.equal((await restored).status(), 200);
  await page.waitForTimeout(400);
  const utterance = page.getByRole('textbox', { name: 'Texto da fala' }).first();
  const originalText = await utterance.innerText();
  await utterance.fill(`${originalText} [QA]`);
  const edited = page.waitForResponse((r) => r.url().endsWith('/transcription/') && r.request().method() === 'PATCH');
  await utterance.press('Tab');
  assert.equal((await edited).status(), 200);
  await page.waitForTimeout(400);
  await utterance.fill(originalText);
  const restoredText = page.waitForResponse((r) => r.url().endsWith('/transcription/') && r.request().method() === 'PATCH');
  await utterance.press('Tab');
  assert.equal((await restoredText).status(), 200);
  }
  await page.screenshot({ path: '.artifacts/transcricao.png', fullPage: true });
  await page.getByRole('tab', { name: 'Ata', exact: true }).click();
  await page.getByRole('heading', { name: 'Resumo executivo' }).waitFor();
  assert.match(await page.locator('main').innerText(), /Equipe revisou o cronograma/);
  if (process.env.E2E_MUTATIONS === 'true') {
  const summary = page.locator('.doc section').first().locator('p');
  const originalSummary = await summary.innerText();
  await summary.fill(`${originalSummary} [QA]`);
  const saved = page.waitForResponse((r) => r.url().endsWith('/minutes/') && r.request().method() === 'PATCH');
  await summary.press('Tab');
  assert.equal((await saved).status(), 200);
  await page.waitForTimeout(400);
  await summary.fill(originalSummary);
  const savedAgain = page.waitForResponse((r) => r.url().endsWith('/minutes/') && r.request().method() === 'PATCH');
  await summary.press('Tab');
  assert.equal((await savedAgain).status(), 200);
  }
  await page.screenshot({ path: '.artifacts/ata.png', fullPage: true });
  const meetingUrl = page.url().replace(/\/ata$/, '');
  const malicious = '<img src=x onerror=window.__ataXss=1>';
  await page.route('**/transcription/', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.segmentos[0].texto = malicious;
    await route.fulfill({ response, json: data });
  });
  await page.route('**/minutes/', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    data.resumo_executivo = malicious;
    data.topicos = [{ titulo: 'Planejamento', comentario: malicious }];
    await route.fulfill({ response, json: data });
  });
  await page.goto(meetingUrl);
  await page.getByText(malicious).first().waitFor();
  await page.getByRole('tab', { name: 'Ata' }).click();
  await page.getByRole('heading', { name: 'Tópicos discutidos' }).waitFor();
  await page.locator('.doc__topic').getByText(malicious).waitFor();
  assert.equal(await page.locator('img[src="x"]').count(), 0);
  assert.equal(await page.evaluate(() => window.__ataXss), undefined);
  await page.unrouteAll();
  await page.goto(`${base}/reunioes/nova`);
  await page.getByText('MP3, WAV, M4A, MP4 ou WEBM · até 5 GiB').waitFor();
  assert.equal(await page.getByRole('checkbox').isChecked(), false);
  await page.screenshot({ path: '.artifacts/nova-reuniao.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Abrir menu' }).click();
  await page.getByRole('navigation', { name: 'Reuniões' }).getByText('Nova reunião').waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  await page.screenshot({ path: '.artifacts/mobile.png', fullPage: true });
  assert.deepEqual(failures, []);
  console.log('Browser smoke passed: login, meetings, transcript, minutes, no page errors.');
} finally {
  await browser.close();
}
