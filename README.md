# Scribrief

Scribrief é uma aplicação web para transcrever reuniões autorizadas, revisar falas, gerar atas por tópicos e visualizar mapas mentais. Usa Django, React/Vite, Celery, PostgreSQL, Valkey (protocolo Redis), ffmpeg e um provedor externo de IA. **Este código é beta, exclusivamente para instalação em rede interna; não o exponha à Internet nem o considere homologado para produção.**

O código original deste pacote candidato está sob **GNU AGPL-3.0-only** (`LICENSE`), sujeita à confirmação dos direitos de redistribuição de todos os recursos antes da publicação aberta. **Copyright (C) 2026 Arthur Gonçalves e contribuidores, na medida dos direitos que detenham.** Uso comercial é permitido. Preserve avisos de autoria/licença e disponibilize o código-fonte correspondente aos usuários que interagirem pela rede com uma versão modificada, nos termos da seção 13. A licença não transfere direitos sobre marcas e não torna automaticamente aberto software independente da instalação. Informações de terceiros em `THIRD_PARTY_NOTICES.md`.

## Beta interno com Docker

O pacote usa contêineres Linux. No Windows 11, instale Docker Desktop com WSL 2; no Linux, Docker Engine e Compose plugin. O host não precisa de Python, Node ou ffmpeg. Verifique os termos de licenciamento do Docker Desktop aplicáveis à sua organização.

1. Obtenha um certificado TLS emitido por CA confiável na empresa, cuja extensão SAN contenha os nomes configurados em `PUBLIC_HOSTNAME` **e** `ADMIN_HOSTNAME`. Certificado autoassinado é apenas para testes isolados.
2. Copie `deploy/beta.env.example` para `deploy/beta.env`. Configure os IPs explícitos das interfaces internas, nomes DNS e portas. Por padrão ambos os serviços ficam apenas no loopback.
3. Windows/PowerShell 7: `./deploy/install.ps1 -Certificate C:\caminho\servidor.crt -PrivateKey C:\caminho\servidor.key`. Linux/Bash: `./deploy/install.sh --certificate /caminho/servidor.crt --private-key /caminho/servidor.key`.
4. O instalador cria segredos diferentes para banco, Valkey, sessão Django e cifragem das chaves de IA; reexecutá-lo não os substitui. Ele aplica migrações e solicita interativamente a criação do administrador, sem senha padrão.
5. Acesse `https://PUBLIC_HOSTNAME:PUBLIC_HTTPS_PORT/`. O admin fica em `https://ADMIN_HOSTNAME:ADMIN_HTTPS_PORT/admin/`. `ADMIN_BIND_IP` precisa pertencer a uma rede de gestão restrita; por padrão é `127.0.0.1`. Use firewall/ACL, não somente portas diferentes.

No Linux, mantenha `deploy/secrets/` e `deploy/certs/` com permissão `0700` e pertencentes à conta instaladora. Os arquivos montados individualmente pelo Compose ficam legíveis (`0644`) **dentro desses diretórios privados**, para os processos não-root dos contêineres; não abra a permissão dos diretórios nem copie os arquivos para uma pasta pública. No Windows, restrinja essas pastas por ACL NTFS à conta operadora e administradores antes de usar dados reais. O Compose não coloca o conteúdo dos segredos em variáveis de ambiente nem na imagem.

**Topologia obrigatória:** a interface de usuário atende apenas estações da LAN autorizada; a interface administrativa atende somente a rede de gestão; PostgreSQL, Valkey, backend e worker ficam em redes Docker privadas, sem publicação no host nem rota de entrada da Internet. Configure firewall do host, roteador e ACL/VLAN para **negar conexões de entrada da Internet** para ambas as interfaces, principalmente `/admin/`. Não faça port forwarding/NAT externo. Somente o Nginx é publicado pelo Compose, e bind de IP não substitui firewall. Mídia permanece em volume privado de arquivos, **não** em BLOB no banco.

O worker precisa de **saída HTTPS (TCP 443) controlada à API da OpenAI**, com DNS e validação TLS; esta saída não autoriza acesso de entrada da Internet. O frontend e as estações não precisam acessar a OpenAI diretamente. Não há funcionamento totalmente offline. Cadastre uma chave separada por setor no admin depois de criar o setor e os usuários. A equipe de rede deve permitir somente os destinos necessários, registrar e monitorar o egress; o Compose sozinho não aplica uma ACL de destino à OpenAI. Conteúdo autorizado de reunião é enviado ao provedor externo após consentimento.

## Operação e limites

Use `docker compose --env-file deploy/beta.env -f compose.beta.yaml ps` e `logs` para diagnóstico. Nunca execute `down -v` para atualizar ou parar, pois remove volumes. Para backup frio, use `deploy/backup.ps1 -EncryptedDestination <pasta-cifrada> -AcknowledgeProtectedStorage` no Windows ou `deploy/backup.sh --encrypted-destination <pasta-cifrada> --ack-protected-storage` no Linux. O comando recusa jobs ativos, pausa temporariamente os serviços de aplicação e copia banco, mídia, configuração e segredos para o destino. **O bundle não é cifrado pelo script**: a pasta precisa ter cifragem e ACL corporativa. Ensaie `deploy/restore-test.ps1 -BackupDirectory <backup>` ou `deploy/restore-test.sh <backup>`; isso cria um projeto Docker isolado sem portas publicadas e não toca no original. Ainda falta definir retenção, destino externo e RPO/RTO de cada empresa.

Para atualizar ou reverter versão/imagens, siga **`UPGRADE.md`**. Não aplique o novo pacote sobre dados reais sem janela, backup frio verificado e clone de ensaio; migrações não são revertidas automaticamente.

Guarde `deploy/secrets/sector_key` junto do backup seguro: sem ela, chaves de IA cifradas no banco não podem ser abertas. Não registre nem envie `deploy/secrets/`, `deploy/certs/localhost.key`, `deploy/beta.env`, áudio, banco, backup ou dados reais em issues.

Antes de dados reais, valide na sua rede: certificado confiável no cliente; isolamento da porta admin; restauração completa de banco **e** mídia; retenção e exclusão; carga de até 5 GiB ou reduza `MAX_UPLOAD_MB`; reunião longa; contas de setores distintos; monitoramento de worker/disco. A varredura preliminar de imagens ainda tem achados altos/críticos no backend (ffmpeg/bibliotecas) e no `gosu` da imagem PostgreSQL; não há aceite de risco ou homologação de produção. Refaça a análise nas imagens exatas da sua instalação. Custos exibidos são **estimativas**, não fatura. A transcrição e a ata requerem revisão humana; o usuário deve ter autorização para enviar o conteúdo ao provedor externo.

## Desenvolvimento

No backend: `uv sync --frozen --python 3.12`, `uv run pytest -q`, `uv run ruff check .`. No frontend: `npm ci`, `npm test`, `npm run build`. Os testes automatizados simulam o provedor externo e não cobram chamadas de IA. Há detalhes da arquitetura em `ARCHITECTURE.md`.

Consulte `SECURITY.md` para relatar vulnerabilidades de forma privada. Não use issues públicas para dados de cliente ou segredos.
