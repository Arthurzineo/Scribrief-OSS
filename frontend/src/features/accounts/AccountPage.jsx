import { useState } from 'react';
import { Button, TextField } from '../../shared/components/index.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';
import { useToast } from '../../shared/context/ToastContext.jsx';
import { changePassword, updateMe } from '../../api/auth.js';
import { applyTheme, effectiveTheme, readTheme } from '../../shared/lib/theme.js';

export default function AccountPage() {
  const { user, setUser, logout } = useAuth();
  const say = useToast();
  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [cur, setCur] = useState('');
  const [nw, setNw] = useState('');
  const [pwErr, setPwErr] = useState('');
  const [theme, setThemeState] = useState(readTheme());
  const eff = effectiveTheme(theme);

  const setTheme = (t) => { setThemeState(t); applyTheme(t); };

  async function saveData() {
    try { const u = await updateMe({ name: name.trim(), email: email.trim() }); setUser(u || { ...user, name, email }); say('Dados salvos'); }
    catch (e) { say(`Não foi possível salvar. ${e.message}`); }
  }
  async function savePassword() {
    if (!cur) { setPwErr('Informe a senha atual.'); return; }
    if (nw.length < 12) { setPwErr('Use pelo menos 12 caracteres.'); return; }
    try { await changePassword(cur, nw); setCur(''); setNw(''); say('Senha alterada'); }
    catch (e) { setPwErr(e.status === 400 || e.status === 403 ? 'Senha atual incorreta.' : `Não foi possível alterar a senha. ${e.message}`); }
  }

  return (
    <div className="page page--narrow">
      <h1 className="t-page">Conta</h1>
      <div className="acct">
        <section>
          <h2 className="t-sub">Dados</h2>
          <TextField id="conta-nome" label="Nome" value={name} onChange={(e) => setName(e.target.value)} />
          <TextField id="conta-email" label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <div><Button onClick={saveData}>Salvar</Button></div>
        </section>
        <section>
          <h2 className="t-sub">Senha</h2>
          <TextField id="conta-senha" label="Senha atual" type="password" autoComplete="current-password" value={cur} onChange={(e) => { setCur(e.target.value); setPwErr(''); }} />
          <TextField id="conta-nova" label="Nova senha" type="password" autoComplete="new-password" value={nw} hint={pwErr ? undefined : 'Pelo menos 12 caracteres.'} error={pwErr || undefined} onChange={(e) => { setNw(e.target.value); setPwErr(''); }} />
          <div><Button onClick={savePassword}>Alterar senha</Button></div>
        </section>
        <section>
          <h2 className="t-sub">Tema</h2>
          <div className="seg" role="group" aria-label="Tema">
            <button type="button" aria-pressed={eff === 'light'} onClick={() => setTheme('light')}>Claro</button>
            <button type="button" aria-pressed={eff === 'dark'} onClick={() => setTheme('dark')}>Escuro</button>
          </div>
        </section>
        <div><Button variant="destructive" onClick={() => logout().finally(() => { window.location.href = '/login/'; })}>Sair</Button></div>
      </div>
    </div>
  );
}
