# Atualização e reversão — beta interno

**Não execute atualização automática em produção.** Este guia é para um operador autorizado, em janela de manutenção, após validação em um clone com o mesmo banco e mídia. Não use `docker compose down -v`.

## Antes da mudança

**Alpha.1 → candidata alpha.2:** há migrações `accounts.0011` (tetos opcionais de IA), `audit.0013` (reservas e vínculo ao ledger) e `meetings.0024` (tamanho do original e admissão de uploads). Não há backfill inventado do custo anterior; entram as estimativas conhecidas do mês. Arquivos antigos em staging sem tamanho medido são contabilizados conservadoramente pelo máximo por arquivo. Preserve o Compose antigo para fazer o backup **antes** de substituí-lo: a nova configuração acrescenta três variáveis de capacidade e o backup antigo deve detectar drift se você trocar os arquivos primeiro. Reversão de schema apaga novos registros/campos: prefira recuperar o backup completo previamente testado, não migrar para trás às cegas. Esta candidata não deve substituir uma instalação ativa sem janela/backup/clone e confirmação de que não há upload/job em execução.

1. Registre versão/commit, imagens por digest, migrações pendentes, quantidade de reuniões e jobs ativos. Interrompa novos uploads; espere jobs terminarem ou cancele-os pelo painel. Não interrompa uma transcrição em andamento para atualizar imagens.
   Confira antes que o Compose da pasta descreve **os mesmos contêineres em execução**. O backup agora compara os hashes de configuração e recusa drift antes de interromper serviços; não force um backup/upgrade com override TLS antigo omitido. Ele reinicia os contêineres originais, não aplica a configuração nova silenciosamente.
2. Faça backup **frio** de PostgreSQL, volumes de mídia/TLS e `deploy/secrets/` com `deploy/backup.ps1 -EncryptedDestination ... -AcknowledgeProtectedStorage` ou `deploy/backup.sh --encrypted-destination ... --ack-protected-storage`. O destino deve ser cifrado e protegido: os scripts não criptografam o bundle. Guarde-o fora do host.
3. Rode `deploy/restore-test.ps1 -BackupDirectory ...` ou `deploy/restore-test.sh ...` em clone isolado e confira reunião, segmentos, arquivo MP3, permissões e chave de IA. Um `pg_dump` sem mídia/chave não basta. Guarde o código/imagens da versão anterior para reversão.
4. Teste a atualização no clone, inclusive imagem PostgreSQL. Versões **major** do PostgreSQL exigem plano de migração específico; a troca 16.6→16.15 ensaiada aqui foi apenas patch no major 16, com 1 reunião sintética.

## Aplicar

1. Troque para o pacote aprovado, mantendo `deploy/beta.env`, `deploy/secrets/`, os volumes originais (inclusive `tls`) e, se presentes, `deploy/certs/` legados. Nunca copie segredos para Git ou para uma issue.
   A alpha constrói localmente `db/Dockerfile` (PostgreSQL **major 16** derivado com `su-exec`); mesmo sem migração de schema, valide a troca de imagem em clone restaurado antes de aplicá-la sobre um volume existente. O backup recusa drift de Compose da instalação legada; não contorne essa proteção com `up` direto.
2. Execute o instalador correspondente **sem** certificado/chave para preservar o volume TLS atual, com `SkipAdmin`/`--skip-admin`. Ele valida configuração/Compose, constrói, sobe DB/Valkey/backend, migra e checa Django, executa a verificação da conta inicial sem criá-la, depois sobe worker/Beat/frontend. Não há redefinição de senhas nem criação de `demo`; se uma conta inicial ainda exige troca de senha, binds fora de loopback são recusados. Certificados explícitos substituem o ativo; prefira o painel admin para rotação. **Migrações não são revertidas automaticamente.**
   A migração `accounts.0009` adiciona `bootstrap_local_only` e marca somente `ADMIN` bootstrap ainda pendente em instalação anterior. Não força troca retroativa dos usuários existentes. A partir desta versão, contas criadas ou senhas redefinidas pelo admin exigem troca no login seguinte; reset revoga sessões antigas. Teste esses casos no clone antes da janela real.
   A migração `accounts.0010` remove campos antigos de identidade externa. **Ela aborta** caso encontre `auth_source` diferente de `local` ou `external_id` preenchido; não transforma essas contas em login por senha local. Nesse caso, pare, preserve o backup e reconcilie ou retire esses vínculos em um plano explícito antes de repetir. **Só desativar o usuário não elimina o bloqueio da migração.** A migração não foi aplicada automaticamente à pilha de desenvolvimento em execução nesta entrega.
3. Confira `docker compose --env-file deploy/beta.env -f compose.beta.yaml ps`; login e CSRF na porta pública; 404 para `/admin/` público; painel admin apenas pela rede de gestão; upload/consulta com mídia **sintética**; logs de erro e Health. Confirme que nenhuma porta de banco/Valkey/backend está publicada.
4. Monitore filas, disco, erros, custo e backup da primeira janela. Atualize o registro operacional com versão, horário, operador e resultado.

## Se falhar

- Se nenhuma migração incompatível foi aplicada e os dados permanecem legíveis, volte ao pacote/imagens anteriores e repita os smokes. Não presuma reversibilidade de migrations Django sem teste explícito.
- Se houve migração incompatível ou corrupção, pare ingress/worker, **restaure o backup verificado em clone primeiro**, e só então restaure o ambiente original conforme plano de contingência da empresa. Isso pode perder mudanças entre backup e falha: RPO/RTO precisam ser definidos pela organização.
- Nunca tente “corrigir” removendo volumes. Preserve logs e artefatos diagnósticos sem segredos/dados pessoais, e reporte a falha por canal privado.

O ensaio local de 2026-10-19 comprovou somente que um clone sintético preservou 1 usuário, 1 reunião e 2 segmentos após patch PostgreSQL 16.6→16.15 e rebuild. **Rollback real, carga longa e outra máquina não foram comprovados.**
