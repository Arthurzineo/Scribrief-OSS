import { useCallback, useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice } from '../../shared/components/index.js';
import { componentLabel } from './adminLabels.js';

const labels = {
  backend: 'Servidor da aplicação', database: 'Banco de dados (PostgreSQL)', redis: 'Fila (Redis)',
  worker: 'Processador de tarefas (Celery)', frontend: 'Interface', storage: 'Volume de mídia',
  sampling: 'Agendador/coleta (indireto)',
};
const statusLabel = { ok: 'Respondendo', down: 'Sem resposta', unknown: 'Indisponível' };
const number = (value) => value == null ? 'Indisponível' : Number(value).toLocaleString('pt-BR');
const usd = (value) => value == null ? 'Indisponível' : `US$ ${Number(value).toFixed(8)}`;
const gib = (value) => value == null ? 'Indisponível' : `${(Number(value) / 1073741824).toFixed(2)} GiB`;

export default function AdminHealthPanel() {
  const [health, setHealth] = useState(null);
  const [usage, setUsage] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const [healthData, usageData] = await Promise.all([
        request('GET', '/api/admin/health/'),
        request('GET', '/api/admin/usage/summary/'),
      ]);
      setHealth(healthData); setUsage(usageData);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return <section className="admin-card admin-report">
    <div className="head"><div><h2 className="t-sec">Saúde da instalação</h2>
      <p className="muted">Sondagem atual e amostras periódicas. Esta instalação tem setores, não organizações independentes.</p></div>
      <Button onClick={load} disabled={busy}>{busy ? 'Verificando…' : 'Atualizar'}</Button></div>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {health ? <>
      <p className="muted">Última sondagem: {new Date(health.checked_at).toLocaleString('pt-BR')} · Última amostra: {health.latest_sample_at ? new Date(health.latest_sample_at).toLocaleString('pt-BR') : 'ainda não disponível'}</p>
      <div className="admin-stats">{Object.entries(labels).map(([key, label]) => <div key={key}>
        <strong>{statusLabel[health.services[key]] || 'Indisponível'}</strong><span>{label}</span>
      </div>)}</div>
      <h3 className="t-sub">Disponibilidade observada nas últimas 24 horas</h3>
      <p className="muted">Cada amostra representa 5 minutos. Lacunas são desconhecidas, não tempo on-line nem queda. “Agendador/coleta” indica apenas amostra recente; não prova qual processo parou. Para um acordo formal de disponibilidade, é necessário monitor externo.</p>
      <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Serviço</th><th>On-line observado</th><th>Tempo observado</th><th>Cobertura</th></tr></thead>
        <tbody>{Object.entries(health.availability_24h).map(([key, item]) => <tr key={key}><td>{labels[key]}</td><td>{item.online_minutes_observed} min</td><td>{item.minutes_observed} min</td><td>{item.sample_count}/{item.expected_sample_count} amostras</td></tr>)}</tbody>
      </table></div>
      <h3 className="t-sub">Espaço de armazenamento da mídia</h3>
      <p className="muted">Capacidade e uso do volume onde ficam os arquivos privados; não é o tamanho exclusivo dos arquivos de reunião.</p>
      <div className="admin-stats"><div><strong>{gib(health.disk.total_bytes)}</strong><span>capacidade</span></div><div><strong>{gib(health.disk.used_bytes)}</strong><span>ocupado</span></div><div><strong>{gib(health.disk.free_bytes)}</strong><span>livre</span></div></div>
      <h3 className="t-sub">Falhas nas últimas 24 horas</h3>
      <p className="muted">Contadores distintos; uma tarefa pode também gerar evento técnico e chamada OpenAI falha.</p>
      <div className="admin-stats"><div><strong>{number(health.errors_24h.system_events)}</strong><span>eventos técnicos de erro</span></div><div><strong>{number(health.errors_24h.failed_jobs)}</strong><span>tarefas falhas</span></div><div><strong>{number(health.errors_24h.failed_openai_attempts)}</strong><span>tentativas OpenAI falhas</span></div><div><strong>{number(health.jobs_24h.submitted)}</strong><span>tarefas enviadas em 24h</span></div><div><strong>{number(health.jobs_24h.queued)}</strong><span>tarefas na fila agora</span></div><div><strong>{number(health.jobs_24h.running)}</strong><span>tarefas em execução agora</span></div></div>
      {health.errors_24h.by_component.length ? <ul className="admin-list">{health.errors_24h.by_component.map((item) => <li key={item.component}><span>{componentLabel(item.component)}</span><strong>{item.count}</strong></li>)}</ul> : null}
    </> : null}
    {usage ? <><h3 className="t-sub">Uso e custos — histórico da instalação</h3>
      <p className="muted">Tokens apenas quando informados pelo provedor. Custo em USD é estimativa, não fatura; chamadas sem estimativa não estão incluídas no valor.</p>
      <div className="admin-stats"><div><strong>{number(usage.totals.total_tokens)}</strong><span>tokens medidos ({number(usage.totals.token_calls)}/{number(usage.totals.calls)} chamadas)</span></div><div><strong>{number(usage.totals.input_tokens)}</strong><span>tokens de entrada</span></div><div><strong>{number(usage.totals.output_tokens)}</strong><span>tokens de saída</span></div><div><strong>{usd(usage.totals.estimated_total_usd)}</strong><span>custo estimado</span></div><div><strong>{number(usage.totals.unavailable)}</strong><span>chamadas sem estimativa</span></div></div>
      <div className="admin-grid"><div><h4 className="t-sub">Por setor</h4><ul className="admin-list">{usage.by_sector.map((item) => <li key={item.sector_id}><span>{item.sector__name} · {number(item.total_tokens)} tokens medidos</span><strong>{usd(item.estimated_total_usd)}</strong></li>)}</ul></div>
        <div><h4 className="t-sub">Por usuário</h4><ul className="admin-list">{usage.by_user.map((item) => <li key={item.requested_by_id || 'deleted'}><span>{item.requested_by__username || 'Conta removida'} · {number(item.total_tokens)} tokens medidos</span><strong>{usd(item.estimated_total_usd)}</strong></li>)}</ul></div></div>
      <p className="muted">Detalhes por reunião/ata e filtros estão em “Custos e uso”. A tabela detalhada é limitada aos primeiros 1.000 usuários/setores.</p>
    </> : null}
  </section>;
}
