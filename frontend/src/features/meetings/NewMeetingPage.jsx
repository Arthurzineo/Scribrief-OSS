import { useEffect, useRef, useState } from 'react';
import { usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, Dropzone, InlineNotice, TextField } from '../../shared/components/index.js';
import {
  confirmStagedMeeting, discardStagedMeeting, discardStagedMeetingKeepalive, stageMeeting,
} from '../../api/meetings.js';
import { useMeetings } from '../../shared/context/MeetingsContext.jsx';
import { fileSize, today } from '../../shared/lib/format.js';

// Ajuste aos limites reais do back-end.
export const MAX_BYTES = 5 * 1024 * 1024 * 1024;
const ACCEPT_EXT = /\.(mp3|wav|m4a|mp4|webm)$/i;

export default function NewMeetingPage() {
  const nav = usePageNavigate();
  const { refresh } = useMeetings();
  const [title, setTitle] = useState('');
  const [date, setDate] = useState(today());
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [consent, setConsent] = useState(false);
  const [stagedId, setStagedId] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const job = useRef(null);
  const stagedIdRef = useRef(null);

  useEffect(() => {
    const onPageHide = () => {
      if (stagedIdRef.current) discardStagedMeetingKeepalive(stagedIdRef.current);
      else job.current?.abort();
    };
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.removeEventListener('pagehide', onPageHide);
      onPageHide();
    };
  }, []);

  function start(f) {
    if (!f) return;
    if (!ACCEPT_EXT.test(f.name)) { setError('Formato não aceito. Use MP3, WAV, M4A, MP4 ou WEBM.'); return; }
    if (f.size > MAX_BYTES) { setError('O arquivo passa de 5 GiB. Envie um arquivo menor.'); return; }
    if (!title.trim()) { setError('Dê um título à reunião antes de enviar.'); return; }
    setError('');
    setFile({ name: f.name, size: fileSize(f.size) });
    setProgress(0);
    job.current = stageMeeting({ title: title.trim(), date, file: f }, setProgress);
    job.current.promise
      .then(({ id }) => {
        job.current = null;
        stagedIdRef.current = id;
        setStagedId(id);
        setProgress(1);
      })
      .catch((e) => {
        job.current = null;
        setFile(null);
        setProgress(0);
        if (e.status !== -1) setError(e.status === 0 ? 'Não foi possível conectar ao servidor. Tente novamente.' : `Não foi possível enviar o arquivo. ${e.message}`);
      });
  }

  async function cancelUpload() {
    if (stagedIdRef.current) {
      const id = stagedIdRef.current;
      try {
        await discardStagedMeeting(id);
        stagedIdRef.current = null;
        setStagedId(null); setFile(null); setProgress(0); setConsent(false);
      } catch (e) { setError(`Não foi possível descartar o arquivo. ${e.message}`); }
      return;
    }
    job.current?.abort();
  }

  async function confirmUpload() {
    if (!stagedIdRef.current || !consent || confirming) return;
    setError(''); setConfirming(true);
    try {
      const id = stagedIdRef.current;
      await confirmStagedMeeting(id);
      stagedIdRef.current = null;
      await refresh();
      nav(`/reunioes/${id}`);
    } catch (e) {
      if (e.status === 404 || e.status === 410) {
        if (stagedIdRef.current) discardStagedMeetingKeepalive(stagedIdRef.current);
        stagedIdRef.current = null;
        setStagedId(null); setFile(null); setProgress(0); setConsent(false);
        setError('O envio temporário expirou ou foi descartado. Envie o arquivo novamente.');
      } else {
        setError(`Não foi possível iniciar a transcrição. ${e.message}`);
      }
    } finally { setConfirming(false); }
  }

  return (
    <div className="page page--narrow">
      <h1 className="t-page">Nova reunião</h1>
      <div className="grid2">
        <TextField id="nova-titulo" label="Título" placeholder="Ex.: Planejamento do trimestre" value={title} disabled={!!file} onChange={(e) => { setTitle(e.target.value); setError(''); }} />
        <TextField id="nova-data" label="Data" type="date" value={date} disabled={!!file} onChange={(e) => setDate(e.target.value)} />
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); if (!file) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); if (!file) start(e.dataTransfer.files[0]); }}
      >
        <Dropzone
          file={file} progress={progress} dragging={dragging}
          hint="MP3, WAV, M4A, MP4 ou WEBM · até 5 GiB"
          accept=".mp3,.wav,.m4a,.mp4,.webm"
          onChange={(e) => { start(e.target.files[0]); e.target.value = ''; }}
          onCancel={confirming ? null : cancelUpload}
        />
      </div>
      {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
      <InlineNotice>{stagedId
        ? 'Arquivo recebido em área privada temporária. Nenhuma transcrição foi iniciada. Confirme abaixo para continuar; sem confirmação, o arquivo expira após 2 horas e a limpeza periódica o remove em até cerca de 5 minutos adicionais. Ao sair, tentamos descartá-lo imediatamente.'
        : 'O arquivo será enviado primeiro para área privada temporária. O áudio só será enviado ao serviço externo após sua confirmação.'}</InlineNotice>
      <label className="consent-control">
        <input type="checkbox" checked={consent} disabled={!stagedId || confirming} onChange={(e) => setConsent(e.target.checked)} />
        <span>Confirmo que os participantes consentiram com a transcrição e o envio do áudio ao serviço externo. O vídeo original será apagado após a transcrição bem-sucedida; o áudio derivado permanece conforme a política de exclusão.</span>
      </label>
      <div className="form-actions"><Button disabled={!stagedId || !consent || confirming} variant="primary" onClick={confirmUpload}>{confirming ? 'Iniciando…' : 'Confirmar e iniciar transcrição'}</Button><Button disabled={confirming} onClick={() => nav('/')}>Voltar para a lista</Button></div>
    </div>
  );
}
