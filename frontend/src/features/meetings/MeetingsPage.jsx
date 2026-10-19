import { useMemo, useState } from 'react';
import { usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, InlineNotice, MeetingRow, TextField } from '../../shared/components/index.js';
import { useMeetings } from '../../shared/context/MeetingsContext.jsx';
import { statusInfo } from '../../api/mappers.js';
import { dateBR, duration } from '../../shared/lib/format.js';

const FILTERS = [
  ['todos', 'Todos'],
  ['sucesso', 'Prontas'],
  ['processando', 'Processando'],
  ['erro', 'Com erro'],
];

export default function MeetingsPage() {
  const { items, loading, error, refresh } = useMeetings();
  const nav = usePageNavigate();
  const [q, setQ] = useState('');
  const [f, setF] = useState('todos');

  const list = useMemo(() => items.filter((m) => {
    const tone = statusInfo(m).tone;
    const okF = f === 'todos' || tone === f || (f === 'processando' && tone === 'neutro');
    return okF && m.title.toLowerCase().includes(q.trim().toLowerCase());
  }), [items, q, f]);

  return (
    <div className="page">
      <div className="head">
        <h1 className="t-page">Reuniões</h1>
        <Button variant="primary" icon="plus" onClick={() => nav('/reunioes/nova')}>Nova reunião</Button>
      </div>

      {error ? <InlineNotice tone="erro" action={<Button icon="retry" onClick={refresh}>Tentar novamente</Button>}>Não foi possível carregar as reuniões.</InlineNotice> : null}

      {loading ? <p className="muted">Carregando…</p>
        : items.length === 0 && !error ? (
          <div className="empty">
            <p>Nenhuma reunião ainda. Envie uma gravação para receber a transcrição.</p>
            <Button variant="primary" icon="upload" onClick={() => nav('/reunioes/nova')}>Enviar a primeira gravação</Button>
          </div>
        ) : items.length > 0 ? (
          <>
            <div className="toolbar">
              <TextField id="busca" label="Buscar por título" type="search" placeholder="Ex.: planejamento" value={q} onChange={(e) => setQ(e.target.value)} />
              <div className="field-inline">
                <label htmlFor="filtro">Estado</label>
                <select id="filtro" className="select" value={f} onChange={(e) => setF(e.target.value)}>
                  {FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                </select>
              </div>
            </div>
            {list.length ? (
              <div className="at-list">
                {list.map((m) => {
                  const s = statusInfo(m);
                  return (
                    <MeetingRow
                      key={m.id} title={m.title} date={dateBR(m.date)}
                      duration={m.durationSeconds ? duration(m.durationSeconds) : null}
                      speakers={m.speakerCount || null} tone={s.tone} statusLabel={s.label}
                      onClick={() => nav(`/reunioes/${m.id}`)}
                    />
                  );
                })}
              </div>
            ) : (
              <div className="empty">
                <p>Nenhuma reunião encontrada com esses filtros.</p>
                <Button onClick={() => { setQ(''); setF('todos'); }}>Limpar filtros</Button>
              </div>
            )}
            <p className="list-foot">{list.length} {list.length === 1 ? 'reunião' : 'reuniões'}</p>
          </>
        ) : null}
    </div>
  );
}
