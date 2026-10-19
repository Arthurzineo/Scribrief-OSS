/** Backend contract adaptation. UI models remain independent of API field names. */
export const STATUS = {
  uploaded: { step: 0, tone: 'neutro', label: 'Enviado' },
  extracting_audio: { step: 1, tone: 'processando', label: 'Extraindo áudio' },
  transcribing: { step: 2, tone: 'processando', label: 'Transcrevendo' },
  transcribed: { step: 3, tone: 'sucesso', label: 'Transcrição pronta' },
  failed: { step: null, tone: 'erro', label: 'Falhou' },
};

export function statusInfo(meeting) {
  const base = STATUS[meeting.status] || STATUS.uploaded;
  if (meeting.status === 'transcribed' && meeting.minutesStatus === 'ready') {
    return { ...base, label: 'Ata pronta' };
  }
  if (meeting.minutesStatus === 'generating') {
    return { ...base, tone: 'processando', label: 'Gerando ata' };
  }
  if (meeting.minutesStatus === 'failed') {
    return { ...base, tone: 'erro', label: 'Ata com erro' };
  }
  return base;
}

export const isProcessing = (meeting) =>
  ['uploaded', 'extracting_audio', 'transcribing'].includes(meeting.status);

export function states(row) {
  const raw = row.status;
  const minutesFailed = raw === 'erro'
    && ['minutes_failed', 'minutes_queue_unavailable'].includes(row.error_code);
  return {
    status: ({
      enviado: 'uploaded',
      extraindo_audio: 'extracting_audio',
      transcrevendo: 'transcribing',
      transcrito: 'transcribed',
      gerando_ata: 'transcribed',
      ata_pronta: 'transcribed',
      erro: minutesFailed ? 'transcribed' : 'failed',
    })[raw] || 'failed',
    minutesStatus: raw === 'gerando_ata' ? (row.minutes_stuck ? 'failed' : 'generating')
      : raw === 'ata_pronta' ? 'ready'
        : minutesFailed ? 'failed' : 'none',
  };
}

export function toMeetingSummary(row) {
  return {
    id: String(row.id),
    title: row.title || '',
    date: row.meeting_date || row.created_at || null,
    durationSeconds: Number(row.duration_seconds || 0),
    speakerCount: Number(row.speaker_count || 0),
    canEdit: Boolean(row.can_edit),
    ownerName: row.owner_name || '',
    ownerId: Number(row.owner_id || 0),
    sharedWithSector: Boolean(row.shared_with_sector),
    accessVersion: Number(row.access_version || 0),
    ...states(row),
    failedStep: row.status === 'erro' ? 2 : null,
  };
}

export function toMinutes(data) {
  return {
    summary: data.resumo_executivo || '',
    topics: Array.isArray(data.topicos) ? data.topicos.map((item) => ({
      title: item.titulo || '', comment: item.comentario || '',
    })) : [],
    decisions: Array.isArray(data.decisoes) ? data.decisoes : [],
    participants: Array.isArray(data.participantes) ? data.participantes : [],
    reviewer: data.revisor || null,
    reviewedAt: data.revisado_em || null,
    tasks: (data.tarefas || []).map((item) => ({
      task: item.descricao || '',
      owner: item.responsavel || '',
      due: item.prazo || '',
    })),
  };
}

export function toMeeting(row, transcript, speakerData, minutesData, audioUrl) {
  const names = transcript?.falantes || {};
  const segments = (transcript?.segmentos || []).map((item) => ({
    id: String(item.id),
    speakerId: String(item.falante_id),
    start: Number(item.inicio),
    end: Number(item.fim),
    text: item.texto || '',
  }));
  const speakerRows = speakerData?.falantes || Object.keys(names).map((code) => ({
    falante_id: code, nome: names[code],
  }));
  const speakers = speakerRows.map((item, index) => {
    const id = String(item.falante_id);
    const label = `Pessoa ${index + 1}`;
    return {
      id,
      index: index + 1,
      label,
      name: item.nome === label ? '' : item.nome || names[id] || '',
      totalSeconds: segments
        .filter((segment) => segment.speakerId === id)
        .reduce((sum, segment) => sum + segment.end - segment.start, 0),
    };
  });
  return {
    ...toMeetingSummary(row),
    durationSeconds: Math.max(0, ...segments.map((segment) => segment.end)),
    speakerCount: speakers.length,
    error: row.error_message || null,
    minutesError: ['minutes_failed', 'minutes_queue_unavailable'].includes(row.error_code)
      ? row.error_message : null,
    audioUrl,
    speakers,
    segments,
    transcriptionVersion: transcript?.version ?? 0,
    minutesVersion: minutesData?.version ?? row.minutes_version ?? 0,
    minutesStale: Boolean(row.minutes_stale),
    minutes: minutesData ? toMinutes(minutesData) : null,
  };
}
