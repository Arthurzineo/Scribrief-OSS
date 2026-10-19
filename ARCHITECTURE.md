# Arquitetura do Scribrief beta

## Contêineres e fronteiras

- **Nginx/frontend:** único serviço com portas publicadas; HTTPS público e HTTPS administrativo em portas distintas. Bloqueia `/admin`, `/api/admin`, Swagger e schema na porta pública.
- **Django/backend:** autenticação, autorização por reunião/setor, HTML MVT, API, trilha de auditoria e administração. Só recebe conexões da rede interna Docker.
- **Bootstrap de identidade:** `bootstrap_admin` cria `ADMIN`/`ADMIN123` apenas quando não há usuários, com hash de senha e `UserMembership.must_change_password=true`; não cria `demo` nem redefine credenciais existentes. Os dois binds permanecem em loopback até a troca. Middleware nega páginas/APIs fora da sessão e da alteração de senha; React mostra exclusivamente o formulário de primeiro acesso. O instalador interrompe antes de subir frontend/worker se a conta inicial pendente coexistir com bind não local.
- **Celery worker:** ffmpeg, transcrição, geração de ata/mapa, purga e tarefas assíncronas. Único componente aplicativo com saída ao provedor externo de IA.
- **Celery Beat:** agendamento de tarefas periódicas, sem saída ao provedor externo.
- **PostgreSQL:** usuários, reuniões, segmentos, atas, empregos, estado e auditoria; nenhum áudio/vídeo BLOB.
- **Valkey:** serviço de fila/cache compatível com o protocolo Redis; não é fonte autoritativa de reuniões.
- **Volumes `media`/`pgdata`/`tls`:** mídia privada, dados relacionais e par HTTPS ativo, respectivamente. Todos devem constar do mesmo plano de recuperação.

`compose.beta.yaml` tem nome de projeto e volumes diferentes do Compose de desenvolvimento. Segredos locais são arquivos montados apenas nos serviços necessários. O volume `tls` é gravável apenas pelo backend e somente leitura no Nginx, sem socket Docker; worker/banco não recebem o certificado/chave. O instalador inicializa-o como root uma única vez, com diretório `0750`, arquivo `0640`, dono app e grupo leitor 101. O backend pertence também ao grupo 101 e o atribui explicitamente ao novo PEM, pois volumes Docker Desktop podem não preservar setgid. O backend troca um PEM combinado por substituição atômica; watcher não privilegiado no frontend verifica mudança, `nginx -t` e recarga graciosa, sem expor chave em HTTP ou logs. A API administrativa registra uma intenção com fingerprint antes de alterar o PEM e registra o resultado em seguida; assim uma falha posterior de auditoria não deixa a tentativa invisível. A chave-mestra setorial é fornecida somente a backend e worker. Variáveis em `deploy/beta.env` não devem conter segredos.

`PUBLIC_HOSTNAME` e `ADMIN_HOSTNAME` entram no `ALLOWED_HOSTS`; ambos precisam constar do SAN do certificado. As portas de usuário e admin devem receber apenas tráfego das redes internas autorizadas, e nenhuma rota de entrada da Internet. PostgreSQL e Valkey não têm portas de host; o worker pode abrir HTTPS à OpenAI pela rede `egress`, mas o Compose **não** aplica filtro por destino. Firewall e ACL/VLAN são obrigatórios. Fontes da interface são servidas pelo próprio Nginx, sem chamada do navegador ao Google Fonts.

## Estados e proteção

Upload temporário não vai à IA antes de confirmação explícita. Processamento é assíncrono; o original/vídeo é removido após transcrição bem-sucedida, e o áudio MP3 permanece para reprodução até exclusão/purga. Exclusão oculta a reunião imediatamente; o administrador pode restaurá-la por 72 horas, após o que a purga remove banco e mídia. Backups podem prolongar a retenção e exigem política própria. Eventos ativos de auditoria/sistema têm retenção de 90 dias. Acesso entre usuários é por dono; partilha setorial concede leitura; transferência muda a propriedade da reunião.

## Limites atuais

Não há modo offline nem integração LDAP. Custos de IA são estimados. O limite configurável de upload pode chegar a 5 GiB, mas carga/recuperação nesse extremo precisa de aceite operacional. Compose em host único não fornece alta disponibilidade. Um backup só é válido depois de restauração ensaiada, incluindo a chave de cifragem setorial e o TLS. O autoassinado inicial vence após 90 dias e precisa ser confiado pelos clientes ou substituído por CA corporativa; o servidor valida par, validade e SAN, **não** a cadeia de confiança do navegador. Firewall corporativo continua responsabilidade do operador.

As bases Docker são fixadas por digest no pacote beta. A varredura Trivy preliminar ainda apontou vulnerabilidades críticas/altas no backend e no utilitário `gosu` da imagem PostgreSQL; não há aceite de produção. O operador deve atualizar/revalidar imagens e avaliar esses riscos antes de dados reais.
