import { API_URL, request, upload, ApiError, postKeepalive } from './client.js';
import { toMeeting, toMeetingSummary, toMinutes } from './mappers.js';

const path = (id) => `/meetings/${encodeURIComponent(id)}/`;

export async function listMeetings({ q, status, signal } = {}) {
  const items = [];
  let next = '/meetings/';
  // Respect server pagination while bounding accidental infinite loops.
  for (let page = 0; next && page < 50; page += 1) {
    const response = await request('GET', next, {
      query: page === 0 ? { search: q, status } : undefined, signal,
    });
    if (Array.isArray(response)) return response.map(toMeetingSummary);
    items.push(...(response.results || []));
    if (!response.next) break;
    const nextUrl = new URL(response.next, window.location.origin);
    if (nextUrl.origin !== window.location.origin || !nextUrl.pathname.startsWith(API_URL)) {
      throw new ApiError(0, 'Paginação inválida recebida do servidor.');
    }
    next = nextUrl.pathname.slice(API_URL.length) + nextUrl.search;
  }
  return items.map(toMeetingSummary);
}

export function stageMeeting({ title, date, file }, onProgress) {
  let aborted = false;
  let transfer = null;
  let id = null;
  const promise = (async () => {
    const created = await request('POST', '/meetings/', {
      json: { title, meeting_date: date },
      headers: { 'X-Staged-Upload': '1' },
    });
    id = String(created.id);
    try {
      if (aborted) throw new ApiError(-1, 'Envio cancelado.');
      const form = new FormData();
      form.append('file', file);
      form.append('consent_confirmed', 'false');
      transfer = upload(`${path(id)}upload/`, form, onProgress);
      await transfer.promise;
      if (aborted) throw new ApiError(-1, 'Envio cancelado.');
      return { id };
    } catch (error) {
      // Fast deletion of the unconfirmed draft; periodic server cleanup covers a lost request.
      try { await discardStagedMeeting(id); } catch { /* server may be unavailable */ }
      throw error;
    }
  })();
  return { promise, abort: () => {
    aborted = true;
    transfer?.abort();
    if (id) discardStagedMeetingKeepalive(id);
  } };
}

export const confirmStagedMeeting = (id) => request('POST', `${path(id)}confirm-upload/`, {
  json: { consent_confirmed: true },
});
export const discardStagedMeeting = (id) => request('POST', `${path(id)}discard-upload/`);
export const discardStagedMeetingKeepalive = (id) => postKeepalive(`${path(id)}discard-upload/`);

export async function getMeeting(id, { signal } = {}) {
  const row = await request('GET', path(id), { signal });
  const hasTranscript = ['transcrito', 'ata_pronta', 'gerando_ata'].includes(row.status)
    || (row.status === 'erro'
      && ['minutes_failed', 'minutes_queue_unavailable'].includes(row.error_code));
  const [transcript, speakers, minutes] = await Promise.all([
    hasTranscript ? request('GET', `${path(id)}transcription/`, { signal }) : null,
    hasTranscript ? request('GET', `${path(id)}speakers/`, { signal }) : null,
    row.status === 'ata_pronta' ? request('GET', `${path(id)}minutes/`, { signal }) : null,
  ]);
  const audioUrl = row.audio_available ? `${API_URL}${path(id)}audio/` : null;
  return toMeeting(row, transcript, speakers, minutes, audioUrl);
}

export const retryMeeting = (id) => request('POST', `${path(id)}retry/`);
export const getMeetingStatus = (id, { signal } = {}) =>
  request('GET', `${path(id)}status/`, { signal });
export const getTranscriptionProgress = (id) => request('GET', `${path(id)}progress/`);
export const deleteMeeting = (id) => request('DELETE', path(id));
export const renameMeeting = (id, title) => request('PATCH', path(id), { json: { title } });
export const setMeetingSharing = (id, enabled, accessVersion) =>
  request('PATCH', `${path(id)}sharing/`, { json: { shared_with_sector: enabled, access_version: accessVersion } });
export const transferMeeting = (id, targetUserId, accessVersion) =>
  request('POST', `${path(id)}transfer/`, { json: { target_user_id: targetUserId, access_version: accessVersion } });
export const listSectorMembers = async () => (await request('GET', '/sector-members/')).members || [];

export const renameSpeaker = (id, code, name, version) =>
  request('PATCH', `${path(id)}speakers/${encodeURIComponent(code)}/`, {
    json: { nome: name, version },
  });

export const mergeSpeakers = (id, source, target, version) =>
  request('POST', `${path(id)}speakers/merge/`, {
    json: { source, target, version },
  });

export const mergeSpeakersBatch = (id, sources, target, version) =>
  request('POST', `${path(id)}speakers/merge-batch/`, {
    json: { sources, target, version },
  });

export const suggestSpeakerMerges = (id, version) =>
  request('POST', `${path(id)}speaker-suggestions/`, { json: { version } });

export const getSpeakerMergeSuggestions = (id) =>
  request('GET', `${path(id)}speaker-suggestions/`);

export const dismissSpeakerMerges = (id, version, codes) =>
  request('POST', `${path(id)}speaker-suggestions/dismiss/`, {
    json: { version, ...(codes ? { codes } : {}) },
  });

export const getMindMap = (id) => request('GET', `${path(id)}mind-map/`);
export const generateMindMap = (id) => request('POST', `${path(id)}mind-map/`, { json: {} });

export const updateSegment = (id, segment, text, version) =>
  request('PATCH', `${path(id)}transcription/`, {
    json: {
      version,
      segmentos: [{
        id: Number(segment.id), texto: text, inicio: segment.start, fim: segment.end,
      }],
    },
  });

export const suggestCorrections = (id, version) =>
  request('POST', `${path(id)}correction-suggestions/`, { json: { version } });

export const getCorrectionSuggestions = (id, jobId) =>
  request('GET', `${path(id)}correction-suggestions/`, { query: { job_id: jobId } });

export const generateMinutes = (id) => request('POST', `${path(id)}minutes/`);

export const reviewMinutes = (id, version) =>
  request('POST', `${path(id)}minutes/review/`, { json: { version } });

export async function saveMinutes(id, minutes, version) {
  const response = await request('PATCH', `${path(id)}minutes/`, {
    json: {
      version,
      resumo_executivo: minutes.summary,
      topicos: (minutes.topics || []).map((topic) => ({
        titulo: topic.title, comentario: topic.comment,
      })),
      decisoes: minutes.decisions,
      participantes: minutes.participants,
      tarefas: minutes.tasks.map((task) => ({
        descricao: task.task,
        responsavel: task.owner,
        prazo: task.due || null,
      })),
    },
  });
  return { ...toMinutes(response), version: response.version };
}
