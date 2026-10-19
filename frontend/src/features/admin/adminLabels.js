// Traduz códigos de API somente na apresentação; os identificadores persistidos não mudam.
const jobs = {
  transcription: 'Transcrição', minutes: 'Ata', mind_map: 'Mapa mental',
  correction: 'Correção sugerida', speaker_analysis: 'Análise de falantes',
  queued: 'Na fila', running: 'Em execução', completed: 'Concluído',
  failed: 'Falhou', cancelled: 'Cancelado',
  transcribing: 'Transcrevendo', processing: 'Processando', generating: 'Gerando',
  uploading: 'Enviando', preparing: 'Preparando', stitching: 'Unindo blocos',
};

const actions = {
  login: 'Entrou no sistema', logout: 'Saiu do sistema', meeting_created: 'Criou reunião',
  meeting_viewed: 'Abriu reunião', meeting_deleted: 'Solicitou exclusão da reunião',
  meeting_restored: 'Restaurou reunião', minutes_viewed: 'Abriu ata',
  minutes_download: 'Baixou ata', original_download: 'Baixou arquivo original',
  audio_play: 'Reproduziu áudio', transcription_viewed: 'Abriu transcrição',
  transcription_download: 'Baixou transcrição', mind_map_viewed: 'Abriu mapa mental',
  transcription_correction_requested: 'Solicitou sugestões de correção',
  speaker_reconciliation_requested: 'Solicitou análise de falantes',
  speaker_reconciliation_dismissed: 'Ignorou sugestão de falantes',
  password_changed: 'Alterou senha', password_change_failed: 'Falha ao alterar senha',
  audit_export: 'Exportou auditoria', health_retention_purge: 'Limpou amostras antigas de saúde',
  job_queued: 'Tarefa entrou na fila', job_started: 'Tarefa iniciada',
  job_completed: 'Tarefa concluída', job_failed: 'Tarefa falhou',
  job_cancelled: 'Tarefa cancelada',
};

const outcomes = {
  success: 'Sucesso', succeeded: 'Sucesso', ok: 'Sucesso',
  failed: 'Falhou', error: 'Erro', queued: 'Na fila', running: 'Em execução',
  completed: 'Concluído', cancelled: 'Cancelado', denied: 'Negado',
};

const targets = {
  user: 'Usuário', sector: 'Setor', meeting: 'Reunião', job: 'Tarefa',
  audit: 'Auditoria', health_sample: 'Amostra de saúde',
  transcription: 'Transcrição', minutes: 'Ata', mind_map: 'Mapa mental',
};

const components = {
  worker: 'Processador de tarefas', backend: 'Servidor da aplicação',
  frontend: 'Interface', cache: 'Cache', database: 'Banco de dados',
  beat: 'Agendador', media: 'Mídia',
};

export const jobLabel = (code) => jobs[code] || 'Etapa não catalogada';
export const actionLabel = (code) => actions[code] || 'Ação não catalogada';
export const outcomeLabel = (code) => outcomes[code] || 'Resultado não catalogado';
export const targetLabel = (code) => targets[code] || 'Alvo não catalogado';
export const componentLabel = (code) => components[code] || 'Componente não catalogado';
export const severityLabel = (code) => ({ info: 'Informação', warning: 'Aviso', error: 'Erro', critical: 'Crítico' })[code] || 'Gravidade não catalogada';
