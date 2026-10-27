# Scribrief — candidata 0.1.0-alpha.2

**Distribuição prevista:** repositório de código-fonte AGPL-3.0-only para instalação **interna**, não imagens Docker pré-construídas. Não exponha a aplicação à Internet. O servidor precisa apenas de saída HTTPS à OpenAI para usar a IA; banco, broker e interface administrativa não devem ser públicos.

## Nesta candidata

- Tetos mensais opcionais de IA por setor e usuário, reservas transacionais por tentativa, saldo administrativo e bloqueio de regeneração quando a cota está esgotada. Valores estimados não equivalem à fatura do provedor.
- Um upload multipart em andamento por instalação, limite agregado de staging por usuário/instalação e piso de espaço livre, com recuperação conservadora após falha. Teto absoluto por arquivo de 5 GiB; staging expira em 2 horas.
- DOMPurify transitivo atualizado para 3.4.17; regressões de orçamento/arquitetura corrigidas, contrato OpenAPI atualizado e novos testes PostgreSQL e PNG/PDF sintéticos em desktop/móvel.

- Instalação Windows/PowerShell e Linux/Bash com Compose, HTTPS local autoassinado e conta inicial `ADMIN` cuja senha deve ser trocada antes de liberar o acesso LAN.
- Contas locais, setores e chave OpenAI cifrada por setor; gravações e transcrições em arquivos privados, atas e mapas, compartilhamento somente leitura e transferência de propriedade dentro do setor.
- Backup frio com verificação de configuração e manifesto, restauração em clone sem portas; o destino do backup **precisa** ter cifragem/ACL próprias.
- PostgreSQL 16.15/Alpine 3.24 derivado: `gosu` substituído por `su-exec`, restrito ao usuário `postgres`, para remover alertas do binário Go da imagem oficial.

## Validação e limites conhecidos

Instalação/backup/restauração com dados **sintéticos** passaram numa distro WSL2 com daemon Docker separado e na CI Linux. O ensaio WSL preservou um usuário, arquivo de mídia e PEM TLS; **não** é teste no PC final, em outro host nem com reunião longa. Antes de usar dados reais, teste firewall/ACL, certificado corporativo, backup portável e fluxo de mídia/IA autorizado no seu ambiente.

No scan da candidata de 22/10/2026, a imagem derivada PostgreSQL, frontend e Valkey tiveram **0 HIGH/CRITICAL**. A imagem backend Debian 13 ainda teve **207 HIGH e 1 CRITICAL** de sistema operacional, sem versão corrigida indicada no feed Debian para essa base. O crítico é `CVE-2026-6653` em `libxml2`, descrito pelo Debian como DoS menor; isso **não** é prova de inaplicabilidade. Não houve aceite de risco ou homologação de produção. Reconstrua e reavalie as imagens antes da instalação real.

O limite configurável de upload de 5 GiB e reuniões de várias horas ainda não tiveram ensaio de capacidade/qualidade suficiente para garantia operacional. Custos OpenAI mostrados pela interface são estimativas parciais. A aplicação usa somente o provedor OpenAI nesta versão. O código-fonte é publicado sem binários FFmpeg; se alguém distribuir imagens prontas, deve cumprir os avisos e obrigações de licença dos binários nelas contidos. Consulte [README](README.md), [avisos de terceiros](THIRD_PARTY_NOTICES.md) e [segurança](SECURITY.md).
