import { useState } from 'react';
import { PageRedirect, usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';

export default function AdminLoginPage() {
  const { user, login, logout, ready } = useAuth();
  const navigate = usePageNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  if (!ready) return null;
  if (user?.is_staff) return <PageRedirect to="/admin/" />;

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(username.trim(), password);
      navigate('/admin', { replace: true });
    } catch {
      setError('Credenciais inválidas ou acesso administrativo indisponível.');
    } finally {
      setPassword('');
      setBusy(false);
    }
  }

  return <div className="login"><div className="login__card">
    <div className="login__brand"><h1 className="t-page">Scribrief</h1>
      <p className="muted">Administração — acesso em rede separada.</p></div>
    {user && !user.is_staff ? <><InlineNotice tone="erro">Sua conta não é administradora.</InlineNotice><Button onClick={() => logout()}>Sair desta conta</Button></> : null}
    <form className="login__form" onSubmit={submit}>
      <TextField label="Usuário" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
      <TextField label="Senha" value={password} onChange={(e) => setPassword(e.target.value)} type="password" autoComplete="current-password" required />
      {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
      <Button variant="primary" type="submit" disabled={busy || !username || !password}>Entrar</Button>
    </form>
  </div></div>;
}
