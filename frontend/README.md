# Scribrief — frontend integrado

Frontend entregue pelo usuário em `ata-frontend.zip` e mantido em `frontend/`. A direção visual e os componentes originais estão documentados em `docs/brief.md`, `docs/design-system.md`, `docs/telas.md` e `docs/tokens.json`. A integração preserva o desenho editorial; só acrescenta consentimento explícito e correções de contraste.

## Executar

Na raiz do projeto, configure `.env` a partir de `.env.example`, então:

```powershell
./scripts/new-dev-cert.ps1
docker compose up -d --build
docker compose exec -T backend python manage.py migrate --noinput
```

Acesse `https://127.0.0.1:18574/` (certificado autoassinado local). O endereço `http://127.0.0.1:18573/` redireciona para HTTPS. Nginx serve os arquivos estáticos do React e encaminha páginas MVT e `/api/` ao Django na mesma origem. Não use uploads reais sem consentimento dos participantes e chave/ambiente autorizados.

Para desenvolvimento com Vite, use o override `docker-compose.dev.yml` para publicar o backend só no loopback, `npm ci` e `npm run dev`. `VITE_API_URL=/api/v1` e `VITE_API_PROXY=http://127.0.0.1:8000` são os valores locais.

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
