import assert from 'node:assert/strict';
import test from 'node:test';
import { buildMindMap } from '../src/shared/lib/mindMap.js';

test('mind map uses only concise AI nodes, never minutes paragraphs', () => {
  const meeting = {
    title: 'Conselho', date: '2026-10-09',
    minutes: { topics: [{ title: 'Café', comment: 'Parágrafo longo da ata.' }] },
  };
  const data = { centro: 'Encontro', ramos: [
    { titulo: 'Logística', pontos: ['Café aprovado', 'Entrega em outubro'] },
  ] };
  const map = buildMindMap(meeting, data);
  assert.equal(map.center, 'Encontro');
  assert.equal(map.branches[0].label, 'Logística');
  assert.deepEqual(map.branches[0].items.map((item) => item.title), data.ramos[0].pontos);
  assert.equal(JSON.stringify(map).includes('Parágrafo longo'), false);
});

test('mind map stays empty without generated compact data', () => {
  assert.equal(buildMindMap({ title: 'Sem mapa', minutes: { topics: [] } }, null), null);
});
