import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, ConfirmModal, Icon, InlineNotice, StatusTag, StepList, ViewTabs } from '../../shared/components/index.js';
import { deleteMeeting, getMeeting, getMeetingStatus, getTranscriptionProgress, listSectorMembers, renameMeeting, retryMeeting, setMeetingSharing, transferMeeting } from '../../api/meetings.js';
import { isProcessing, statusInfo } from '../../api/mappers.js';
import { useMeetings } from '../../shared/context/MeetingsContext.jsx';
import { dateBR, duration } from '../../shared/lib/format.js';
import TranscriptView from './TranscriptView.jsx';
import MinutesView from './MinutesView.jsx';
import MindMapView from './MindMapView.jsx';

const POLL_MS = 3000;

export default function MeetingPage({ tab }) {
  const { id } = useParams();
  const nav = usePageNavigate();
  const { refresh: refreshList } = useMeetings();
  const [m, setM] = useState(null);
  const [error, setError] = useState(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [titleBusy, setTitleBusy] = useState(false);
  const [titleError, setTitleError] = useState('');
  const [accessError, setAccessError] = useState('');
  const [accessBusy, setAccessBusy] = useState(false);
  const [members, setMembers] = useState([]);
  const [transferTarget, setTransferTarget] = useState('');
  const [transferConfirm, setTransferConfirm] = useState(false);
  const polling = useRef(false);

  const load = useCallback(async ({ signal } = {}) => {
    try {
      const r = await getMeeting(id, { signal });
      if (signal?.aborted) return null;
      setM(r); setError(null); return r;
    } catch (e) {
      if (!signal?.aborted) setError(e);
      return null;
    }
  }, [id]);

  useEffect(() => { setM(null); load(); }, [load]);
  useEffect(() => {
    if (!m?.canEdit) return;
    listSectorMembers().then(setMembers).catch(() => setMembers([]));
  }, [m?.id, m?.canEdit]);

  // Acompanha o processamento e a geração da ata.
  useEffect(() => {
    if (!m || (!isProcessing(m) && m.minutesStatus !== 'generating')) return undefined;
    const controller = new AbortController();
    const timer = setInterval(async () => {
      if (polling.current) return;
      polling.current = true;
      try {
        let result;
        if (m.minutesStatus === 'generating') {
          const status = await getMeetingStatus(id, { signal: controller.signal });
          if (controller.signal.aborted ||
              (status.status === 'gerando_ata' && !status.minutes_stuck)) return;
          result = await load({ signal: controller.signal });
        } else {
          result = await load({ signal: controller.signal });
        }
        if (result && !isProcessing(result) && result.minutesStatus !== 'generating') refreshList();
      } catch (e) {
        if (!controller.signal.aborted) {
          setError(e);
          if (e.status === 404) setM(null);
        }
      } finally { polling.current = false; }
    }, POLL_MS);
    return () => { clearInterval(timer); controller.abort(); };
  }, [m, id, load, refreshList]);

  if (error && !m) {
    return (
      <div className="page page--narrow">
        <InlineNotice tone="erro" action={<Button icon="retry" onClick={load}>Tentar novamente</Button>}>
          {error.status === 404 ? 'Reunião não encontrada.' : 'Não foi possível carregar a reunião.'}
        </InlineNotice>
      </div>
    );
  }
  if (!m) return <div className="page"><p className="muted">Carregando…</p></div>;

  async function confirmDelete() {
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteMeeting(m.id);
      await refreshList();
      nav('/', { replace: true });
    } catch (e) {
      setDeleteError(`Não foi possível excluir a reunião. ${e.message}`);
    } finally {
      setDeleting(false);
      setDeleteOpen(false);
    }
  }

  async function saveTitle(event) {
    event.preventDefault();
    const title = titleDraft.trim();
    if (!title) { setTitleError('Informe um nome para a reunião.'); return; }
    if (title === m.title) { setEditingTitle(false); return; }
    setTitleBusy(true);
    setTitleError('');
    try {
      await renameMeeting(m.id, title);
      await load();
      await refreshList();
      setEditingTitle(false);
    } catch (e) { setTitleError(`Não foi possível renomear a reunião. ${e.message}`); }
    finally { setTitleBusy(false); }
  }

  async function changeSharing() {
    setAccessBusy(true); setAccessError('');
    try {
      await setMeetingSharing(m.id, !m.sharedWithSector, m.accessVersion);
      await load(); await refreshList();
    } catch (e) { setAccessError(`Não foi possível alterar a partilha. ${e.message}`); }
    finally { setAccessBusy(false); }
  }

  async function confirmTransfer() {
    setAccessBusy(true); setAccessError('');
    try {
      await transferMeeting(m.id, Number(transferTarget), m.accessVersion);
      await refreshList();
      nav('/', { replace: true });
    } catch (e) { setAccessError(`Não foi possível transferir. ${e.message}`); }
    finally { setAccessBusy(false); setTransferConfirm(false); }
  }

  const accessPanel = m.canEdit ? <section className="meeting-access" aria-label="Acesso à reunião">
    <div><strong>Partilha com o setor</strong><p>{m.sharedWithSector ? 'Colegas do setor podem ver todos os artefatos em modo leitura.' : 'Somente você pode abrir esta reunião.'}</p></div>
    <Button disabled={accessBusy} onClick={changeSharing}>{m.sharedWithSector ? 'Revogar acesso do setor' : 'Permitir leitura ao setor'}</Button>
    {['transcribed'].includes(m.status) && m.minutesStatus !== 'generating' ? <div className="meeting-access__transfer">
      <label htmlFor="transfer-target">Transferir toda a reunião para</label>
      <select id="transfer-target" className="select" value={transferTarget} onChange={(e) => setTransferTarget(e.target.value)}>
        <option value="">Selecione um membro</option>
        {members.filter((member) => member.id !== m.ownerId).map((member) => <option key={member.id} value={member.id}>{member.name}</option>)}
      </select>
      <Button disabled={!transferTarget || accessBusy} onClick={() => setTransferConfirm(true)}>Transferir</Button>
    </div> : null}
    {accessError ? <InlineNotice tone="erro">{accessError}</InlineNotice> : null}
    <ConfirmModal open={transferConfirm} title="Transferir reunião inteira?"
      message="O novo dono poderá editar e excluir áudio, transcrição, ata e mapa. Você perderá essa permissão imediatamente."
      confirmLabel="Confirmar transferência" busy={accessBusy}
      onCancel={() => setTransferConfirm(false)} onConfirm={confirmTransfer} />
  </section> : <InlineNotice tone="neutro">Leitura compartilhada por {m.ownerName}. Somente o dono pode editar ou excluir.</InlineNotice>;

  const deleteButton = m.canEdit ? (
    <Button variant="destructive" disabled={deleting || ['extracting_audio', 'transcribing'].includes(m.status) || m.minutesStatus === 'generating'} onClick={() => setDeleteOpen(true)}>Excluir reunião</Button>
  ) : null;
  const deleteDialog = (
    <ConfirmModal open={deleteOpen} destructive busy={deleting} title="Excluir reunião?"
      message="A reunião, a transcrição, a ata e o áudio ficarão ocultos agora. Um administrador poderá restaurá-los por 3 dias; depois desse prazo, dados e arquivos serão excluídos definitivamente."
      confirmLabel={deleting ? 'Excluindo…' : 'Excluir reunião'}
      onCancel={() => { if (!deleting) setDeleteOpen(false); }} onConfirm={confirmDelete} />
  );

  const s = statusInfo(m);
  const header = (
    <div>
      {editingTitle ? (
        <form className="meeting-title-edit" onSubmit={saveTitle}>
          <label htmlFor="meeting-title-input" className="sr-only">Nome da reunião</label>
          <input id="meeting-title-input" className="at-input" autoFocus maxLength={200} value={titleDraft}
            onChange={(event) => setTitleDraft(event.target.value)}
            onKeyDown={(event) => { if (event.key === 'Escape') { setEditingTitle(false); setTitleError(''); } }} />
          <Button variant="primary" type="submit" disabled={titleBusy}>Salvar</Button>
          <Button disabled={titleBusy} onClick={() => { setEditingTitle(false); setTitleError(''); }}>Cancelar</Button>
        </form>
      ) : (
        <div className="meeting-title">
          <h1 className="t-page">{m.title}</h1>
          {m.canEdit ? <button type="button" className="meeting-title__edit" aria-label="Editar nome da reunião"
            onClick={() => { setTitleDraft(m.title); setTitleError(''); setEditingTitle(true); }}>
            <Icon name="edit" size={18} />
          </button> : null}
        </div>
      )}
      {titleError ? <p className="meeting-title__error" role="alert">{titleError}</p> : null}
      <div className="head__meta">
        <span>{dateBR(m.date)}</span>
        {m.durationSeconds ? <span className="mono">{duration(m.durationSeconds)}</span> : null}
        {m.status === 'transcribed'
          ? <span>{m.speakers.length} {m.speakers.length === 1 ? 'falante' : 'falantes'}</span>
          : <StatusTag tone={s.tone}>{s.label}</StatusTag>}
      </div>
    </div>
  );

  if (m.status !== 'transcribed') {
    return (
      <div className="page page--narrow">
        <div className="mt__tools">{header}{deleteButton}</div>
        {accessPanel}
        {deleteError ? <InlineNotice tone="erro">{deleteError}</InlineNotice> : null}
        <Processing m={m} canEdit={m.canEdit} onRetry={async () => { await retryMeeting(m.id); await load(); refreshList(); }} onBack={() => nav('/')} />
        {deleteDialog}
      </div>
    );
  }

  return (
    <div className="page">
      <div className="mt__tools">{header}{deleteButton}</div>
      {accessPanel}
      {deleteError ? <InlineNotice tone="erro">{deleteError}</InlineNotice> : null}
      <ViewTabs items={['Transcrição', 'Ata', 'Mapa mental']} active={tab} onChange={(t) => nav(t === 'Ata' ? `/reunioes/${m.id}/ata` : t === 'Mapa mental' ? `/reunioes/${m.id}/mapa` : `/reunioes/${m.id}`)} />
      {tab === 'Ata'
        ? <MinutesView m={m} setM={setM} reload={load} refreshList={refreshList} />
        : tab === 'Mapa mental'
          ? <MindMapView m={m} />
          : <TranscriptView m={m} setM={setM} reload={load} refreshList={refreshList} onGenerated={() => nav(`/reunioes/${m.id}/ata`)} />}
      {deleteDialog}
    </div>
  );
}

const LABELS = ['Arquivo recebido', 'Extraindo áudio', 'Transcrevendo', 'Transcrição pronta'];

function Processing({ m, canEdit, onRetry, onBack }) {
  const [busy, setBusy] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [progress, setProgress] = useState(null);
  const [progressError, setProgressError] = useState(false);
  const failed = m.status === 'failed';
  useEffect(() => {
    if (!showProgress) return undefined;
    let mounted = true;
    async function refresh() {
      try {
        const value = await getTranscriptionProgress(m.id);
        if (mounted) { setProgress(value); setProgressError(false); }
      } catch {
        if (mounted) setProgressError(true);
      }
    }
    refresh();
    const timer = isProcessing(m) ? setInterval(refresh, POLL_MS) : null;
    return () => { mounted = false; if (timer) clearInterval(timer); };
  }, [showProgress, m.id, m.status]);
  // Em falha, `failedStep` (1 = extração, 2 = transcrição) diz onde parou; sem ele, marca a extração.
  const current = failed ? (m.failedStep ?? 1) : (statusInfo(m).step || 0);
  const steps = LABELS.map((label, i) => {
    let state = 'pendente';
    if (i === 0 || i < current) state = 'concluida';
    if (i === current && i > 0) state = failed ? 'erro' : 'andamento';
    if (!failed && current === 0 && i === 1) state = 'andamento';
    if (i === 3) state = 'pendente';
    return { label, state, detail: state === 'erro' ? (m.error || 'Não foi possível processar o arquivo.') : undefined };
  });

  return (
    <div className="proc">
      <StepList steps={steps} />
      <Button onClick={() => setShowProgress((visible) => !visible)} aria-expanded={showProgress}>
        {showProgress ? 'Ocultar progresso' : 'Ver progresso'}
      </Button>
      {showProgress ? (
        <section className="proc__progress" aria-label="Progresso da transcrição">
          {progressError ? <InlineNotice tone="erro">Não foi possível atualizar o progresso. O processamento continua; tente novamente.</InlineNotice> : null}
          {!progress && !progressError ? <p className="proc__note">Consultando progresso…</p> : null}
          {progress ? (
            <>
              <p className="proc__note" role="status">
                {progress.stage === 'finalizando' ? 'Todos os blocos foram transcritos. Finalizando…'
                  : progress.stage === 'extraindo_audio' ? 'Extraindo áudio…'
                    : progress.stage === 'aguardando' ? 'Aguardando início…'
                      : progress.stage === 'concluido' ? 'Transcrição concluída.'
                        : progress.stage === 'erro' ? 'Processamento interrompido.'
                          : 'Transcrevendo áudio…'}
              </p>
              {progress.total_chunks != null ? (
                <>
                  <progress className="proc__bar" value={progress.percent ?? 0} max="100" aria-label="Blocos transcritos" />
                  <p className="proc__note">{progress.completed_chunks} de {progress.total_chunks} blocos concluídos · {progress.percent ?? 0}%</p>
                </>
              ) : (
                <p className="proc__note">A contagem detalhada não está disponível para este processamento.{failed ? '' : ' Ele continua normalmente.'}</p>
              )}
            </>
          ) : null}
        </section>
      ) : null}
      {failed ? (
        <div className="at-hrow">
          {canEdit ? <Button variant="primary" icon="retry" disabled={busy} onClick={async () => { setBusy(true); try { await onRetry(); } finally { setBusy(false); } }}>Tentar novamente</Button> : null}
          <Button onClick={onBack}>Voltar para a lista</Button>
        </div>
      ) : (
        <p className="proc__note">Você pode fechar esta página. A reunião aparece na lista quando estiver pronta.</p>
      )}
    </div>
  );
}
