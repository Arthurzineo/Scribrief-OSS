import { useState } from 'react';
import { Button, ConfirmModal, InlineNotice, StepList } from '../../shared/components/index.js';
import { reviewMinutes, saveMinutes } from '../../api/meetings.js';
import { useToast } from '../../shared/context/ToastContext.jsx';
import { dateBR, duration, slug } from '../../shared/lib/format.js';
import { minutesToPdf, minutesToTxt, reviewLabel } from '../../shared/lib/export.js';
import { downloadFile } from '../../shared/lib/download.js';
import { isGeneric, speakerName } from './TranscriptView.jsx';
import useGenerate from './useGenerate.js';

/** A ata usa a paleta editorial do Scribrief; o resto da tela segue neutro. */
export default function MinutesView({ m, setM, reload, refreshList }) {
  const say = useToast();
  const [confirm, setConfirm] = useState(null); // 'regerar' | 'nomes' | 'revisar'
  const [menu, setMenu] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const gen = useGenerate(m, setM, refreshList, say);
  const a = m.minutes;
  const people = a?.participants || m.speakers.map(speakerName);

  async function update(next) {
    if (!m.canEdit) return;
    setSaving(true);
    setM({ ...m, minutes: { ...next, reviewer: null, reviewedAt: null } });
    try { await saveMinutes(m.id, next, m.minutesVersion); }
    catch (e) { say(`Não foi possível salvar a edição. ${e.message}`); }
    finally { await reload(); setSaving(false); }
  }
  const edit = (key, idx, field) => m.canEdit ? ({
    contentEditable: 'true',
    suppressContentEditableWarning: true,
    onBlur: (e) => {
      const v = e.currentTarget.textContent;
      const next = structuredClone(a);
      if (idx == null) next[key] = v; else if (field) next[key][idx][field] = v; else next[key][idx] = v;
      if (JSON.stringify(next) !== JSON.stringify(a)) update(next);
    },
  }) : ({});
  const editTask = (index, field, original) => ({
    defaultValue: original,
    readOnly: !m.canEdit,
    onBlur: m.canEdit ? (event) => {
      const value = event.currentTarget.value.trim();
      if (field === 'task' && !value) {
        event.currentTarget.value = original;
        return;
      }
      if (value !== original) {
        const next = structuredClone(a);
        next.tasks[index][field] = value;
        update(next);
      }
    } : undefined,
  });
  async function regenerate() {
    if (confirm === 'regerar' && m.speakers.some(isGeneric)) { setConfirm('nomes'); return; }
    setConfirm(null);
    await gen.run();
  }
  async function markReviewed() {
    setConfirm(null);
    if (m.minutesStale) {
      say('A ata está desatualizada. Gere novamente antes de marcar a revisão.');
      return;
    }
    setReviewing(true);
    try {
      await reviewMinutes(m.id, m.minutesVersion);
      say('Ata marcada como revisada.');
    } catch (e) { say(`Não foi possível marcar a revisão. ${e.message}`); }
    finally { setReviewing(false); await reload(); }
  }
  async function exportPdf() {
    setMenu(false);
    try { downloadFile(`${slug(`ata ${m.title}`)}.pdf`, await minutesToPdf(m, a, people)); }
    catch { say('Não foi possível gerar o PDF. Tente o formato .txt.'); }
  }
  function exportTxt() {
    setMenu(false);
    downloadFile(`${slug(`ata ${m.title}`)}.txt`, minutesToTxt(m, a, people));
  }
  async function copy() {
    const text = minutesToTxt(m, a, people);
    try { await navigator.clipboard.writeText(text); say('Ata copiada'); }
    catch { say('Não foi possível copiar. Selecione o texto da ata e copie manualmente.'); }
  }

  let body;
  if (m.minutesStatus === 'generating') {
    body = (
      <div className="proc">
        <StepList steps={[{ label: 'Gerando ata', state: 'andamento', detail: 'Resumo, decisões e tarefas a partir da transcrição.' }]} />
        <p className="proc__note">Leva menos de um minuto. Você pode voltar para a transcrição enquanto isso.</p>
      </div>
    );
  } else if (m.minutesStatus === 'failed') {
    body = (
      <div className="proc">
        <StepList steps={[{ label: 'Gerando ata', state: 'erro', detail: m.minutesError || 'Não foi possível gerar a ata.' }]} />
        {m.canEdit ? <div className="at-hrow"><Button variant="primary" icon="retry" disabled={gen.busy} onClick={() => gen.run()}>Tentar novamente</Button></div> : null}
      </div>
    );
  } else if (!a) {
    body = (
      <div className="empty">
        <p>Esta reunião ainda não tem ata. Nomeie os falantes e gere a ata a partir da transcrição.</p>
        {m.canEdit ? <Button variant="primary" disabled={gen.busy} onClick={() => (m.speakers.some(isGeneric) ? setConfirm('nomes') : gen.run())}>Gerar ata</Button> : null}
      </div>
    );
  } else {
    body = (
      <>
        <div className="ata-actions">
          <Button icon="download" aria-expanded={menu} aria-haspopup="menu" onClick={() => setMenu(!menu)}>Baixar</Button>
          {menu ? (
            <div className="menu" role="menu">
              <button type="button" role="menuitem" onClick={exportPdf}>PDF (.pdf)</button>
              <button type="button" role="menuitem" onClick={exportTxt}>Texto (.txt)</button>
            </div>
          ) : null}
          <Button icon="copy" onClick={copy}>Copiar</Button>
          {m.canEdit && !m.minutesStale && !a.reviewedAt ? (
            <Button disabled={reviewing || saving} onClick={() => setConfirm('revisar')}>Marcar ata como revisada</Button>
          ) : null}
          {m.canEdit ? <Button variant="destructive" icon="retry" disabled={gen.busy} onClick={() => setConfirm('regerar')}>Gerar novamente</Button> : null}
        </div>
        <p className="doc__meta">{m.canEdit ? 'Clique em qualquer trecho da ata para editar. A revisão é opcional; novas edições removem a marca de revisão.' : 'Ata compartilhada em modo leitura.'}</p>
        <article className="doc">
          <header className="doc__head">
            <p className="doc__kicker">Ata de reunião</p>
            <h2 className="doc__title">{m.title}</h2>
            <div className="doc__facts">
              <span>{dateBR(m.date)}</span>
              <span className="mono">{duration(m.durationSeconds)}</span>
              <span>Participantes: {people.join(', ') || 'Não informados'}</span>
            </div>
            <p className="doc__review">{reviewLabel(a)}</p>
          </header>
          <section>
            <h2 className="t-sec">Participantes</h2>
            <ul className="doc__participants">
              {a.participants.map((name, i) => (
                <li key={i}>
                  <label className="sr-only" htmlFor={`participant-${i}`}>Nome do participante {i + 1}</label>
                  <input id={`participant-${i}`} className="doc__input" defaultValue={name} readOnly={!m.canEdit}
                    onBlur={m.canEdit ? (e) => {
                      const value = e.target.value.trim();
                      if (value && value !== name) {
                        const next = structuredClone(a); next.participants[i] = value; update(next);
                      } else if (!value) e.target.value = name;
                    } : undefined} />
                  {m.canEdit ? <Button onClick={() => update({ ...a, participants: a.participants.filter((_, index) => index !== i) })}>Remover</Button> : null}
                </li>
              ))}
            </ul>
            {m.canEdit ? <Button onClick={() => update({ ...a, participants: [...a.participants, 'Novo participante'] })}>Adicionar participante</Button> : null}
          </section>
          <section><h2 className="t-sec">Resumo executivo</h2><p {...edit('summary')}>{a.summary}</p></section>
          <section>
            <h2 className="t-sec">Tópicos discutidos</h2>
            {a.topics.map((topic, i) => (
              <div className="doc__topic" key={i}>
                <h3 className="t-sub" {...edit('topics', i, 'title')}>{topic.title}</h3>
                <p {...edit('topics', i, 'comment')}>{topic.comment}</p>
              </div>
            ))}
            {m.canEdit ? <Button onClick={() => update({ ...a, topics: [...a.topics, { title: 'Novo tópico', comment: 'Descreva o que foi discutido.' }] })}>Adicionar tópico</Button> : null}
          </section>
          <section>
            <h2 className="t-sec">Decisões</h2>
            <ol>{a.decisions.map((d, i) => (
              <li key={i} className="doc__decision">
                <span {...edit('decisions', i)}>{d}</span>
                {m.canEdit ? <Button onClick={() => update({ ...a, decisions: a.decisions.filter((_, index) => index !== i) })}>Remover</Button> : null}
              </li>
            ))}</ol>
            {m.canEdit ? <Button onClick={() => update({ ...a, decisions: [...a.decisions, 'Nova decisão'] })}>Adicionar decisão</Button> : null}
          </section>
          <section>
            <h2 className="t-sec">Tarefas pendentes</h2>
            <div className="doc__tasks">
              {a.tasks.map((task, i) => (
                <div className="doc__task" key={`${i}:${task.task}:${task.owner}:${task.due}`}>
                  <div className="doc__task-fields">
                    <label className="doc__task-field">
                      <span>Tarefa/ação</span>
                      <textarea className="doc__task-input doc__task-input--description" rows="2"
                        {...editTask(i, 'task', task.task)} />
                    </label>
                    <label className="doc__task-field">
                      <span>Responsável</span>
                      <input className="doc__task-input" type="text" placeholder="Não definido"
                        {...editTask(i, 'owner', task.owner)} />
                    </label>
                    <label className="doc__task-field">
                      <span>Prazo</span>
                      <input className="doc__task-input" type="text" placeholder="Não definido"
                        {...editTask(i, 'due', task.due)} />
                    </label>
                  </div>
                  {m.canEdit ? <Button disabled={saving} onClick={() => update({ ...a, tasks: a.tasks.filter((_, index) => index !== i) })}>Remover tarefa</Button> : null}
                </div>
              ))}
            </div>
            {m.canEdit ? <Button onClick={() => update({ ...a, tasks: [...a.tasks, { task: 'Nova tarefa', owner: '', due: '' }] })}>Adicionar tarefa pendente</Button> : null}
          </section>
        </article>
      </>
    );
  }

  return (
    <div className="ata-wrap">
      {m.minutesStale ? (
        <InlineNotice tone="processando">
          A transcrição mudou desde a geração da ata. Gere novamente para atualizar e poder revisar o documento.
        </InlineNotice>
      ) : null}
      {body}
      <ConfirmModal
        open={confirm === 'regerar'} destructive title="Gerar novamente"
        message="A ata atual, com as suas edições, será substituída." confirmLabel="Gerar novamente"
        onCancel={() => setConfirm(null)} onConfirm={regenerate}
      />
      <ConfirmModal
        open={confirm === 'nomes'} title="Gerar ata" message="Ainda há falantes sem nome. Gerar mesmo assim?"
        confirmLabel="Gerar ata" onCancel={() => setConfirm(null)} onConfirm={() => { setConfirm(null); gen.run(); }}
      />
      <ConfirmModal
        open={confirm === 'revisar'} title="Confirmar revisão da ata"
        message="Confirma que você conferiu a ata? Seu usuário e a data da revisão aparecerão no documento. A revisão não é obrigatória."
        confirmLabel="Marcar como revisada" onCancel={() => setConfirm(null)} onConfirm={markReviewed}
      />
    </div>
  );
}
