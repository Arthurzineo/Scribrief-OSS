import { useState } from 'react';
import { changePassword, getMe } from '../../api/auth.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';

export default function InitialPasswordPanel() {
  const { setUser, logout } = useAuth();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (next !== confirm) { setError('A confirmação não corresponde à nova senha.'); return; }
    setBusy(true); setError('');
    try {
      await changePassword(current, next);
      setUser(await getMe());
    } catch (err) { setError(err.message); }
    finally { setCurrent(''); setNext(''); setConfirm(''); setBusy(false); }
  }

  return <div className="login"><div className="login__card">
    <div className="login__brand"><h1 className="t-page">Primeiro acesso</h1>
      <p className="muted">Por segurança, troque a senha inicial antes de usar o Scribrief ou liberar acesso pela rede.</p></div>
    <form className="login__form" onSubmit={submit}>
      <TextField label="Senha inicial" type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
      <TextField label="Nova senha" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required minLength={12} hint="Use pelo menos 12 caracteres e não reutilize a senha inicial." />
      <TextField label="Confirme a nova senha" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={12} />
      {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
      <Button variant="primary" type="submit" disabled={busy || !current || !next || !confirm}>{busy ? 'Alterando…' : 'Alterar senha e continuar'}</Button>
    </form>
    <Button onClick={() => logout().finally(() => { window.location.href = '/admin/login/'; })}>Sair</Button>
  </div></div>;
}
