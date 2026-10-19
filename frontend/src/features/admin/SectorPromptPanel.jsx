import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, TextField } from '../../shared/components/index.js';

export default function SectorPromptPanel({ sectorId }) {
  const [items, setItems] = useState([]);
  const [kind, setKind] = useState('minutes');
  const [draft, setDraft] = useState('');
  const [password, setPassword] = useState('');
  const [note, setNote] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const selected = items.find((item) => item.kind === kind);

  useEffect(() => {
    let active = true;
    request('GET', `/api/admin/sectors/${sectorId}/ai-prompts/`)
      .then((data) => {
        if (!active) return;
        setItems(data.prompts || []);
        setNote(data.transcription_note || '');
        setMessage('');
      })
      .catch((error) => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, [sectorId]);

  useEffect(() => { setDraft(selected?.text || ''); setPassword(''); }, [selected?.text, kind]);

  async function changePrompt(method) {
    if (!selected || !password || busy) return;
    if (method === 'DELETE' && !window.confirm(`Restaurar as instruções padrão de ${selected.label}?`)) return;
    setBusy(true); setMessage('');
    try {
      const result = await request(method, `/api/admin/sectors/${sectorId}/ai-prompts/${kind}/`, {
        json: { text: draft, expected_version: selected.version, current_password: password },
      });
      setItems((current) => current.map((item) => item.kind === kind ? result : item));
      setDraft(result.text);
      setPassword('');
      setMessage(method === 'DELETE' ? 'Instruções padrão restauradas.' : 'Instruções do setor salvas.');
    } catch (error) { setMessage(error.message); }
    finally { setBusy(false); }
  }

  return <div className="admin-form admin-key">
    <h3 className="t-sub">Instruções da IA do setor</h3>
    <p className="muted">Textos usados pela IA nas próximas execuções deste setor. Não inclua chaves ou dados sigilosos. A validação dos resultados permanece no sistema.</p>
    <p className="muted">{note}</p>
    <label className="at-field"><span className="at-field__label">Operação</span><select className="select" value={kind} onChange={(event) => setKind(event.target.value)}>
      {items.map((item) => <option key={item.kind} value={item.kind}>{item.label}</option>)}
    </select></label>
    {selected ? <>
      <p className="muted">{selected.source === 'default' ? 'Padrão do sistema' : `Personalizado · versão ${selected.version}`}</p>
      <TextField label="Instruções enviadas à IA" multiline rows={12} maxLength={8000} value={draft} onChange={(event) => setDraft(event.target.value)} />
      <TextField label="Confirme sua senha de administrador" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
      <div className="admin-actions"><Button onClick={() => changePrompt('PUT')} variant="primary" disabled={busy || !password || draft.trim().length < 20 || draft === selected.text}>Salvar instruções</Button>
        {selected.source === 'custom' ? <Button onClick={() => changePrompt('DELETE')} variant="destructive" disabled={busy || !password}>Restaurar padrão</Button> : null}</div>
    </> : null}
    {message ? <p role="status">{message}</p> : null}
  </div>;
}
