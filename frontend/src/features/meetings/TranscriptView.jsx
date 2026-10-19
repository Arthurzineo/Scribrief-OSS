import { useEffect, useMemo, useRef, useState } from 'react';
import { AudioPlayer, Button, ConfirmModal, InlineNotice, SpeakerRow, Utterance } from '../../shared/components/index.js';
import { dismissSpeakerMerges, getCorrectionSuggestions, getSpeakerMergeSuggestions, mergeSpeakersBatch, renameSpeaker, suggestCorrections, suggestSpeakerMerges, updateSegment } from '../../api/meetings.js';
import { useToast } from '../../shared/context/ToastContext.jsx';
import useAudio from '../../shared/lib/useAudio.js';
import { activeSegmentId } from '../../shared/lib/transcriptPlayback.js';
import { minutes as fmtMinutes, slug, stamp } from '../../shared/lib/format.js';
import { transcriptToTxt } from '../../shared/lib/export.js';
import { downloadFile } from '../../shared/lib/download.js';
import useGenerate from './useGenerate.js';

export const speakerName = (sp) => (sp?.name?.trim() ? sp.name.trim() : sp?.label || 'Pessoa');
export const isGeneric = (sp) => !sp.name || !sp.name.trim();

/** Agrupa falas seguidas do mesmo falante. */
export function groupSegments(m) {
  const byId = Object.fromEntries(m.speakers.map((s) => [s.id, s]));
  const groups = [];
  m.segments.forEach((seg, i) => {
    const last = groups[groups.length - 1];
    if (last && last.speakerId === seg.speakerId) last.items.push({ seg, i });
    else groups.push({ speakerId: seg.speakerId, speaker: byId[seg.speakerId], items: [{ seg, i }] });
  });
  return groups;
}

export default function TranscriptView({ m, setM, reload, refreshList, onGenerated }) {
  const say = useToast();
  const audio = useAudio(m.audioUrl);
  const [selectedSpeakers, setSelectedSpeakers] = useState([]);
  const [batchTarget, setBatchTarget] = useState('');
  const [batchConfirm, setBatchConfirm] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [suggestions, setSuggestions] = useState({});
  const [checking, setChecking] = useState(false);
  const [deciding, setDeciding] = useState(null);
  const [reviewed, setReviewed] = useState(false);
  const [speakerAnalysis, setSpeakerAnalysis] = useState(null);
  const [speakerAnalysisLoading, setSpeakerAnalysisLoading] = useState(true);
  const [speakerGroupSelection, setSpeakerGroupSelection] = useState({});
  const [speakerGroupBusy, setSpeakerGroupBusy] = useState(false);
  const [confirmSpeakerGroup, setConfirmSpeakerGroup] = useState(null);
  const readRef = useRef(null);
  const cancelled = useRef(false);
  useEffect(() => {
    cancelled.current = false;
    return () => { cancelled.current = true; };
  }, []);
  const gen = useGenerate(m, setM, refreshList, say);
  const speakerGroups = speakerAnalysis?.groups || [];
  const speakerChecking = speakerAnalysis?.status === 'processing';
  const speakerCaution = Boolean(speakerAnalysis?.caution);
  const speakerSampleTimes = speakerAnalysis?.sample_times || {};
  const speakerAnalyzed = speakerAnalysis?.status === 'ready';
  const groups = useMemo(() => groupSegments(m), [m]);
  const selected = m.speakers.filter((speaker) => selectedSpeakers.includes(speaker.id));
  const targetId = selected.some((speaker) => speaker.id === batchTarget) ? batchTarget : selected[0]?.id;
  const targetSpeaker = selected.find((speaker) => speaker.id === targetId);
  const currentSegmentId = audio.playing || audio.current > 0
    ? activeSegmentId(m.segments, audio.current)
    : null;

  useEffect(() => {
    if (currentSegmentId == null || document.activeElement?.isContentEditable) return;
    const element = document.getElementById(`fala-${m.id}-${currentSegmentId}`);
    if (!element) return;
    const container = readRef.current;
    if (!container) return;
    const bounds = element.getBoundingClientRect();
    const viewport = container.getBoundingClientRect();
    if (bounds.top < viewport.top || bounds.bottom > viewport.bottom) {
      const top = container.scrollTop + bounds.top - viewport.top;
      container.scrollTo({ top: top - (container.clientHeight - bounds.height) / 2, behavior: 'instant' });
    }
  }, [currentSegmentId, m.id]);

  useEffect(() => {
    if (!m.canEdit) { setSpeakerAnalysisLoading(false); return undefined; }
    let mounted = true;
    setSpeakerAnalysisLoading(true);
    getSpeakerMergeSuggestions(m.id).then((result) => {
      if (mounted) setSpeakerAnalysis(result);
    }).catch(() => {
      if (mounted) say('Não foi possível carregar as sugestões de falantes.');
    }).finally(() => { if (mounted) setSpeakerAnalysisLoading(false); });
    return () => { mounted = false; };
  }, [m.id, m.transcriptionVersion, m.canEdit]);

  useEffect(() => {
    if (!speakerChecking) return undefined;
    let mounted = true;
    const timer = setInterval(async () => {
      try {
        const result = await getSpeakerMergeSuggestions(m.id);
        if (mounted) setSpeakerAnalysis(result);
      } catch {
        // A tarefa continua no servidor; a próxima atualização tentará de novo.
      }
    }, 3000);
    return () => { mounted = false; clearInterval(timer); };
  }, [m.id, speakerChecking]);

  useEffect(() => {
    if (!speakerAnalyzed) return;
    setSpeakerGroupSelection((old) => Object.fromEntries(speakerGroups.map((codes) => {
      const key = codes.join('|');
      return [key, old[key] || (codes.length === 2 ? codes : [])];
    })));
  }, [speakerAnalysis]);

  const firstStart = useMemo(() => {
    const r = {};
    m.segments.forEach((s) => { if (r[s.speakerId] == null) r[s.speakerId] = s.start; });
    return r;
  }, [m.segments]);

  function setName(spId, name) {
    setM({ ...m, speakers: m.speakers.map((s) => (s.id === spId ? { ...s, name } : s)) });
  }
  async function commitName(spId, name) {
    if (!name.trim()) { await reload(); return; }
    try { await renameSpeaker(m.id, spId, name.trim(), m.transcriptionVersion); }
    catch (e) { say(`Não foi possível salvar o nome. ${e.message}`); }
    finally { await reload(); }
  }
  async function editSegment(index, text) {
    const seg = m.segments[index];
    if (!seg || seg.text === text) return;
    setM({ ...m, segments: m.segments.map((s, i) => (i === index ? { ...s, text } : s)) });
    try {
      await updateSegment(m.id, seg, text, m.transcriptionVersion);
      setSuggestions((old) => { const next = { ...old }; delete next[seg.id]; return next; });
    }
    catch (e) { say(`Não foi possível salvar a correção. ${e.message}`); }
    finally { await reload(); }
  }
  async function mergeSelected() {
    if (selected.length < 2 || !targetId) return;
    setBatchBusy(true);
    try {
      await mergeSpeakersBatch(m.id, selected.filter((speaker) => speaker.id !== targetId).map((speaker) => speaker.id), targetId, m.transcriptionVersion);
      await reload();
      setSelectedSpeakers([]);
      setBatchTarget('');
      say('Falantes selecionados unidos.');
    } catch (e) {
      say(`Não foi possível unir os falantes. ${e.message}`);
      await reload();
      setSelectedSpeakers([]);
      setBatchTarget('');
    } finally { setBatchBusy(false); setBatchConfirm(false); }
  }
  async function generate() {
    setConfirm(false);
    if (await gen.run()) onGenerated();
  }
  function download() {
    const g = groups.map((x) => ({ name: speakerName(x.speaker), segments: x.items.map((it) => it.seg) }));
    downloadFile(`${slug(`transcricao ${m.title}`)}.txt`, transcriptToTxt(m, g));
  }

  async function askCorrections() {
    setChecking(true);
    setReviewed(false);
    try {
      let result = await suggestCorrections(m.id, m.transcriptionVersion);
      const deadline = Date.now() + 10 * 60 * 1000;
      while (result.status === 'processing' && !cancelled.current && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (!cancelled.current) result = await getCorrectionSuggestions(m.id, result.job_id);
      }
      if (cancelled.current) return;
      if (result.status === 'processing') throw new Error('A análise ainda está em andamento. Tente novamente em instantes.');
      if (result.status === 'error') throw new Error(result.message || 'A análise falhou.');
      setSuggestions(Object.fromEntries((result.sugestoes || []).map((item) => [item.segmento_id, item])));
      setReviewed(true);
      if (!result.sugestoes?.length) say('A IA não encontrou ajustes suficientemente seguros para sugerir.');
    } catch (error) {
      say(`Não foi possível analisar a transcrição. ${error.message}`);
      if (error.status === 409) await reload();
    } finally { setChecking(false); }
  }
  async function acceptSuggestion(segmentId) {
    const suggestion = suggestions[segmentId];
    const segment = m.segments.find((item) => item.id === segmentId);
    if (!suggestion || !segment || segment.text !== suggestion.texto_original) {
      setSuggestions((old) => { const next = { ...old }; delete next[segmentId]; return next; });
      say('A fala mudou desde a análise. Execute a revisão novamente.');
      return;
    }
    setDeciding(segmentId);
    try {
      await updateSegment(m.id, segment, suggestion.texto_sugerido, m.transcriptionVersion);
      setSuggestions((old) => { const next = { ...old }; delete next[segmentId]; return next; });
      await reload();
      say('Correção aceita e salva.');
    } catch (error) {
      say(`Não foi possível aceitar a correção. ${error.message}`);
      await reload();
    } finally { setDeciding(null); }
  }
  function rejectSuggestion(segmentId) {
    setSuggestions((old) => { const next = { ...old }; delete next[segmentId]; return next; });
  }

  async function askSpeakerMerges() {
    try {
      const result = await suggestSpeakerMerges(m.id, m.transcriptionVersion);
      setSpeakerAnalysis(result);
      if (result.status === 'processing') say('Análise iniciada. Você pode sair desta página e voltar depois.');
    } catch (error) {
      say(`Não foi possível analisar os falantes. ${error.message}`);
      try { setSpeakerAnalysis(await getSpeakerMergeSuggestions(m.id)); } catch { /* keep last state */ }
      if (error.status === 409) await reload();
    }
  }

  async function dismissSpeakerGroup(codes) {
    setSpeakerGroupBusy(true);
    try {
      const result = await dismissSpeakerMerges(m.id, m.transcriptionVersion, codes);
      setSpeakerAnalysis(result);
      say(codes ? 'Sugestão ignorada.' : 'Sugestões dispensadas.');
    } catch (error) {
      say(`Não foi possível dispensar a sugestão. ${error.message}`);
      try { setSpeakerAnalysis(await getSpeakerMergeSuggestions(m.id)); } catch { /* keep last state */ }
    } finally { setSpeakerGroupBusy(false); }
  }

  async function acceptSpeakerGroup() {
    const codes = confirmSpeakerGroup?.codes;
    if (!codes || codes.length < 2) return;
    setSpeakerGroupBusy(true);
    try {
      const merged = await mergeSpeakersBatch(m.id, codes.slice(1), codes[0], m.transcriptionVersion);
      let dismissalFailed = false;
      try {
        const result = await dismissSpeakerMerges(m.id, merged.version, confirmSpeakerGroup.key.split('|'));
        setSpeakerAnalysis(result);
      } catch {
        dismissalFailed = true;
        try { setSpeakerAnalysis(await getSpeakerMergeSuggestions(m.id)); } catch { /* merge already completed */ }
      }
      setSelectedSpeakers([]);
      await reload();
      say(dismissalFailed
        ? 'Falantes unidos, mas não foi possível arquivar a sugestão. Atualize a página e dispense-a.'
        : 'Falantes unidos após sua confirmação. Confira as falas e o nome da pessoa.');
    } catch (error) {
      await reload();
      say(`Não foi possível unir os falantes. ${error.message}`);
    } finally { setSpeakerGroupBusy(false); setConfirmSpeakerGroup(null); }
  }

  const nameForCode = (code) => speakerName(m.speakers.find((speaker) => speaker.id === code));

  return (
    <div className="mt">
      <div className="mt__col">
        <div className="mt__read" ref={readRef} role="region" aria-label="Falas da transcrição" tabIndex={0}>
          {m.segments.length === 0 ? <p className="muted">A transcrição está vazia.</p> : null}
          {groups.map((g) => (
            <Utterance
              key={g.items[0].seg.id}
              speakerIndex={g.speaker?.index || 1}
              speakerName={speakerName(g.speaker)}
              editable={m.canEdit}
              segments={g.items.map(({ seg }) => ({
                key: seg.id, domId: `fala-${m.id}-${seg.id}`, time: stamp(seg.start),
                seconds: seg.start, text: seg.text, active: seg.id === currentSegmentId,
                suggestion: m.canEdit && suggestions[seg.id]?.texto_original === seg.text ? suggestions[seg.id] : null,
              }))}
              onSeek={(t) => audio.seek(t, true)}
              onEdit={m.canEdit ? (si, text) => editSegment(g.items[si].i, text) : undefined}
              onAccept={acceptSuggestion}
              onReject={rejectSuggestion}
              deciding={deciding}
            />
          ))}
        </div>
        <div className="mt__player">
          <AudioPlayer
            playing={audio.playing} current={audio.current} duration={audio.duration || m.durationSeconds} speed={audio.speed}
            disabled={!audio.available} onToggle={audio.toggle} onSeek={(v) => audio.seek(v)} onSpeed={audio.setSpeed}
          />
        </div>
      </div>

      <aside className="mt__sidebar" aria-label="Falantes e ações da transcrição">
        <section className="mt__panel" aria-labelledby="mt-speakers-title">
        <h2 id="mt-speakers-title" className="t-sub">Falantes</h2>
        {m.canEdit ? <p className="mt__hint">Troque "Pessoa N" pelo nome real. A mudança aparece em todas as falas.</p> : null}
        {m.canEdit && m.speakers.length > 1 ? <p className="mt__hint">Selecione dois ou mais falantes para unir em um só.</p> : null}
        {m.speakers.map((sp) => (
          <div key={sp.id}>
            {m.canEdit && m.speakers.length > 1 ? (
              <label className="mt__speaker-select">
                <input type="checkbox" checked={selectedSpeakers.includes(sp.id)} disabled={batchBusy}
                  onChange={() => setSelectedSpeakers((old) => old.includes(sp.id) ? old.filter((id) => id !== sp.id) : [...old, sp.id])} />
                Selecionar {speakerName(sp)}
              </label>
            ) : null}
            <SpeakerRow
              index={sp.index} name={sp.name} placeholder={sp.label} total={fmtMinutes(sp.totalSeconds)}
              readOnly={!m.canEdit}
              onNameChange={(v) => setName(sp.id, v)}
              onNameCommit={(v) => commitName(sp.id, v)}
              onListen={() => audio.seek(firstStart[sp.id] ?? 0, true)}
            />
          </div>
        ))}
        {!audio.available && m.audioUrl ? <InlineNotice tone="erro">Não foi possível carregar o áudio.</InlineNotice> : null}
        </section>
        {m.canEdit && m.speakers.length > 1 && m.audioUrl ? (
          <section className="mt__panel mt__panel--suggestions" aria-label="Sugestões de união de falantes">
            <h2 className="t-sub">Falantes semelhantes</h2>
            <p className="mt__hint">A IA compara duas amostras limpas por falante. O resultado é uma hipótese: ouça antes de unir.</p>
            <p className="mt__hint" role="status">
              {speakerAnalysisLoading ? 'Consultando análises…' : `${speakerAnalysis?.remaining ?? 2} de 2 análises disponíveis nesta reunião.`}
            </p>
            <Button disabled={speakerAnalysisLoading || speakerChecking || speakerGroupBusy || speakerAnalysis?.remaining === 0 || (speakerAnalyzed && speakerGroups.length > 0)} onClick={askSpeakerMerges}>
              {speakerChecking ? 'IA comparando vozes…' : speakerAnalyzed && speakerGroups.length ? 'Revise as sugestões abaixo' : 'IA sugere uniões'}
            </Button>
            {speakerChecking ? <p className="mt__hint" role="status">A análise continua em segundo plano. Você pode sair desta página e voltar depois.</p> : null}
            {speakerAnalysis?.status === 'error' ? <InlineNotice tone="erro">{speakerAnalysis.message || 'A análise falhou.'}</InlineNotice> : null}
            {speakerCaution ? <InlineNotice tone="neutro">A IA deu o mesmo rótulo a todas as amostras. Isso pode ser uma simplificação do modelo, não prova de que sejam a mesma pessoa. Selecione apenas vozes que você confirmou ao ouvir.</InlineNotice> : null}
            {speakerAnalyzed && !speakerGroups.length ? <p className="mt__hint" role="status">Nenhuma união sugerida.</p> : null}
            {speakerGroups.map((codes) => (
              <div className="mt__suggestion" key={codes.join('-')}>
                <p className="mt__hint">A IA atribuiu o mesmo rótulo a estas vozes. Ouça e marque apenas as que você considera da mesma pessoa.</p>
                <div className="mt__suggestion-list">
                  {codes.map((code) => (
                    <div className="mt__suggestion-person" key={code}>
                      <label className="mt__speaker-select">
                        <input type="checkbox" checked={(speakerGroupSelection[codes.join('|')] || []).includes(code)}
                          onChange={() => setSpeakerGroupSelection((old) => {
                            const key = codes.join('|');
                            const selectedCodes = old[key] || [];
                            return { ...old, [key]: selectedCodes.includes(code)
                              ? selectedCodes.filter((item) => item !== code) : [...selectedCodes, code] };
                          })} />
                        {nameForCode(code)} ({code})
                      </label>
                      {(speakerSampleTimes[code] || [firstStart[code] ?? 0]).map((seconds, index) => (
                        <Button key={`${code}-${index}`} disabled={!audio.available}
                          aria-label={`Ouvir amostra ${index + 1} de ${nameForCode(code)}`}
                          onClick={() => audio.seek(seconds, true)}>
                          Ouvir {index + 1}
                        </Button>
                      ))}
                    </div>
                  ))}
                </div>
                <div className="mt__suggestion-list">
                  <Button variant="primary" disabled={(speakerGroupSelection[codes.join('|')] || []).length < 2}
                    onClick={() => setConfirmSpeakerGroup({ key: codes.join('|'), codes: speakerGroupSelection[codes.join('|')] })}>
                    Confirmar e unir selecionados
                  </Button>
                  <Button disabled={speakerGroupBusy} onClick={() => dismissSpeakerGroup(codes)}>Ignorar</Button>
                </div>
              </div>
            ))}
            {speakerGroups.length ? <Button disabled={speakerGroupBusy} onClick={() => dismissSpeakerGroup()}>Negar todas as sugestões</Button> : null}
          </section>
        ) : null}
        {m.canEdit && selected.length > 0 ? (
          <section className="mt__panel mt__panel--merge" aria-label="Unir falantes selecionados">
          <div className="mt__batch-merge">
            <p className="mt__hint" role="status">{selected.length} {selected.length === 1 ? 'falante selecionado' : 'falantes selecionados'}</p>
            {selected.length > 1 ? (
              <>
                <label htmlFor="batch-merge-target" className="at-field__label">Manter como</label>
                <select id="batch-merge-target" className="select" value={targetId} onChange={(event) => setBatchTarget(event.target.value)}>
                  {selected.map((speaker) => <option key={speaker.id} value={speaker.id}>{speakerName(speaker)}</option>)}
                </select>
                <Button variant="primary" disabled={batchBusy} onClick={() => setBatchConfirm(true)}>Unir selecionados</Button>
              </>
            ) : null}
            <Button disabled={batchBusy} onClick={() => { setSelectedSpeakers([]); setBatchTarget(''); }}>Limpar seleção</Button>
          </div>
          </section>
        ) : null}
        <section className="mt__panel mt__panel--actions" aria-label="Ações da transcrição">
        <div className="mt__panel-actions">
          {m.canEdit ? <Button disabled={checking || deciding !== null || m.minutesStatus === 'generating'} onClick={askCorrections}>
            {checking ? 'IA analisando…' : 'IA ajuda a corrigir a transcrição'}
          </Button> : null}
          {reviewed ? <p className="mt__hint" role="status">{Object.keys(suggestions).length} sugestão(ões) pendente(s). Nenhum texto é alterado sem sua confirmação.</p> : null}
          <Button icon="download" onClick={download}>Baixar transcrição</Button>
          {m.canEdit ? <Button variant="primary" disabled={gen.busy || m.minutesStatus === 'generating'} onClick={() => (m.speakers.some(isGeneric) ? setConfirm(true) : generate())}>
            {m.minutesStatus === 'generating' ? 'Gerando ata…' : m.minutes ? 'Gerar ata novamente' : 'Gerar ata'}
          </Button> : null}
        </div>
        </section>
      </aside>

      <ConfirmModal
        open={confirm} title="Gerar ata" message="Ainda há falantes sem nome. Gerar mesmo assim?"
        confirmLabel="Gerar ata" onCancel={() => setConfirm(false)} onConfirm={generate}
      />
      <ConfirmModal
        open={batchConfirm} busy={batchBusy} title="Unir falantes selecionados?"
        message={`As falas de ${selected.length} falantes passarão a aparecer como ${speakerName(targetSpeaker)}. O texto das falas não será alterado.`}
        confirmLabel="Unir falantes" onCancel={() => setBatchConfirm(false)} onConfirm={mergeSelected}
      />
      <ConfirmModal
        open={Boolean(confirmSpeakerGroup)} busy={speakerGroupBusy} title="Confirmar união sugerida?"
        message={`Você ouviu e confirmou que ${confirmSpeakerGroup?.codes.map(nameForCode).join(' e ')} são a mesma pessoa? As falas serão unidas, mas o texto não será alterado.`}
        confirmLabel="Confirmar e unir" onCancel={() => setConfirmSpeakerGroup(null)} onConfirm={acceptSpeakerGroup}
      />
    </div>
  );
}
