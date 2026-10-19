import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const values = Object.fromEntries((await readFile(resolve(root, 'pentest/.env'), 'utf8'))
  .split(/\r?\n/).filter((line) => line && !line.startsWith('#'))
  .map((line) => line.split(/=(.*)/s).slice(0, 2)));
const base = 'https://127.0.0.2:18674';
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const map = {
  centro: 'Aplicativo institucional UX Educa',
  ramos: [
    { titulo: 'Aplicativos e bases', pontos: ['Produção', 'Treinamento', 'Qualidade'] },
    { titulo: 'Área acadêmica', pontos: ['Portal', 'Matrícula', 'Permissões'] },
    { titulo: 'Funções nativas', pontos: ['Notificações', 'Pagamentos', 'Carteirinha'] },
    { titulo: 'Experiência de uso', pontos: ['Contexto', 'Validação', 'Demonstração'] },
    { titulo: 'Comunicações', pontos: ['E-mail', 'Prazos', 'Canais', 'Evitar excesso'] },
    { titulo: 'Adoção na graduação', pontos: ['Público', 'Valor', 'Regras'] },
  ],
};

try {
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, ignoreHTTPSErrors: true });
    await page.goto(`${base}/login/`, { waitUntil: 'networkidle' });
    await page.getByLabel('Usuário').fill('pt_owner');
    await page.getByLabel('Senha').fill(values.PENTEST_OWNER_PASSWORD);
    await page.getByRole('button', { name: 'Entrar' }).click();
    await page.getByRole('heading', { name: 'Reuniões', exact: true }).waitFor();
    const meetings = await page.evaluate(async () =>
      fetch('/api/v1/meetings/', { credentials: 'same-origin' }).then((response) => response.json()));
    const id = meetings.results.find((row) => row.title === 'PENTEST — privada')?.id;
    assert.ok(id, 'clone fixture missing');
    await page.route(`**/api/v1/meetings/${id}/mind-map/`, (route) => route.fulfill({
      status: 200, json: { status: 'ready', version: 1, mapa: map },
    }));
    await page.goto(`${base}/reunioes/${id}/mapa/`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: map.centro }).waitFor();
    await page.locator('.mind-map__connectors [data-branch-connector]').first().waitFor({ state: 'attached' });
    await page.locator('.mind-map__connectors [data-card-connector]').first()
      .waitFor({ state: 'attached', timeout: 3000 });
    const geometry = await page.evaluate(() => {
      const canvas = document.querySelector('.mind-map__canvas');
      const canvasBox = canvas.getBoundingClientRect();
      const titles = [...document.querySelectorAll('.mind-map__branch-title')];
      const links = [...document.querySelectorAll('[data-branch-connector]')];
      return {
        canvasWidth: canvasBox.width,
        viewportWidth: document.querySelector('.mind-map__viewport').clientWidth,
        pageOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        count: links.length,
        rows: [...new Set(titles.map((title) => Math.round(title.getBoundingClientRect().top)))].length,
        links: links.map((line, index) => {
          const title = titles[index].getBoundingClientRect();
          return {
            x1: Number(line.getAttribute('x1')), x2: Number(line.getAttribute('x2')),
            y1: Number(line.getAttribute('y1')), y2: Number(line.getAttribute('y2')),
            titleLeft: title.left - canvasBox.left, titleRight: title.right - canvasBox.left,
            titleMiddle: title.top + title.height / 2 - canvasBox.top,
          };
        }),
        children: [...document.querySelectorAll('.mind-map__branch')].map((branch, index) => {
          const title = branch.querySelector('.mind-map__branch-title').getBoundingClientRect();
          const spine = document.querySelector(`[data-branch-child-spine="${index}"]`);
          const cards = [...branch.querySelectorAll('.mind-map__card')];
          return {
            titleBottom: title.bottom - canvasBox.top,
            spine: { x1: Number(spine.getAttribute('x1')), x2: Number(spine.getAttribute('x2')),
              y1: Number(spine.getAttribute('y1')), y2: Number(spine.getAttribute('y2')) },
            cards: cards.map((card, pointIndex) => {
              const rect = card.getBoundingClientRect();
              const line = document.querySelector(`[data-card-connector="${index}-${pointIndex}"]`);
              return {
                left: rect.left - canvasBox.left, right: rect.right - canvasBox.left,
                middle: rect.top + rect.height / 2 - canvasBox.top,
                x1: Number(line.getAttribute('x1')), x2: Number(line.getAttribute('x2')),
                y1: Number(line.getAttribute('y1')), y2: Number(line.getAttribute('y2')),
              };
            }),
          };
        }),
      };
    });
    assert.equal(geometry.count, 6);
    assert.equal(geometry.rows, 3);
    assert.ok(geometry.canvasWidth >= 1120);
    assert.ok(geometry.pageOverflow <= 1);
    if (width === 390) assert.ok(geometry.canvasWidth > geometry.viewportWidth);
    for (const [index, line] of geometry.links.entries()) {
      assert.ok(Math.abs(line.y1 - line.titleMiddle) < 1, JSON.stringify({ index, line }));
      assert.equal(line.y1, line.y2);
      if (index % 2 === 0) {
        assert.ok(line.x1 < line.titleLeft && Math.abs(line.x2 - line.titleLeft) < 1);
      } else {
        assert.ok(Math.abs(line.x1 - line.titleRight) < 1 && line.x2 > line.titleRight);
      }
    }
    assert.equal(geometry.children.reduce((sum, branch) => sum + branch.cards.length, 0), 19);
    for (const [branchIndex, branch] of geometry.children.entries()) {
      assert.equal(branch.spine.x1, branch.spine.x2);
      assert.ok(Math.abs(branch.spine.y1 - branch.titleBottom) < 1);
      assert.ok(Math.abs(branch.spine.y2 - branch.cards.at(-1).middle) < 1);
      for (const card of branch.cards) {
        assert.ok(Math.abs(card.y1 - card.middle) < 1 && card.y1 === card.y2);
        if (branchIndex % 2 === 0) {
          assert.ok(card.x1 === branch.spine.x1 && card.x1 < card.left
            && Math.abs(card.x2 - card.left) < 1);
        } else {
          assert.ok(Math.abs(card.x1 - card.right) < 1 && card.x2 === branch.spine.x1
            && card.x2 > card.right);
        }
      }
    }
    for (const [format, signature] of [['PNG', '89504e470d0a1a0a'], ['PDF', '255044462d']]) {
      const download = page.waitForEvent('download');
      await page.getByRole('button', { name: `Baixar ${format}` }).click();
      const bytes = await readFile(await (await download).path());
      assert.equal(bytes.subarray(0, signature.length / 2).toString('hex'), signature);
      if (width === 1440 && format === 'PNG') {
        await writeFile(resolve(root, 'frontend/.artifacts/map-connectors-after.png'), bytes);
      }
    }
    await page.close();
  }
  console.log('PASS independent mind-map connectors in three rows and full exports');
} finally {
  await browser.close();
}
