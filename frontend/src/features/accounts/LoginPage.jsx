import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { PageRedirect, usePageNavigate } from '../../shared/lib/pageNavigation.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';

export default function LoginPage() {
  const { user, login } = useAuth();
  const nav = usePageNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  if (user) return <PageRedirect to={user.must_change_password ? (user.is_staff ? '/admin/' : '/primeiro-acesso/') : '/'} />;

  async function submit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const signedIn = await login(email.trim(), password);
      nav(signedIn?.must_change_password
        ? (signedIn.is_staff ? '/admin/' : '/primeiro-acesso/')
        : (document.getElementById('root')?.dataset.next || loc.state?.from || '/'), { replace: true });
    } catch (err) {
      // Mensagem genérica: não revela se o erro foi no e-mail ou na senha.
      setError(err.status === 0 ? 'Não foi possível conectar ao servidor. Tente novamente.' : 'E-mail ou senha incorretos.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__brand">
          <h1 className="t-page">Scribrief</h1>
          <p className="muted" style={{ margin: 0 }}>Transcrição e ata das suas reuniões.</p>
        </div>
        <form className="login__form" onSubmit={submit} noValidate>
          <TextField id="login-email" label="Usuário" type="text" autoComplete="username" value={email} onChange={(e) => { setEmail(e.target.value); setError(''); }} />
          <TextField id="login-senha" label="Senha" type="password" autoComplete="current-password" value={password} onChange={(e) => { setPassword(e.target.value); setError(''); }} />
          {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
          <Button variant="primary" type="submit" disabled={busy || !email || !password}>{busy ? 'Entrando…' : 'Entrar'}</Button>
        </form>
      </div>
    </div>
  );
}
