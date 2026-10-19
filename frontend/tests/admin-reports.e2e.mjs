import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';

const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const base = process.env.E2E_ADMIN_BASE_URL || 'https://127.0.0.1:18575';

try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
    const queries = [];
    // O Django protege /admin no MVT; este ensaio de relatórios usa um documento
    // sintético e APIs simuladas, sem tentar contornar a autenticação real.
    await page.route(`${base}/admin`, (route) => route.fulfill({
      status: 200, contentType: 'text/html',
      body: '<!doctype html><html lang="pt-BR"><head><link rel="stylesheet" href="/assets/style.css"></head><body><div id="root" data-mvt="1"></div><script type="module" src="/assets/app.js"></script></body></html>',
    }));
    await page.route('**/api/**', (route) => {
      const url = new URL(route.request().url());
      queries.push(`${url.pathname}${url.search}`);
      let data = { count: 0, results: [], next: null };
      if (url.pathname.endsWith('/session/')) data = { user: { id: 1, username: 'admin_local', name: 'Admin', is_staff: true } };
      else if (url.pathname.endsWith('/sectors/choices/')) data = [{ id: 1, name: 'TI' }];
      else if (url.pathname.endsWith('/usage/summary/')) data = {
        totals: { calls: 2, failed: 1, unavailable: 1, estimated_total_usd: '0.01', minutes_usd: '0.01' },
        by_user: [], by_sector: [],
      };
      else if (url.pathname.endsWith('/jobs/summary/')) data = {
        totals: { requests: 120, queued: 0, running: 3, failed: 0, cancelled: 0, uploaded_media_seconds: '36000' },
        by_user: [], by_sector: [],
      };
      else if (url.pathname.endsWith('/jobs/worker-health/')) data = { status: 'responding', responding_workers: 1 };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    });
    try {
      await page.goto(`${base}/admin`, { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: 'Administração' }).waitFor();
      await page.getByRole('tab', { name: 'Execuções' }).click();
      await page.getByRole('heading', { name: 'Execuções' }).waitFor();
      await page.getByLabel('Estado').selectOption('running');
      await page.getByRole('button', { name: 'Filtrar' }).click();
      await page.getByText('Processadores de tarefas respondendo:').waitFor();
      assert.ok(queries.some((value) => value.includes('/jobs/summary/?') && value.includes('status=running')));
      await page.getByRole('tab', { name: 'Custos e uso' }).click();
      await page.getByText('tentativas falhas').waitFor();
      await page.getByRole('tab', { name: 'Auditoria' }).click();
      await page.getByRole('heading', { name: 'Auditoria' }).waitFor();
      await page.getByText('Eventos de auditoria são mantidos por 90 dias', { exact: false }).waitFor();
      await page.getByLabel('Ação').fill('login');
      await page.getByRole('button', { name: 'Filtrar' }).click();
      assert.ok(queries.some((value) => value.includes('/audit/?') && value.includes('action=login')));
      const exportHref = await page.getByRole('link', { name: 'Baixar auditoria JSONL' }).getAttribute('href');
      assert.ok(exportHref.includes('action=login'));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    } finally { await page.close(); }
  }
  console.log('Relatórios administrativos: filtros e estados em desktop/móvel.');
} finally { await browser.close(); }
