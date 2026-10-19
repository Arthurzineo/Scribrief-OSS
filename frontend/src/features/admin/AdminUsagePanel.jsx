import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { jobLabel } from './adminLabels.js';

function usd(value) {
  return value == null ? 'Indisponível' : `US$ ${Number(value).toFixed(8)}`;
}

function usageSummary(usage) {
  if (!usage || typeof usage !== 'object') return 'Indisponível';
  const parts = [];
  if (usage.seconds != null) parts.push(`Áudio: ${Number(usage.seconds).toLocaleString('pt-BR')} s`);
  if (usage.input_tokens != null) parts.push(`Entrada: ${usage.input_tokens} tokens`);
  if (usage.output_tokens != null) parts.push(`Saída: ${usage.output_tokens} tokens`);
  if (usage.total_tokens != null && usage.input_tokens == null) parts.push(`Total: ${usage.total_tokens} tokens`);
  return parts.join(' · ') || 'Indisponível';
}

const operationLabels = {
  transcription_chunk: 'Transcrição — blocos', transcription: 'Transcrição',
  minutes: 'Ata', mind_map: 'Mapa mental', correction: 'Correção sugerida',
  speaker_analysis: 'Análise de falantes',
};

export default function AdminUsagePanel({ sectors, users }) {
  const [filter, setFilter] = useState({ sector_id: '', user_id: '', meeting_id: '' });
  const [summary, setSummary] = useState(null);
  const [events, setEvents] = useState([]);
  const [page, setPage] = useState(1);
  const [next, setNext] = useState(false);
  const [meetings, setMeetings] = useState([]);
  const [meetingPage, setMeetingPage] = useState(1);
  const [meetingNext, setMeetingNext] = useState(false);
  const [meetingCount, setMeetingCount] = useState(0);
  const [error, setError] = useState('');
  const [meetingError, setMeetingError] = useState('');

  async function load(targetPage = 1, selected = filter) {
    setError('');
    try {
      const [overview, list] = await Promise.all([
        request('GET', '/api/admin/usage/summary/', { query: selected }),
        request('GET', '/api/admin/usage/', { query: { ...selected, page: targetPage } }),
      ]);
      setSummary(overview); setEvents(list.results || []); setPage(targetPage); setNext(Boolean(list.next));
    } catch (err) { setError(err.message); }
  }
  async function loadMeetings(targetPage = 1, selected = filter) {
    setMeetingError('');
    try {
      const result = await request('GET', '/api/admin/usage/meetings/', {
        query: { ...selected, page: targetPage },
      });
      setMeetings(result.results || []); setMeetingPage(targetPage);
      setMeetingNext(Boolean(result.next)); setMeetingCount(result.count || 0);
    } catch (err) { setMeetingError(err.message); }
  }
  useEffect(() => {
    const empty = { sector_id: '', user_id: '', meeting_id: '' };
    load(1, empty); loadMeetings(1, empty);
  }, []);

  return <section className="admin-card admin-report"><div className="head"><h2 className="t-sec">Uso da OpenAI</h2>
    <p className="muted">Valores por chamada são estimativas, não uma fatura. Falhas e uso sem unidades faturáveis têm custo indisponível, não necessariamente zero.</p></div>
    <form className="admin-filters" onSubmit={(event) => { event.preventDefault(); load(1); loadMeetings(1); }}>
      <label className="at-field"><span className="at-field__label">Setor</span><select className="select" value={filter.sector_id} onChange={(e) => setFilter({ ...filter, sector_id: e.target.value })}>
        <option value="">Todos</option>{sectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <label className="at-field"><span className="at-field__label">Usuário</span><select className="select" value={filter.user_id} onChange={(e) => setFilter({ ...filter, user_id: e.target.value })}>
        <option value="">Todos</option>{users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
      </select></label>
      <TextField label="Ou ID de outro usuário" type="number" min="1" value={filter.user_id} onChange={(e) => setFilter({ ...filter, user_id: e.target.value })} />
      <TextField label="ID da reunião" value={filter.meeting_id} onChange={(e) => setFilter({ ...filter, meeting_id: e.target.value })} />
      <Button type="submit" variant="primary">Filtrar</Button>
    </form>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {summary ? <><div className="admin-stats">
      <div><strong>{summary.totals.calls}</strong><span>chamadas</span></div>
      <div><strong>{usd(summary.totals.estimated_total_usd)}</strong><span>custo estimado total</span></div>
      <div><strong>{usd(summary.totals.minutes_usd)}</strong><span>gerações de ata</span></div>
      <div><strong>{summary.totals.unavailable}</strong><span>sem estimativa</span></div>
      <div><strong>{summary.totals.failed}</strong><span>tentativas falhas</span></div>
    </div><div className="admin-grid">
      <div><h3 className="t-sub">Por usuário</h3><ul className="admin-list">{summary.by_user.map((item) => <li key={item.requested_by_id}><span>{item.requested_by__username || 'Conta removida'} · {item.calls} chamadas</span><strong>{usd(item.estimated_total_usd)}</strong></li>)}</ul></div>
      <div><h3 className="t-sub">Por setor</h3><ul className="admin-list">{summary.by_sector.map((item) => <li key={item.sector_id}><span>{item.sector__name} · {item.calls} chamadas</span><strong>{usd(item.estimated_total_usd)}</strong></li>)}</ul></div>
    </div></> : null}
    <section className="admin-meeting-costs" aria-labelledby="meeting-costs-heading">
      <h3 id="meeting-costs-heading" className="t-sub">Custo por reunião</h3>
      <p className="muted">Soma das chamadas registradas por reunião: transcrição por blocos, ata, mapa mental e demais operações. Quando alguma chamada não possui estimativa, o valor mostrado é apenas a soma conhecida — não o custo final.</p>
      {meetingError ? <InlineNotice tone="erro">{meetingError}</InlineNotice> : null}
      {meetings.length ? meetings.map((meeting) => <details key={meeting.meeting_id} className="admin-meeting-cost">
        <summary><span><strong>{meeting.title || 'Reunião removida'}</strong><small className="mono">{meeting.meeting_id}</small></span>
          <span><strong>{meeting.unpriced_calls ? 'Soma conhecida' : 'Total estimado'}: {usd(meeting.estimated_usd)}</strong><small>{meeting.calls} chamadas · {meeting.unpriced_calls} sem valor · {meeting.failed_calls} falhas</small></span></summary>
        <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Operação</th><th>Chamadas</th><th>Sem valor</th><th>Falhas</th><th>Soma estimada conhecida</th></tr></thead><tbody>
          {meeting.operations.map((operation) => <tr key={operation.operation}><td>{operationLabels[operation.operation] || jobLabel(operation.operation)}</td><td>{operation.calls}</td><td>{operation.unpriced_calls}</td><td>{operation.failed_calls}</td><td>{usd(operation.estimated_usd)}</td></tr>)}
        </tbody></table></div>
      </details>) : !meetingError ? <p className="muted">Nenhuma chamada de IA para os filtros selecionados.</p> : null}
      <div className="admin-actions"><Button disabled={meetingPage <= 1} onClick={() => loadMeetings(meetingPage - 1)}>Anterior</Button><span>Página {meetingPage} · {meetingCount} reuniões</span><Button disabled={!meetingNext} onClick={() => loadMeetings(meetingPage + 1)}>Próxima</Button></div>
    </section>
    <h3 className="t-sub">Chamadas</h3>
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Quando</th><th>Usuário</th><th>Setor</th><th>Operação/modelo</th><th>Estado</th><th>Reunião</th><th>Uso</th><th>Estimativa</th></tr></thead>
      <tbody>{events.map((event) => <tr key={event.id}><td>{new Date(event.created_at).toLocaleString('pt-BR')}</td><td>{event.username}</td><td>{event.sector_name}</td><td>{operationLabels[event.operation] || jobLabel(event.operation)}<br /><small>{event.provider_id} · {event.model}</small></td><td>{event.outcome === 'failed' ? 'Falhou' : 'Sucesso'}</td><td className="mono">{event.meeting_id}</td><td>{usageSummary(event.usage)}<br /><small>{event.usage_basis === 'measured' ? 'Medido pela resposta' : 'Indisponível'}</small></td><td>{usd(event.estimated_usd)}<br /><small>{event.estimate_status === 'estimated' ? 'Estimado' : 'Indisponível'}</small></td></tr>)}</tbody></table></div>
    <div className="admin-actions"><Button disabled={page <= 1} onClick={() => load(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={!next} onClick={() => load(page + 1)}>Próxima</Button></div>
  </section>;
}
