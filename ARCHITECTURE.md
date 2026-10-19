# Arquitetura do Scribrief beta

## Contêineres e fronteiras

- **Nginx/frontend:** único serviço com portas publicadas; HTTPS público e HTTPS administrativo em portas distintas. Bloqueia `/admin`, `/api/admin`, Swagger e schema na porta pública.
- **Django/backend:** autenticação, autorização por reunião/setor, HTML MVT, API, trilha de auditoria e administração. Só recebe conexões da rede interna Docker.
- **Celery worker:** ffmpeg, transcrição, geração de ata/mapa, purga e tarefas assíncronas. Único componente aplicativo com saída ao provedor externo de IA.
- **Celery Beat:** agendamento de tarefas periódicas, sem saída ao provedor externo.
- **PostgreSQL:** usuários, reuniões, segmentos, atas, empregos, estado e auditoria; nenhum áudio/vídeo BLOB.
- **Valkey:** serviço de fila/cache compatível com o protocolo Redis; não é fonte autoritativa de reuniões.
- **Volumes `media`/`pgdata`:** mídia privada no sistema de arquivos e dados relacionais, respectivamente. Ambos devem constar do mesmo plano de recuperação.

`compose.beta.yaml` tem nome de projeto e volumes diferentes do Compose de desenvolvimento. Segredos locais são arquivos montados apenas nos serviços necessários. Certificado/chave TLS são montados somente no Nginx; a chave-mestra setorial, somente em backend e worker. Variáveis em `deploy/beta.env` não devem conter segredos.

## Estados e proteção

Upload temporário não vai à IA antes de confirmação explícita. Processamento é assíncrono; o original/vídeo é removido após transcrição bem-sucedida, e o áudio MP3 permanece para reprodução até exclusão/purga. Exclusão oculta a reunião imediatamente; o administrador pode restaurá-la por 72 horas, após o que a purga remove banco e mídia. Backups podem prolongar a retenção e exigem política própria. Eventos ativos de auditoria/sistema têm retenção de 90 dias. Acesso entre usuários é por dono; partilha setorial concede leitura; transferência muda a propriedade da reunião.

## Limites atuais

Não há modo offline nem integração LDAP. Custos de IA são estimados. O limite configurável de upload pode chegar a 5 GiB, mas carga/recuperação nesse extremo precisa de aceite operacional. Compose em host único não fornece alta disponibilidade. Um backup só é válido depois de restauração ensaiada, incluindo a chave de cifragem setorial. Certificado confiável e firewall corporativo são responsabilidade do operador; o instalador só valida par, validade temporal e SAN, não a cadeia de confiança no navegador.
