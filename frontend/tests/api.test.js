import assert from 'node:assert/strict';
import test from 'node:test';
import { request } from '../src/api/client.js';
import { isProcessing, states, toMeeting, toMeetingSummary } from '../src/api/mappers.js';
import { minutesToTxt } from '../src/shared/lib/export.js';

test('maps backend processing/minutes states without treating minutes failure as transcription failure', () => {
  assert.deepEqual(states({ status: 'extraindo_audio' }), {
    status: 'extracting_audio', minutesStatus: 'none',
  });
  assert.deepEqual(states({ status: 'gerando_ata' }), {
    status: 'transcribed', minutesStatus: 'generating',
  });
  assert.deepEqual(states({ status: 'gerando_ata', minutes_stuck: true }), {
    status: 'transcribed', minutesStatus: 'failed',
  });
  assert.deepEqual(states({ status: 'erro', error_code: 'minutes_failed' }), {
    status: 'transcribed', minutesStatus: 'failed',
  });
  assert.equal(isProcessing(toMeetingSummary({ id: '1', status: 'transcrevendo' })), true);
});

test('maps diarized transcript and minutes to the preserved UI model', () => {
  const result = toMeeting(
    { id: 'id', title: 'Reunião', status: 'ata_pronta', created_at: '2026-10-08',
      transcription_version: 2, minutes_version: 3, minutes_stale: true },
    { version: 2, falantes: { A: 'Ana' }, segmentos: [
      { id: 7, falante_id: 'A', inicio: 1, fim: 3, texto: '<img onerror=alert(1)>' },
    ] },
    { falantes: [{ falante_id: 'A', nome: 'Ana' }] },
    { version: 3, resumo_executivo: 'Resumo',
      topicos: [{ titulo: 'Planejamento', comentario: 'Equipe discutiu o prazo.' }], decisoes: ['Sim'],
      tarefas: [{ descricao: 'Fazer', responsavel: 'Ana', prazo: null }],
      participantes: ['Ana', 'Bruno'], revisor: 'Ana', revisado_em: '2026-10-09T12:00:00Z' },
    '/api/v1/meetings/id/audio/',
  );
  assert.equal(result.speakers[0].totalSeconds, 2);
  assert.equal(result.segments[0].text, '<img onerror=alert(1)>');
  assert.equal(result.minutes.tasks[0].task, 'Fazer');
  assert.deepEqual(result.minutes.participants, ['Ana', 'Bruno']);
  assert.equal(result.minutes.reviewer, 'Ana');
  assert.deepEqual(result.minutes.topics, [{ title: 'Planejamento', comment: 'Equipe discutiu o prazo.' }]);
  assert.equal(result.minutesVersion, 3);
  assert.equal(result.minutesStale, true);
  assert.equal(result.audioUrl, '/api/v1/meetings/id/audio/');
});

test('mutation obtains CSRF cookie and sends it without bearer token', async () => {
  const calls = [];
  globalThis.document = { cookie: '' };
  globalThis.window = new EventTarget();
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/csrf/')) {
      document.cookie = 'csrftoken=abc';
      return { ok: true, status: 200 };
    }
    return { ok: true, status: 200, text: async () => '{"ok":true}' };
  };
  assert.deepEqual(await request('POST', '/meetings/', { json: { title: 'A' } }), { ok: true });
  assert.equal(calls[1].options.headers['X-CSRFToken'], 'abc');
  assert.equal(calls[1].options.headers.Authorization, undefined);
  assert.equal(calls[1].options.credentials, 'same-origin');
});

test('certificate multipart upload keeps browser boundary and CSRF', async () => {
  globalThis.document = { cookie: 'csrftoken=xyz' };
  globalThis.window = new EventTarget();
  let sent;
  globalThis.fetch = async (_url, options) => {
    sent = options;
    return { ok: true, status: 200, text: async () => '{"configured":true}' };
  };
  const form = new FormData();
  form.append('current_password', 'synthetic');
  await request('POST', '/api/admin/tls/', { form });
  assert.equal(sent.body, form);
  assert.equal(sent.headers['Content-Type'], undefined);
  assert.equal(sent.headers['X-CSRFToken'], 'xyz');
});

test('exports topic-based minutes', () => {
  const meeting = { title: 'Pautas', date: '2026-10-08', durationSeconds: 60 };
  const common = { summary: 'Resumo', decisions: [], tasks: [] };
  const topical = minutesToTxt(meeting, {
    ...common, topics: [{ title: 'Planejamento', comment: 'Equipe discutiu o prazo.' }],
  }, ['Ana']);
  assert.match(topical, /TÓPICOS DISCUTIDOS/);
  assert.match(topical, /Planejamento/);
  assert.match(topical, /Equipe discutiu o prazo/);
  assert.match(topical, /Ata não revisada/);
  const reviewed = minutesToTxt(meeting, {
    ...common, topics: [], reviewer: 'Ana', reviewedAt: '2026-10-09T12:00:00Z',
  }, ['Ana', 'Bruno']);
  assert.match(reviewed, /Ata revisada por Ana/);
  assert.match(reviewed, /Participantes: Ana, Bruno/);
});

test('API errors extract structured message and notify on expired session', async () => {
  globalThis.document = { cookie: 'csrftoken=abc' };
  globalThis.window = new EventTarget();
  let unauthorized = 0;
  window.addEventListener('ata:unauthorized', () => { unauthorized += 1; });
  globalThis.fetch = async () => ({
    ok: false, status: 401,
    text: async () => '{"error":{"code":"not_authenticated","message":"Sessão expirada."}}',
  });
  await assert.rejects(
    () => request('GET', '/meetings/'),
    (error) => error.status === 401 && error.message === 'Sessão expirada.',
  );
  assert.equal(unauthorized, 1);
});
