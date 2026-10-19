# Scribrief — frontend integrado

Frontend React/Vite do Scribrief, mantido em `frontend/`. A direção visual editorial está documentada em `docs/brief.md`, `docs/design-system.md`, `docs/telas.md` e `docs/tokens.json`. A aplicação inclui consentimento explícito e ajustes de acessibilidade.

## Executar

Para instalar o sistema completo em rede interna, siga o `README.md` da raiz, que usa `compose.beta.yaml` e `deploy/install.ps1`/`deploy/install.sh`. Não exponha a interface à Internet e não use gravações reais sem autorização para enviá-las ao provedor externo.

Para desenvolvimento da interface, execute `npm ci` e `npm run dev` nesta pasta, com um backend de teste separado. Defina `VITE_API_URL=/api/v1` e `VITE_API_PROXY=http://127.0.0.1:8000` para o proxy local se necessário. Em produção, o Nginx do Compose serve os arquivos estáticos do React e encaminha páginas MVT e `/api/` ao Django na mesma origem.

## Contrato real

A API usa **cookie de sessão + CSRF**, não Bearer/localStorage. A base é `/api/v1/`. Login aceita `username` e `password`; o frontend obtém `csrftoken` em `/csrf/` e envia `X-CSRFToken` em mutações. O fluxo de upload cria a reunião (`POST /meetings/`) e depois envia multipart (`POST /meetings/{id}/upload/`) com `consent_confirmed=true`; se falhar, o frontend tenta remover o rascunho.

O mapeamento de estados/campos está em `src/api/mappers.js`; as rotas e versões de edição em `src/api/meetings.js`. O backend exige versão para renomear/unir falantes e editar transcrição/ata. O áudio normalizado é servido por endpoint autenticado com suporte a Range. Downloads de PDF/TXT são gerados localmente pelo frontend; Markdown/JSON também podem ser baixados via API autenticada.

## Verificação

```powershell
npm ci
npm test
npm run build
npm audit --audit-level=moderate
```

O teste visual/local requer Chrome instalado, backend/Compose ativos e dados sintéticos do comando `seed_demo`:

```powershell
$env:E2E_USERNAME='demo'
$env:E2E_PASSWORD='<senha sintética configurada>'
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

O teste padrão é somente leitura: cobre login, lista, transcrição, ata, upload (interface/consentimento), XSS e layout móvel. Para exercer renomeação/edição na reunião sintética, defina `E2E_MUTATIONS=true`; ele tenta restaurar os valores, mas marcará a ata como desatualizada, exigindo nova geração ou redefinição da fixture. Capturas locais ficam em `.artifacts/`, ignorada pelo Git. Não chama OpenAI.

## Limitações

- Sem chave/áudio autorizados, a geração real pela OpenAI não foi exercitada.
- `seed_demo` não contém áudio; o player fica desabilitado nesse registro sintético.
- HTTPS/domínio, retenção, backups, orçamento e operação de upload de 5 GiB ainda exigem decisão antes de produção.
