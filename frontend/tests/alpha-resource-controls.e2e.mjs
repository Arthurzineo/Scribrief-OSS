// Synthetic UI contract/export test: does not touch the installed alpha or OpenAI.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { chromium } from 'playwright-core';

const port = process.env.ALPHA_UI_TEST_PORT || '18774';
const base = `http://127.0.0.1:${port}`;
const server = spawn(process.execPath, ['node_modules/vite/bin/vite.js', 'preview',
  '--host', '127.0.0.1', '--port', port, '--strictPort'], { stdio: 'ignore' });
let browser;
try {
  let started = false;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try { if ((await fetch(base)).ok) { started = true; break; } } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.ok(started, 'isolated preview server did not start');
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_PATH ||
    (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : '/usr/bin/google-chrome') });
  for (const width of [390, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = []; const saved = []; let aiRequests = 0;
    const sector = { id: 1, name: 'Sintético', slug: 'sintetico', is_active: true,
      monthly_ai_budget_usd: '10.00', member_count: 1 };
    page.on('pageerror', (error) => errors.push(error.message));
    await page.context().addCookies([{ name: 'csrftoken', value: 'synthetic', url: base }]);
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url()); const path = url.pathname;
      const method = route.request().method(); let data = {};
      if (path.endsWith('/session/')) data = { user: { id: 1, username: 'synthetic-admin', name: 'Admin', is_staff: true } };
      else if (path.includes('/api/admin/sectors/choices/')) data = [sector];
      else if (path.includes('/api/admin/sectors/')) {
        if (method !== 'GET') { saved.push(route.request().postDataJSON()); data = sector; }
        else data = { count: 1, results: [sector] };
      } else if (path.includes('/api/admin/users/')) {
        if (method !== 'GET') saved.push(route.request().postDataJSON());
        data = { count: 1, results: [{ id: 2, username: 'colega', sector_id: 1, sector_name: 'Sintético', is_active: true }] };
      } else if (path.includes('/usage/summary/')) data = {
        totals: { calls: 0, failed: 0, unavailable: 0, estimated_total_usd: '0', minutes_usd: '0' }, by_user: [], by_sector: [],
      };
      else if (path.includes('/usage/budget/')) data = { period: '2026-10', sector_id: 1,
        sector_limit_usd: '10.00', sector_used_usd: '0.25', sector_remaining_usd: '9.75' };
      else if (path.includes('/usage/')) data = { count: 0, results: [] };
      else if (path.includes('/mind-map/')) {
        if (method === 'POST') aiRequests += 1;
        data = { status: 'ready', version: 1, mapa: { centro: 'Teste alpha', ramos: [
          { titulo: 'Recursos', pontos: ['Orçamento', '<img src=x onerror=alert(1)>'] },
        ] } };
      } else if (path.includes('/minutes/')) data = { version: 1, topicos: [], decisoes: [], tarefas: [], participantes: [] };
      else if (path.includes('/speakers/')) data = { version: 1, falantes: [] };
      else if (path.includes('/transcription/')) data = { version: 1, falantes: {}, segmentos: [] };
      else if (path.endsWith('/meetings/synthetic/')) data = { id: 'synthetic', title: 'Mapa sintético', status: 'ata_pronta', minutes_version: 1, can_edit: true };
      else if (path.includes('/meetings/')) data = { count: 0, results: [] };
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${base}/admin`, { waitUntil: 'networkidle' });
    await page.getByLabel('Nome', { exact: true }).fill('Novo setor');
    await page.getByLabel('Identificador', { exact: true }).fill('novo-setor');
    await page.getByLabel('Teto mensal estimado de IA do setor (US$)', { exact: true }).fill('12.50');
    await page.getByRole('button', { name: 'Salvar setor', exact: true }).click();
    await page.getByText('Setor salvo.', { exact: true }).waitFor();
    assert.equal(saved[0].monthly_ai_budget_usd, '12.50');
    await page.getByRole('tab', { name: 'Usuários', exact: true }).click();
    await page.getByLabel('Usuário', { exact: true }).fill('novo');
    await page.getByRole('combobox').first().selectOption('1');
    await page.getByLabel('Senha temporária', { exact: true }).fill('Synthetic-UI-Password-123');
    await page.getByLabel('Teto mensal estimado de IA deste usuário (US$)', { exact: true }).fill('2.25');
    await page.getByRole('button', { name: 'Salvar usuário', exact: true }).click();
    await page.getByText('Usuário salvo.', { exact: true }).waitFor();
    assert.equal(saved[1].monthly_ai_budget_usd, '2.25');
    await page.getByRole('tab', { name: 'Custos e uso', exact: true }).click();
    await page.getByRole('combobox').first().selectOption('1');
    await page.getByRole('button', { name: 'Filtrar', exact: true }).click();
    await page.getByRole('region', { name: 'Orçamento mensal de IA' }).waitFor();
    assert.ok(await page.getByText(/restante US\$ 9.75/).isVisible());
    await page.goto(`${base}/reunioes/synthetic/mapa/`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: 'Teste alpha', exact: true }).waitFor();
    assert.equal(await page.locator('.mind-map__card img').count(), 0);
    for (const [format, signature] of [['PNG', '89504e470d0a1a0a'], ['PDF', '255044462d']]) {
      const promise = page.waitForEvent('download');
      await page.getByRole('button', { name: `Baixar ${format}` }).click();
      const bytes = await readFile(await (await promise).path());
      assert.equal(bytes.subarray(0, signature.length / 2).toString('hex'), signature);
    }
    assert.equal(aiRequests, 0); assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Alpha UI: budgets, escaped map and PNG/PDF passed at 390/1440px (mock APIs).');
} finally {
  await browser?.close(); server.kill();
}
