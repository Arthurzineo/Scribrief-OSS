/** Reproducible README screenshots: local Vite preview + fully mocked, fictitious API. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = resolve(frontend, 'docs/screenshots');
const origin = process.env.SCREENSHOT_ORIGIN || 'http://127.0.0.1:4173';
const browserPath = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';

const sectors = [
  { id: 1, name: 'Equipe Exemplo', slug: 'equipe-exemplo', is_active: true,
    member_count: 2, max_upload_minutes: 180, max_monthly_minutes_per_user: 600 },
  { id: 2, name: 'Projetos de Demonstração', slug: 'projetos-demo', is_active: true,
    member_count: 1, max_upload_minutes: null, max_monthly_minutes_per_user: null },
];
const users = [
  { id: 10, username: 'ana.exemplo', first_name: 'Ana', last_name: 'Exemplo',
    email: '', sector_id: 1, sector_name: 'Equipe Exemplo', is_active: true,
    is_staff: false, must_change_password: false },
  { id: 11, username: 'bruno.teste', first_name: 'Bruno', last_name: 'Teste',
    email: '', sector_id: 1, sector_name: 'Equipe Exemplo', is_active: true,
    is_staff: false, must_change_password: true },
];

const responses = new Map([
  ['/api/v1/session/', { user: { id: 1, username: 'admin.exemplo',
    name: 'Administrador fictício', is_staff: true, must_change_password: false } }],
  ['/api/admin/sectors/', { count: sectors.length, next: null, results: sectors }],
  ['/api/admin/sectors/choices/', sectors],
  ['/api/admin/users/', { count: users.length, next: null, results: users }],
  ['/api/admin/ai-providers/', { providers: [{ id: 'openai' }] }],
  ['/api/admin/sectors/1/ai-credentials/openai/', { configured: false, version: 0 }],
]);

await mkdir(out, { recursive: true });
const browser = await chromium.launch({ executablePath: browserPath, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!responses.has(path)) throw new Error(`API não simulada: ${path}`);
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify(responses.get(path)) });
  });
  const response = await page.goto(`${origin}/admin`, { waitUntil: 'networkidle' });
  assert.equal(response.status(), 200);
  await page.getByRole('heading', { name: 'Administração', exact: true }).waitFor();
  await page.getByText('Equipe Exemplo').first().waitFor();
  await page.screenshot({ path: resolve(out, 'admin-setores.png'), fullPage: true });

  await page.getByRole('button', { name: 'Configurar IA' }).first().click();
  await page.getByRole('heading', { name: 'Credencial de IA do setor' }).waitFor();
  await page.getByText('Não configurada').waitFor();
  await page.screenshot({ path: resolve(out, 'admin-ia.png'), fullPage: true });

  await page.getByRole('tab', { name: 'Usuários' }).click();
  await page.getByText('bruno.teste').waitFor();
  await page.screenshot({ path: resolve(out, 'admin-usuarios.png'), fullPage: true });
  assert.deepEqual(errors, []);
  console.log('Capturas sintéticas geradas em frontend/docs/screenshots.');
} finally {
  await browser.close();
}
