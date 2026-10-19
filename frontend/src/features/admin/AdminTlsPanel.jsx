import { useEffect, useState } from 'react';
import { request } from '../../api/client.js';
import { Button, InlineNotice, TextField } from '../../shared/components/index.js';

export default function AdminTlsPanel() {
  const [status, setStatus] = useState(null);
  const [certificate, setCertificate] = useState(null);
  const [privateKey, setPrivateKey] = useState(null);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    request('GET', '/api/admin/tls/').then(setStatus).catch((err) => setError(err.message));
  }, []);

  async function rotate(event) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!window.confirm('Substituir o certificado HTTPS das portas pública e administrativa? Confirme que os dois endereços estão no SAN.')) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const form = new FormData();
      form.append('certificate', certificate);
      form.append('private_key', privateKey);
      form.append('current_password', password);
      const result = await request('POST', '/api/admin/tls/', { form });
      const refreshed = await request('GET', '/api/admin/tls/');
      setStatus(refreshed || result);
      setNotice('Par TLS validado e salvo. A recarga do Nginx ocorre em até alguns segundos; confirme o certificado nas duas portas.');
      setCertificate(null); setPrivateKey(null);
      formElement.reset();
    } catch (err) { setError(err.message); }
    finally { setPassword(''); setBusy(false); }
  }

  return <section className="admin-card admin-form">
    <h2 className="t-sec">Certificado HTTPS</h2>
    <p className="muted">Na instalação local é criado um certificado autoassinado, que gera aviso no navegador até ser confiado pelos clientes. Para uso interno, substitua-o por certificado da CA corporativa. Não exponha o site à Internet.</p>
    {error ? <InlineNotice tone="erro">{error}</InlineNotice> : null}
    {notice ? <InlineNotice tone="sucesso">{notice}</InlineNotice> : null}
    {status?.configured && status.valid !== false ? <p>Atual: SHA-256 <code>{status.fingerprint_sha256}</code><br />Vencimento: {new Date(status.expires_at).toLocaleString('pt-BR')}<br />SAN exigido: {(status.hostnames || []).join(', ')}</p> : status?.configured ? <InlineNotice tone="erro">O certificado ativo está inválido ou expirado. Substitua o par PEM.</InlineNotice> : <p className="muted">Status indisponível ou certificado não configurado.</p>}
    <form className="admin-form" onSubmit={rotate} autoComplete="off">
      <label className="at-field"><span className="at-field__label">Certificado ou cadeia completa PEM (.crt/.pem)</span><input type="file" accept=".crt,.pem" required onChange={(e) => setCertificate(e.target.files?.[0] || null)} /></label>
      <label className="at-field"><span className="at-field__label">Chave privada PEM sem senha (.key/.pem)</span><input type="file" accept=".key,.pem" required onChange={(e) => setPrivateKey(e.target.files?.[0] || null)} /></label>
      <TextField label="Confirme sua senha de administrador" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      <Button type="submit" variant="primary" disabled={busy || !certificate || !privateKey || !password}>Trocar certificado</Button>
    </form>
    <p className="muted">A chave fica apenas no volume TLS do servidor e não pode ser baixada por esta interface. Antes da troca, faça backup e confirme acesso ao painel em outro navegador.</p>
  </section>;
}
