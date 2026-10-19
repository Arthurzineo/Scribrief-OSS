import { useCallback, useEffect, useRef, useState } from 'react';
import { PageRedirect } from '../../shared/lib/pageNavigation.js';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';
import { useAuth } from '../../shared/context/AuthContext.jsx';
import AdminUsagePanel from './AdminUsagePanel.jsx';
import AdminAuditPanel from './AdminAuditPanel.jsx';
import AdminSystemLogPanel from './AdminSystemLogPanel.jsx';
import AdminJobsPanel from './AdminJobsPanel.jsx';
import AdminDeletionPanel from './AdminDeletionPanel.jsx';
import AdminHealthPanel from './AdminHealthPanel.jsx';
import SectorPromptPanel from './SectorPromptPanel.jsx';
import AdminTlsPanel from './AdminTlsPanel.jsx';
import InitialPasswordPanel from './InitialPasswordPanel.jsx';

const emptySector = { name: '', slug: '', is_active: true, max_upload_minutes: '', max_monthly_minutes_per_user: '' };
const emptyUser = { username: '', first_name: '', last_name: '', email: '', sector_id: '', password: '' };

export default function AdminPage() {
  const { user, ready, logout } = useAuth();
  const [tab, setTab] = useState('sectors');
  const [sectors, setSectors] = useState([]);
  const [sectorChoices, setSectorChoices] = useState([]);
  const [users, setUsers] = useState([]);
  const [sectorForm, setSectorForm] = useState(emptySector);
  const [userForm, setUserForm] = useState(emptyUser);
  const [selectedSector, setSelectedSector] = useState(null);
  const [selectedAiSector, setSelectedAiSector] = useState(null);
  const [aiSection, setAiSection] = useState('key');
  const [aiLoading, setAiLoading] = useState(false);
  const aiLoadSequence = useRef(0);
  const [members, setMembers] = useState([]);
  const [userPage, setUserPage] = useState(1);
  const [sectorPage, setSectorPage] = useState(1);
  const [memberPage, setMemberPage] = useState(1);
  const [userNext, setUserNext] = useState(false);
  const [sectorNext, setSectorNext] = useState(false);
  const [memberNext, setMemberNext] = useState(false);
  const [memberPeriod, setMemberPeriod] = useState('');
  const [keyStatus, setKeyStatus] = useState(null);
  const [aiProviders, setAiProviders] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState('openai');
  const [keyDraft, setKeyDraft] = useState('');
  const [reauthPassword, setReauthPassword] = useState('');
  const [keyBusy, setKeyBusy] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ currentPassword: '', newPassword: '' });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [sectorData, userData, choices] = await Promise.all([
      request('GET', '/api/admin/sectors/'),
      request('GET', '/api/admin/users/'),
      request('GET', '/api/admin/sectors/choices/'),
    ]);
    setSectors(sectorData.results || []);
    setUsers(userData.results || []);
    setSectorChoices(choices || []);
    setSectorPage(1); setUserPage(1);
    setSectorNext(Boolean(sectorData.next)); setUserNext(Boolean(userData.next));
  }, []);

  async function loadPage(kind, page) {
    try {
      const data = await request('GET', `/api/admin/${kind}/`, { query: { page } });
      if (kind === 'users') { setUsers(data.results || []); setUserPage(page); setUserNext(Boolean(data.next)); }
      else { setSectors(data.results || []); setSectorPage(page); setSectorNext(Boolean(data.next)); }
    } catch (err) { setError(err.message); }
  }

  useEffect(() => { if (user?.is_staff && !user.must_change_password) refresh().catch((err) => setError(err.message)); }, [refresh, user?.is_staff, user?.must_change_password]);
  if (!ready) return null;
  if (!user) return <PageRedirect to="/admin/login/" />;
  if (!user.is_staff) return <main className="page"><h1 className="t-page">Acesso negado</h1><p>Conta sem permissão administrativa.</p></main>;
  if (user.must_change_password) return <InitialPasswordPanel />;

  async function saveSector(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const method = sectorForm.id ? 'PATCH' : 'POST';
      const path = sectorForm.id ? `/api/admin/sectors/${sectorForm.id}/` : '/api/admin/sectors/';
      const saved = await request(method, path, { json: {
        ...sectorForm,
        max_upload_minutes: sectorForm.max_upload_minutes === ''
          ? null : Number(sectorForm.max_upload_minutes),
        max_monthly_minutes_per_user: sectorForm.max_monthly_minutes_per_user === ''
          ? null : Number(sectorForm.max_monthly_minutes_per_user),
      } });
      if (selectedSector?.id === saved.id) setSelectedSector(saved);
      if (selectedAiSector?.id === saved.id) setSelectedAiSector(saved);
      setSectorForm(emptySector); setNotice('Setor salvo.'); await refresh();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  async function saveUser(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const method = userForm.id ? 'PATCH' : 'POST';
      const path = userForm.id ? `/api/admin/users/${userForm.id}/` : '/api/admin/users/';
      const payload = { ...userForm, sector_id: Number(userForm.sector_id) };
      if (!payload.password) delete payload.password;
      await request(method, path, { json: payload });
      setUserForm(emptyUser); setNotice('Usuário salvo.'); await refresh();
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  async function toggleUser(item) {
    if (!window.confirm(`${item.is_active ? 'Desativar' : 'Ativar'} ${item.username}?`)) return;
    try {
      await request('PATCH', `/api/admin/users/${item.id}/`, { json: { is_active: !item.is_active } });
      await refresh();
    } catch (err) { setError(err.message); }
  }

  async function showMembers(sector, page = 1) {
    setSelectedSector(sector); setError('');
    try {
      const data = await request('GET', `/api/admin/sectors/${sector.id}/members/`, { query: { page } });
      setMembers(data.results || []);
      setMemberPeriod(data.monthly_period || '');
      setMemberPage(page); setMemberNext(Boolean(data.next));
    } catch (err) { setError(err.message); }
  }

  async function showSectorAI(sector, providerId = 'openai') {
    const sequence = ++aiLoadSequence.current;
    setSelectedAiSector(sector); setSelectedProvider(providerId); setTab('ai');
    setAiSection('key'); setKeyStatus(null); setAiLoading(true); setError('');
    setKeyDraft(''); setReauthPassword('');
    try {
      const [key, catalog] = await Promise.all([
        request('GET', `/api/admin/sectors/${sector.id}/ai-credentials/${providerId}/`),
        request('GET', '/api/admin/ai-providers/'),
      ]);
      if (sequence !== aiLoadSequence.current) return;
      setKeyStatus(key); setAiProviders(catalog.providers || []);
    } catch (err) { if (sequence === aiLoadSequence.current) setError(err.message); }
    finally { if (sequence === aiLoadSequence.current) setAiLoading(false); }
  }

  async function saveKey(event) {
    event.preventDefault();
    setKeyBusy(true); setError(''); setNotice('');
    try {
      const result = await request('POST', `/api/admin/sectors/${selectedAiSector.id}/ai-credentials/${selectedProvider}/`, {
        json: { api_key: keyDraft, current_password: reauthPassword },
      });
      setKeyStatus(result); setNotice('Credencial setorial salva. O valor não será mostrado novamente.');
    } catch (err) { setError(err.message); }
    finally { setKeyDraft(''); setReauthPassword(''); setKeyBusy(false); }
  }

  async function revokeKey() {
    if (!window.confirm(`Revogar a credencial ${selectedProvider} impedirá operações que usam esse provedor neste setor. Continuar?`)) return;
    setKeyBusy(true); setError('');
    try {
      await request('DELETE', `/api/admin/sectors/${selectedAiSector.id}/ai-credentials/${selectedProvider}/`, {
        json: { current_password: reauthPassword },
      });
      setKeyStatus({ configured: false }); setNotice('Credencial setorial revogada.');
    } catch (err) { setError(err.message); }
    finally { setKeyDraft(''); setReauthPassword(''); setKeyBusy(false); }
  }

  async function changeAdminPassword(event) {
    event.preventDefault(); setError(''); setNotice('');
    try {
      await request('POST', '/api/v1/account/password/', { json: passwordForm });
      setPasswordForm({ currentPassword: '', newPassword: '' });
      setNotice('Senha administrativa alterada.');
    } catch (err) { setError(err.message); }
  }

  return <div className="admin-shell"><header className="admin-head">
    <div><strong>Scribrief</strong><span>Administração</span></div>
    <div className="admin-head__right"><span>{user.name}</span><Button onClick={() => logout().finally(() => { window.location.href = '/admin/login'; })}>Sair</Button></div>
  </header><main className="page">
    <div className="head"><div><h1 className="t-page">Administração</h1><p className="muted">Setores e contas locais. LDAP será integrado posteriormente.</p></div></div>
    <div className="at-tabs" role="tablist" aria-label="Áreas administrativas">
      <button className={`at-tab ${tab === 'sectors' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'sectors'} onClick={() => setTab('sectors')}>Setores</button>
      <button className={`at-tab ${tab === 'ai' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'ai'} onClick={() => setTab('ai')}>IA por setor</button>
      <button className={`at-tab ${tab === 'users' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'users'} onClick={() => setTab('users')}>Usuários</button>
      <button className={`at-tab ${tab === 'usage' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'usage'} onClick={() => setTab('usage')}>Custos e uso</button>
      <button className={`at-tab ${tab === 'health' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'health'} onClick={() => setTab('health')}>Saúde do sistema</button>
      <button className={`at-tab ${tab === 'jobs' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'jobs'} onClick={() => setTab('jobs')}>Execuções</button>
      <button className={`at-tab ${tab === 'deletions' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'deletions'} onClick={() => setTab('deletions')}>Fila de exclusão</button>
      <button className={`at-tab ${tab === 'audit' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'audit'} onClick={() => setTab('audit')}>Auditoria</button>
      <button className={`at-tab ${tab === 'system' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'system'} onClick={() => setTab('system')}>Registros do sistema</button>
      <button className={`at-tab ${tab === 'security' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'security'} onClick={() => setTab('security')}>Minha senha</button>
      <button className={`at-tab ${tab === 'tls' ? 'at-tab--active' : ''}`} role="tab" aria-selected={tab === 'tls'} onClick={() => setTab('tls')}>Certificado HTTPS</button>
    </div>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {notice ? <InlineNotice tone="sucesso">{notice}</InlineNotice> : null}
    {tab === 'usage' ? <AdminUsagePanel sectors={sectorChoices} users={users} /> : null}
    {tab === 'health' ? <AdminHealthPanel /> : null}
    {tab === 'jobs' ? <AdminJobsPanel sectors={sectorChoices} users={users} /> : null}
    {tab === 'deletions' ? <AdminDeletionPanel /> : null}
    {tab === 'audit' ? <AdminAuditPanel sectors={sectorChoices} users={users} /> : null}
    {tab === 'system' ? <AdminSystemLogPanel /> : null}
    {tab === 'tls' ? <AdminTlsPanel /> : null}
    {tab === 'ai' ? <section className="admin-card admin-form admin-ai-config">
      <h2 className="t-sec">Configuração de IA por setor</h2>
      <p className="muted">Escolha um setor para configurar sua chave de API e as instruções da IA usadas nas próximas execuções. As configurações de um setor não afetam os demais.</p>
      <label className="at-field"><span className="at-field__label">Setor para configurar</span><select className="select" value={selectedAiSector?.id || ''} disabled={keyBusy} onChange={(e) => {
        const sector = sectorChoices.find((item) => String(item.id) === e.target.value);
        if (sector) showSectorAI(sector);
      }}><option value="">Selecione um setor</option>{sectorChoices.map((sector) => <option key={sector.id} value={sector.id}>{sector.name}</option>)}</select></label>
      {selectedAiSector ? <>
        <div className="admin-actions" aria-label="Configurações de IA"><Button variant={aiSection === 'key' ? 'primary' : undefined} onClick={() => setAiSection('key')}>Chave de API</Button><Button variant={aiSection === 'prompts' ? 'primary' : undefined} onClick={() => setAiSection('prompts')}>Instruções da IA</Button></div>
        {aiSection === 'key' ? <form className="admin-form admin-key" onSubmit={saveKey} autoComplete="off">
          <h3 className="t-sub">Credencial de IA do setor</h3>
          <label className="at-field"><span className="at-field__label">Provedor</span><select className="select" value={selectedProvider} disabled={aiLoading} onChange={(e) => showSectorAI(selectedAiSector, e.target.value)}>
            {aiProviders.map((provider) => <option key={provider.id} value={provider.id}>{provider.id}</option>)}
          </select></label>
          <p className="muted">Seleção das operações por configuração do servidor. Consulte o provedor selecionado para conhecer as funções disponíveis.</p>
          <p className="muted">{aiLoading ? 'Verificando a chave...' : keyStatus === null ? 'Estado indisponível' : keyStatus.configured ? `Configurada · versão ${keyStatus.version}` : 'Não configurada'}; o valor nunca é exibido.</p>
          <TextField label="Nova credencial" type="password" value={keyDraft} required minLength={selectedProvider === 'openai' ? 20 : 8} autoComplete="off" onChange={(e) => setKeyDraft(e.target.value)} />
          <TextField label="Confirme sua senha de administrador" type="password" value={reauthPassword} required autoComplete="current-password" onChange={(e) => setReauthPassword(e.target.value)} />
          <div className="admin-actions"><Button type="submit" variant="primary" disabled={aiLoading || keyStatus === null || keyBusy || !keyDraft || !reauthPassword}>Salvar chave</Button>
            {keyStatus?.configured ? <Button variant="destructive" disabled={aiLoading || keyBusy || !reauthPassword} onClick={revokeKey}>Revogar chave</Button> : null}</div>
        </form> : <SectorPromptPanel key={selectedAiSector.id} sectorId={selectedAiSector.id} />}
      </> : <p className="muted">Selecione um setor para ver as configurações de IA.</p>}
    </section> : null}
    {tab === 'security' ? <form className="admin-card admin-form" onSubmit={changeAdminPassword}><h2 className="t-sec">Alterar minha senha</h2>
      <TextField label="Senha atual" type="password" autoComplete="current-password" required value={passwordForm.currentPassword} onChange={(e) => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })} />
      <TextField label="Nova senha" type="password" autoComplete="new-password" minLength={12} required value={passwordForm.newPassword} onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })} />
      <Button type="submit" variant="primary">Alterar senha</Button>
    </form> : null}
    {tab === 'sectors' ? <section className="admin-grid">
      <div className="admin-card"><h2 className="t-sec">Setores</h2>
        <ul className="admin-list">{sectors.map((sector) => <li key={sector.id}>
          <div><strong>{sector.name}</strong><small>{sector.slug} · {sector.member_count} membros · {sector.is_active ? 'Ativo' : 'Inativo'} · {sector.max_upload_minutes ? `até ${sector.max_upload_minutes} min por arquivo` : 'sem limite por arquivo'} · {sector.max_monthly_minutes_per_user ? `${sector.max_monthly_minutes_per_user} min/mês por pessoa` : 'sem cota mensal'}</small></div>
          <div className="admin-actions"><Button onClick={() => showMembers(sector)}>Membros</Button><Button onClick={() => showSectorAI(sector)}>Configurar IA</Button>
              <Button onClick={() => setSectorForm({ id: sector.id, name: sector.name, slug: sector.slug, is_active: sector.is_active, max_upload_minutes: sector.max_upload_minutes ?? '', max_monthly_minutes_per_user: sector.max_monthly_minutes_per_user ?? '' })}>Editar</Button></div>
        </li>)}</ul>
        <div className="admin-actions"><Button disabled={sectorPage <= 1} onClick={() => loadPage('sectors', sectorPage - 1)}>Anterior</Button><span>Página {sectorPage}</span><Button disabled={!sectorNext} onClick={() => loadPage('sectors', sectorPage + 1)}>Próxima</Button></div>
        {selectedSector ? <div className="admin-members"><h3 className="t-sub">{selectedSector.name}: membros</h3>
          {members.length ? <><p className="muted">Consumo de mídia aceito em {memberPeriod || 'mês atual'} (horário de São Paulo). Excluir ou cancelar reunião não devolve minutos.</p><ul>{members.map((m) => <li key={m.id}>{m.username} {m.is_active ? '' : '(inativo)'} · {(Number(m.monthly_used_seconds || 0) / 60).toFixed(2)} min usados em {m.monthly_upload_count || 0} envios {selectedSector.max_monthly_minutes_per_user ? `de ${selectedSector.max_monthly_minutes_per_user} min disponíveis` : '(sem cota)'}</li>)}</ul></> : <p>Nenhum membro.</p>}
          <div className="admin-actions"><Button disabled={memberPage <= 1} onClick={() => showMembers(selectedSector, memberPage - 1)}>Anterior</Button><span>Página {memberPage}</span><Button disabled={!memberNext} onClick={() => showMembers(selectedSector, memberPage + 1)}>Próxima</Button></div>
        </div> : null}
      </div>
      <form className="admin-card admin-form" onSubmit={saveSector}><h2 className="t-sec">{sectorForm.id ? 'Editar setor' : 'Novo setor'}</h2>
        <TextField label="Nome" value={sectorForm.name} maxLength={120} required onChange={(e) => setSectorForm({ ...sectorForm, name: e.target.value })} />
        <TextField label="Identificador" hint="Letras minúsculas, números e hífen." value={sectorForm.slug} maxLength={120} required onChange={(e) => setSectorForm({ ...sectorForm, slug: e.target.value })} />
        <TextField label="Duração máxima por áudio/vídeo (minutos)" hint="Vale para cada arquivo enviado por membros do setor; vazio mantém sem limite setorial. O limite global de 5 GiB continua valendo." type="number" min={1} max={10080} value={sectorForm.max_upload_minutes ?? ''} onChange={(e) => setSectorForm({ ...sectorForm, max_upload_minutes: e.target.value })} />
        <TextField label="Cota mensal de mídia por usuário (minutos)" hint="Soma das durações dos arquivos aceitos no mês em America/Sao_Paulo; vazio mantém sem cota. Exclusão ou falha posterior não devolve minutos." type="number" min={1} max={44640} value={sectorForm.max_monthly_minutes_per_user ?? ''} onChange={(e) => setSectorForm({ ...sectorForm, max_monthly_minutes_per_user: e.target.value })} />
        {sectorForm.id ? <label className="admin-check"><input type="checkbox" checked={sectorForm.is_active} onChange={(e) => setSectorForm({ ...sectorForm, is_active: e.target.checked })} /> Setor ativo</label> : null}
        <div className="admin-actions"><Button type="submit" variant="primary" disabled={busy}>Salvar setor</Button>{sectorForm.id ? <Button onClick={() => setSectorForm(emptySector)}>Cancelar</Button> : null}</div>
      </form>
    </section> : tab === 'users' ? <section className="admin-grid">
      <div className="admin-card"><h2 className="t-sec">Usuários</h2>
        <ul className="admin-list">{users.map((item) => <li key={item.id}>
          <div><strong>{item.username}</strong><small>{item.sector_name || 'Sem setor'} · {item.is_active ? 'Ativo' : 'Inativo'}</small></div>
          {!item.is_staff ? <div className="admin-actions"><Button onClick={() => setUserForm({ id: item.id, username: item.username, first_name: item.first_name, last_name: item.last_name, email: item.email, sector_id: item.sector_id, password: '' })}>Editar</Button><Button onClick={() => toggleUser(item)}>{item.is_active ? 'Desativar' : 'Ativar'}</Button></div> : null}
        </li>)}</ul>
        <div className="admin-actions"><Button disabled={userPage <= 1} onClick={() => loadPage('users', userPage - 1)}>Anterior</Button><span>Página {userPage}</span><Button disabled={!userNext} onClick={() => loadPage('users', userPage + 1)}>Próxima</Button></div>
      </div>
      <form className="admin-card admin-form" onSubmit={saveUser} autoComplete="off"><h2 className="t-sec">{userForm.id ? 'Editar usuário' : 'Novo usuário local'}</h2>
        <TextField label="Usuário" value={userForm.username} maxLength={150} required disabled={Boolean(userForm.id)} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })} />
        <div className="admin-two"><TextField label="Nome" value={userForm.first_name} onChange={(e) => setUserForm({ ...userForm, first_name: e.target.value })} />
          <TextField label="Sobrenome" value={userForm.last_name} onChange={(e) => setUserForm({ ...userForm, last_name: e.target.value })} /></div>
        <TextField label="E-mail" type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} />
        <label className="at-field"><span className="at-field__label">Setor</span><select className="select" value={userForm.sector_id} required onChange={(e) => setUserForm({ ...userForm, sector_id: e.target.value })}>
          <option value="">Selecione</option>{sectorChoices.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select></label>
        <TextField label={userForm.id ? 'Nova senha (opcional)' : 'Senha inicial'} type="password" value={userForm.password} minLength={12} required={!userForm.id} autoComplete="new-password" onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} />
        <div className="admin-actions"><Button type="submit" variant="primary" disabled={busy}>Salvar usuário</Button>{userForm.id ? <Button onClick={() => setUserForm(emptyUser)}>Cancelar</Button> : null}</div>
      </form>
    </section> : null}
  </main></div>;
}
