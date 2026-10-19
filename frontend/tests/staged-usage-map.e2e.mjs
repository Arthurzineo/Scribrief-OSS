import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const values = Object.fromEntries((await readFile(resolve(root, 'pentest/.env'), 'utf8')).split(/\r?\n/)
  .filter((line) => line && !line.startsWith('#')).map((line) => line.split(/=(.*)/s).slice(0, 2)));
const base = 'https://127.0.0.2';
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  headless: true,
});

async function login(page, port, username, password) {
  await page.goto(`${base}:${port}/${port === 18675 ? 'admin/' : ''}login/`, { waitUntil: 'networkidle' });
  await page.getByLabel('Usuário').fill(username);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await page.getByRole('heading', {
    name: port === 18675 ? 'Administração' : 'Reuniões', exact: true,
  }).waitFor();
}

try {
  execFileSync('docker', [
    'exec', 'scribrief-pentest-backend-1', 'ffmpeg', '-hide_banner', '-loglevel', 'error',
    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', '-ac', '1', '-ar', '16000',
    '-codec:a', 'libmp3lame', '-q:a', '6', '-y', '/tmp/staged-browser-test.mp3',
  ]);
  const mp3 = Buffer.from(execFileSync('docker', [
    'exec', 'scribrief-pentest-backend-1', 'python', '-c',
    "import base64;print(base64.b64encode(open('/tmp/staged-browser-test.mp3','rb').read()).decode())",
  ]).toString().trim(), 'base64');

  const owner = await browser.newPage({ viewport: { width: 1280, height: 900 }, ignoreHTTPSErrors: true });
  await login(owner, 18674, 'pt_owner', values.PENTEST_OWNER_PASSWORD);
  await owner.goto(`${base}:18674/reunioes/nova/`, { waitUntil: 'networkidle' });
  await owner.getByLabel('Título').fill('PENTEST — upload temporário da interface');
  const uploadResponse = owner.waitForResponse((response) =>
    response.url().includes('/upload/') && response.request().method() === 'POST');
  await owner.locator('input[type=file]').setInputFiles({
    name: 'synthetic.mp3', mimeType: 'audio/mpeg', buffer: mp3,
  });
  const uploadResult = await uploadResponse;
  assert.equal(uploadResult.status(), 201);
  const staged = await uploadResult.json();
  assert.equal(staged.awaiting_consent, true);
  await owner.getByText(/Nenhuma transcrição foi iniciada/).waitFor();
  const continueButton = owner.getByRole('button', { name: 'Confirmar e iniciar transcrição' });
  assert.equal(await continueButton.isDisabled(), true);
  await owner.locator('.consent-control input').check();
  assert.equal(await continueButton.isEnabled(), true);
  await owner.getByRole('button', { name: 'Voltar para a lista' }).click();
  await owner.getByRole('heading', { name: 'Reuniões', exact: true }).waitFor();
  let removed = false;
  for (let attempt = 0; attempt < 10; attempt += 1) {
    const result = execFileSync('docker', [
      'exec', 'scribrief-pentest-backend-1', 'python', 'manage.py', 'shell', '-c',
      `from apps.meetings.models import Meeting; print(Meeting.objects.filter(pk='${staged.meeting_id}').exists())`,
    ]).toString();
    if (result.includes('False')) { removed = true; break; }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  assert.equal(removed, true, 'staged upload should be deleted after leaving');

  const fixtureId = await owner.evaluate(async () => {
    const result = await fetch('/api/v1/meetings/', { credentials: 'same-origin' }).then((r) => r.json());
    return result.results.find((row) => row.title === 'PENTEST — privada')?.id;
  });
  assert.ok(fixtureId);
  await owner.route(`**/api/v1/meetings/${fixtureId}/mind-map/`, (route) => route.fulfill({
    status: 200, json: {
      status: 'ready', version: 1, mapa: {
        centro: 'Planejamento anual', ramos: [
          { titulo: 'Logística da equipe', pontos: ['Prazos principais', 'Recursos disponíveis'] },
          { titulo: 'Decisões tomadas', pontos: ['Café aprovado', 'Responsáveis definidos'] },
        ],
      },
    },
  }));
  await owner.setViewportSize({ width: 390, height: 800 });
  await owner.goto(`${base}:18674/reunioes/${fixtureId}/mapa/`, { waitUntil: 'networkidle' });
  await owner.getByRole('heading', { name: 'Planejamento anual' }).waitFor();
  const geometry = await owner.evaluate(() => {
    const viewport = document.querySelector('.mind-map__viewport');
    const canvas = document.querySelector('.mind-map__canvas');
    const [left, right] = [...document.querySelectorAll('.mind-map__branch')];
    return {
      docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      viewportWidth: viewport.clientWidth, scrollWidth: viewport.scrollWidth,
      canvasWidth: canvas.getBoundingClientRect().width,
      separated: left.getBoundingClientRect().right <= right.getBoundingClientRect().left,
    };
  });
  assert.ok(geometry.canvasWidth >= 1120 && geometry.scrollWidth > geometry.viewportWidth,
    JSON.stringify(geometry));
  assert.ok(geometry.docOverflow <= 1 && geometry.separated, JSON.stringify(geometry));
  for (const [format, signature] of [['PNG', '89504e470d0a1a0a'], ['PDF', '255044462d']]) {
    const downloadPromise = owner.waitForEvent('download');
    await owner.getByRole('button', { name: `Baixar ${format}` }).click();
    const bytes = await readFile(await (await downloadPromise).path());
    assert.equal(bytes.subarray(0, signature.length / 2).toString('hex'), signature);
    if (format === 'PNG') assert.equal(bytes.readUInt32BE(16), 1120);
  }
  await owner.close();

  const admin = await browser.newPage({ viewport: { width: 1280, height: 900 }, ignoreHTTPSErrors: true });
  await login(admin, 18675, 'pt_admin', values.PENTEST_ADMIN_PASSWORD);
  await admin.route('**/api/admin/usage/meetings/**', (route) => route.fulfill({
    status: 200, json: {
      count: 1, next: null, previous: null, results: [{
        meeting_id: '00000000-0000-4000-8000-000000000001', title: 'Reunião sintética',
        calls: 4, estimated_usd: '0.12000000', unpriced_calls: 1, failed_calls: 0,
        operations: [
          { operation: 'transcription_chunk', calls: 2, estimated_usd: '0.10000000', unpriced_calls: 1, failed_calls: 0 },
          { operation: 'minutes', calls: 1, estimated_usd: '0.01000000', unpriced_calls: 0, failed_calls: 0 },
          { operation: 'mind_map', calls: 1, estimated_usd: '0.01000000', unpriced_calls: 0, failed_calls: 0 },
        ],
      }],
    },
  }));
  await admin.getByRole('tab', { name: 'Custos e uso' }).click();
  await admin.getByRole('heading', { name: 'Custo por reunião' }).waitFor();
  await admin.getByText(/Soma conhecida: US\$ 0\.12000000/).click();
  await admin.getByText('Transcrição — chunks').waitFor();
  await admin.getByRole('cell', { name: 'Mapa mental' }).waitFor();
  await admin.close();
  console.log('PASS clone staged upload, map viewport and meeting costs UI');
} finally {
  await browser.close();
}
