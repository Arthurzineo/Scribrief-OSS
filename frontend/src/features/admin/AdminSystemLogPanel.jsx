import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { actionLabel, componentLabel, jobLabel, outcomeLabel, severityLabel } from './adminLabels.js';

const emptyFilter = { event_code: '', error_code: '', job_id: '', meeting_id: '', from_date: '', to_date: '' };

export default function AdminSystemLogPanel() {
  const [filter, setFilter] = useState(emptyFilter);
  const [events, setEvents] = useState([]);
  const [page, setPage] = useState(1);
  const [next, setNext] = useState(false);
  const [error, setError] = useState('');

  async function load(targetPage = 1, selected = filter) {
    setError('');
    try {
      const data = await request('GET', '/api/admin/system-events/', { query: { ...selected, page: targetPage } });
      setEvents(data.results || []);
      setPage(targetPage);
      setNext(Boolean(data.next));
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { load(1, emptyFilter); }, []);
  return <section className="admin-card admin-report"><h2 className="t-sec">Registros do sistema e tarefas</h2>
    <form className="admin-filters" onSubmit={(event) => { event.preventDefault(); load(1); }}>
      <TextField label="Evento" value={filter.event_code} onChange={(e) => setFilter({ ...filter, event_code: e.target.value })} />
      <TextField label="Código de erro" value={filter.error_code} onChange={(e) => setFilter({ ...filter, error_code: e.target.value })} />
      <TextField label="ID da tarefa" value={filter.job_id} onChange={(e) => setFilter({ ...filter, job_id: e.target.value })} />
      <TextField label="ID da reunião" value={filter.meeting_id} onChange={(e) => setFilter({ ...filter, meeting_id: e.target.value })} />
      <TextField label="De" type="date" value={filter.from_date} onChange={(e) => setFilter({ ...filter, from_date: e.target.value })} />
      <TextField label="Até" type="date" value={filter.to_date} onChange={(e) => setFilter({ ...filter, to_date: e.target.value })} />
      <Button type="submit" variant="primary">Filtrar</Button>
    </form>
    <p className="muted">Eventos técnicos sem conteúdo de áudio, transcrição ou chaves. Retenção ativa: 90 dias. Uma falha no banco pode impedir a gravação do evento; o console é contingência, não arquivo permanente.</p>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Quando</th><th>Componente</th><th>Evento</th><th>Resultado</th><th>Conta/IP</th><th>Tarefa/reunião</th><th>Fase/erro</th><th>Requisição</th></tr></thead>
      <tbody>{events.map((event) => <tr key={event.id}>
        <td>{new Date(event.created_at).toLocaleString('pt-BR')}</td>
        <td>{componentLabel(event.component)}</td><td>{actionLabel(event.event_code)} · {severityLabel(event.severity)}</td>
        <td>{event.outcome ? outcomeLabel(event.outcome) : '—'}</td>
        <td>{event.user_name || (event.user_id_snapshot ? `Usuário #${event.user_id_snapshot}` : '—')}<br /><small className="mono">{event.client_ip || '—'}</small></td>
        <td className="mono">{event.job_id || '—'}<br />{event.meeting_id || '—'}</td>
        <td>{event.stage ? jobLabel(event.stage) : '—'}<br />{event.error_code ? 'Erro técnico registrado' : '—'}</td>
        <td className="mono">{event.request_id || '—'}</td>
      </tr>)}</tbody></table></div>
    <div className="admin-actions"><Button disabled={page <= 1} onClick={() => load(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={!next} onClick={() => load(page + 1)}>Próxima</Button></div>
  </section>;
}
