import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { jobLabel } from './adminLabels.js';

function hours(seconds) {
  return seconds == null ? '—' : `${(Number(seconds) / 3600).toFixed(2)} h`;
}

export default function AdminJobsPanel({ sectors, users }) {
  const [filter, setFilter] = useState({ sector_id: '', user_id: '', status: '' });
  const [summary, setSummary] = useState(null);
  const [workerHealth, setWorkerHealth] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [page, setPage] = useState(1);
  const [next, setNext] = useState(false);
  const [password, setPassword] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function load(targetPage = 1, selected = filter) {
    setError('');
    try {
      const [overview, list, health] = await Promise.all([
        request('GET', '/api/admin/jobs/summary/', { query: selected }),
        request('GET', '/api/admin/jobs/', { query: { ...selected, page: targetPage } }),
        request('GET', '/api/admin/jobs/worker-health/'),
      ]);
      setSummary(overview); setJobs(list.results || []); setPage(targetPage); setNext(Boolean(list.next)); setWorkerHealth(health);
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { load(1, { sector_id: '', user_id: '', status: '' }); }, []);

  async function cancel(job) {
    if (!password || !window.confirm(`Cancelar a execução ${job.id}? A chamada externa já em andamento pode terminar e ser faturada.`)) return;
    setBusyId(job.id); setError(''); setNotice('');
    try {
      await request('POST', `/api/admin/jobs/${job.id}/cancel/`, { json: { current_password: password } });
      setNotice('Cancelamento solicitado. O resultado desta execução não será publicado.');
      await load(page);
    } catch (err) { setError(err.message); }
    finally { setPassword(''); setBusyId(null); }
  }

  return <section className="admin-card admin-report">
    <div className="head"><h2 className="t-sec">Execuções</h2><p className="muted">Cancelamento cooperativo: não encerra o processador compartilhado nem interrompe imediatamente uma chamada OpenAI em curso.</p></div>
    <form className="admin-filters" onSubmit={(event) => { event.preventDefault(); load(1); }}>
      <label className="at-field"><span className="at-field__label">Setor</span><select className="select" value={filter.sector_id} onChange={(e) => setFilter({ ...filter, sector_id: e.target.value })}><option value="">Todos</option>{sectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
      <label className="at-field"><span className="at-field__label">Usuário</span><select className="select" value={filter.user_id} onChange={(e) => setFilter({ ...filter, user_id: e.target.value })}><option value="">Todos</option>{users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}</select></label>
      <TextField label="Ou ID de outro usuário" type="number" min="1" value={filter.user_id} onChange={(e) => setFilter({ ...filter, user_id: e.target.value })} />
      <label className="at-field"><span className="at-field__label">Estado</span><select className="select" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}><option value="">Todos</option><option value="queued">Na fila</option><option value="running">Em execução</option><option value="completed">Concluído</option><option value="failed">Falhou</option><option value="cancelled">Cancelado</option></select></label>
      <Button type="submit" variant="primary">Filtrar</Button><Button onClick={() => load(page)}>Atualizar</Button>
    </form>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {notice ? <InlineNotice tone="sucesso">{notice}</InlineNotice> : null}
    {summary ? <><div className="admin-stats"><div><strong>{summary.totals.requests}</strong><span>solicitações</span></div><div><strong>{summary.totals.running}</strong><span>em execução</span></div><div><strong>{summary.totals.failed}</strong><span>falhas</span></div><div><strong>{hours(summary.totals.uploaded_media_seconds)}</strong><span>mídia enviada</span></div></div>
      <p className="muted">Processadores de tarefas respondendo: {workerHealth?.status === 'responding' ? workerHealth.responding_workers : 'sem resposta / indisponível'} (sondagem pontual; não prova que cada tarefa progride).</p>
      <div className="admin-grid"><div><h3 className="t-sub">Por usuário</h3><ul className="admin-list">{summary.by_user.map((item) => <li key={item.requested_by_id}><span>{item.requested_by__username || 'Conta removida'} · {item.requests} solicitações</span><strong>{hours(item.uploaded_media_seconds)}</strong></li>)}</ul></div><div><h3 className="t-sub">Por setor</h3><ul className="admin-list">{summary.by_sector.map((item) => <li key={item.sector_id}><span>{item.sector__name} · {item.requests} solicitações</span><strong>{hours(item.uploaded_media_seconds)}</strong></li>)}</ul></div></div></> : null}
    <div className="admin-actions"><TextField label="Senha de administrador para cancelar" type="password" value={password} autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} /></div>
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Recebido</th><th>Usuário / setor</th><th>Tipo / reunião</th><th>Estado / progresso</th><th>Mídia</th><th>Ação</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}>
      <td>{new Date(job.queued_at).toLocaleString('pt-BR')}</td><td>{job.username || 'Conta removida'}<br /><small>{job.sector_name}</small></td><td>{jobLabel(job.kind)}<br /><small className="mono">{job.meeting_id}</small></td><td>{jobLabel(job.status)}{job.potentially_stalled ? <strong> · Possivelmente travado</strong> : null}<br /><small>{job.stage ? jobLabel(job.stage) : 'Aguardando'} {job.total_units ? `${job.completed_units}/${job.total_units}` : ''}</small></td><td>{hours(job.media_duration_seconds)}</td><td>{['queued', 'running'].includes(job.status) ? <Button variant="destructive" disabled={!password || busyId === job.id} onClick={() => cancel(job)}>Cancelar</Button> : '—'}</td>
    </tr>)}</tbody></table></div>
    <div className="admin-actions"><Button disabled={page <= 1} onClick={() => load(page - 1)}>Anterior</Button><span>Página {page}</span><Button disabled={!next} onClick={() => load(page + 1)}>Próxima</Button></div>
  </section>;
}
