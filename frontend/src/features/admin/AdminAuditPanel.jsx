import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { actionLabel, outcomeLabel, targetLabel } from './adminLabels.js';

export default function AdminAuditPanel({ sectors, users }) {
  const [filter, setFilter] = useState({ sector_id: '', actor_id: '', action: '', target_id: '', from_date: '', to_date: '' });
  const [events, setEvents] = useState([]);
  const [page, setPage] = useState(1);
  const [next, setNext] = useState(false);
  const [error, setError] = useState('');
  async function load(targetPage = 1, selected = filter) {
    setError('');
    try {
      const data = await request('GET', '/api/admin/audit/', { query: { ...selected, page: targetPage } });
      setEvents(data.results || []); setPage(targetPage); setNext(Boolean(data.next));
    } catch (err) { setError(err.message); }
  }
  useEffect(() => { load(1, { sector_id: '', actor_id: '', action: '', target_id: '', from_date: '', to_date: '' }); }, []);
  const exportQuery = new URLSearchParams(Object.entries(filter).filter(([, value]) => value)).toString();
  return <section className="admin-card admin-report"><h2 className="t-sec">Auditoria</h2>
    <form className="admin-filters" onSubmit={(event) => { event.preventDefault(); load(1); }}>
      <label className="at-field"><span className="at-field__label">Setor</span><select className="select" value={filter.sector_id} onChange={(e) => setFilter({ ...filter, sector_id: e.target.value })}>
        <option value="">Todos</option>{sectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <label className="at-field"><span className="at-field__label">Usuário</span><select className="select" value={filter.actor_id} onChange={(e) => setFilter({ ...filter, actor_id: e.target.value })}>
        <option value="">Todos</option>{users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
      </select></label>
      <TextField label="Ou ID de outro usuário" type="number" min="1" value={filter.actor_id} onChange={(e) => setFilter({ ...filter, actor_id: e.target.value })} />
      <TextField label="Ação" value={filter.action} onChange={(e) => setFilter({ ...filter, action: e.target.value })} />
      <TextField label="ID da reunião" value={filter.target_id} onChange={(e) => setFilter({ ...filter, target_id: e.target.value })} />
      <TextField label="De (AAAA-MM-DD)" type="date" value={filter.from_date} onChange={(e) => setFilter({ ...filter, from_date: e.target.value })} />
      <TextField label="Até (AAAA-MM-DD)" type="date" value={filter.to_date} onChange={(e) => setFilter({ ...filter, to_date: e.target.value })} />
      <Button type="submit" variant="primary">Filtrar</Button>
    </form>
    <p className="muted">Eventos de auditoria são mantidos por 90 dias; limpeza diária às 03h15 (horário de São Paulo). Exportação limitada a 10.000 eventos e registrada na auditoria.</p>
    <a className="btn" href={`/api/admin/audit/export/${exportQuery ? `?${exportQuery}` : ''}`}>Baixar auditoria JSONL</a>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Quando</th><th>Ator</th><th>Ação</th><th>Resultado</th><th>Origem (IP)</th><th>Alvo</th><th>Alterações</th></tr></thead>
      <tbody>{events.map((event) => <tr key={event.id}><td>{new Date(event.created_at).toLocaleString('pt-BR')}</td><td>{event.actor_name || (event.actor_id_snapshot ? `Usuário #${event.actor_id_snapshot}` : 'Não autenticado')}</td><td>{actionLabel(event.action)}</td><td>{outcomeLabel(event.outcome)}</td><td className="mono">{event.client_ip || 'Indisponível'}<br /><small>intermediário: {event.peer_ip || '—'}</small></td><td className="mono">{targetLabel(event.target_type)} {event.target_ref}</td><td>{event.details && Object.keys(event.details).length ? <details><summary>Ver campos e linhas</summary><pre className="mono">{JSON.stringify(event.details, null, 2)}</pre><small>Requisição: {event.request_id || '—'}</small></details> : '—'}</td></tr>)}</tbody></table></div>
    <div className="admin-actions"><Button disabled={page <= 1} onClick={() => load(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={!next} onClick={() => load(page + 1)}>Próxima</Button></div>
  </section>;
}
