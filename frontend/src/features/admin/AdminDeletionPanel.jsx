import { useCallback, useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';

function dateTime(value) {
  return value ? new Date(value).toLocaleString('pt-BR') : '—';
}

export default function AdminDeletionPanel() {
  const [items, setItems] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [next, setNext] = useState(false);
  const [password, setPassword] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async (targetPage = 1) => {
    try {
      const data = await request('GET', '/api/admin/deletions/', { query: { page: targetPage } });
      setItems(data.results || []);
      setCount(data.count || 0);
      setPage(targetPage);
      setNext(Boolean(data.next));
      setError('');
    } catch (err) { setError(err.message); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function restore(item) {
    if (!password || !window.confirm(`Restaurar a reunião “${item.title}” e devolvê-la ao proprietário?`)) return;
    setBusyId(item.id); setError(''); setNotice('');
    try {
      await request('POST', `/api/admin/deletions/${item.id}/restore/`, {
        json: { current_password: password },
      });
      setNotice('Reunião restaurada. O proprietário poderá acessá-la novamente.');
      await load(1);
    } catch (err) { setError(err.message); }
    finally { setBusyId(null); setPassword(''); }
  }

  return <section className="admin-card admin-report">
    <div className="head"><h2 className="t-sec">Fila de exclusão · {count}</h2>
      <p className="muted">Reuniões ocultas por 72 horas. O administrador pode restaurar antes do prazo; depois, a purga automática remove dados e arquivos. Falhas são tentadas novamente.</p></div>
    <div className="admin-actions"><Button onClick={() => load(page)}>Atualizar fila</Button>
      <TextField label="Senha administrativa para restaurar" type="password" value={password}
        autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} /></div>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {notice ? <InlineNotice tone="sucesso">{notice}</InlineNotice> : null}
    <div className="admin-table-wrap"><table className="admin-table"><thead><tr>
      <th>Reunião</th><th>Dono / setor</th><th>Ocultada</th><th>Excluir definitivamente após</th><th>Purga</th><th>Ação</th>
    </tr></thead><tbody>{items.map((item) => {
      const expired = Date.now() >= new Date(item.deletion_due_at).getTime();
      return <tr key={item.id}>
        <td><strong>{item.title}</strong><br /><small className="mono">{item.id}</small></td>
        <td>{item.owner_name}<br /><small>{item.sector_name}</small></td>
        <td>{dateTime(item.deletion_requested_at)}</td>
        <td>{dateTime(item.deletion_due_at)}{expired ? <strong> · prazo encerrado</strong> : null}</td>
        <td>{item.purge_error_code ? `Falhou (${item.purge_error_code}); tentativas: ${item.purge_attempts}` : 'Aguardando prazo'}</td>
        <td><Button disabled={expired || !password || busyId === item.id} onClick={() => restore(item)}>Restaurar</Button></td>
      </tr>;
    })}</tbody></table></div>
    {!items.length ? <p className="muted">Nenhuma reunião na fila.</p> : null}
    <div className="admin-actions"><Button disabled={page <= 1} onClick={() => load(page - 1)}>Anterior</Button>
      <span>Página {page}</span><Button disabled={!next} onClick={() => load(page + 1)}>Próxima</Button></div>
  </section>;
}
