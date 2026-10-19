# Telas

Como cada tela do produto se monta com os tokens e componentes. Estrutura comum: barra lateral (`barra-lateral`, fundo `superficie-alt`) + área principal sobre `papel`, conteúdo até `conteudo-max`, topo a `space-12`.

## 1. Login

- Sem barra lateral. Fundo `papel`; cartão central de `cartao-login` (400 px) em `superficie`, borda 1 px `borda`, raio `radius-md`, padding `space-8`.
- Nome do produto em `titulo-pagina`, uma linha de descrição em `interface` `tinta-2`, `TextField` de e-mail e de senha, `Button` primário "Entrar" em largura total.
- Erro: `InlineNotice tone="erro"` acima do botão — "E-mail ou senha incorretos". Sem imagem lateral, sem ilustração.

## 2. Lista de reuniões

- Cabeçalho: "Reuniões" em `titulo-pagina` à esquerda, `Button` primário "Nova reunião" (ícone `plus`) à direita.
- Barra de ferramentas: `TextField` de busca por título (ícone `search`) e filtro por estado (seletor com os rótulos de `StatusTag`).
- Lista em `at-list` com um `MeetingRow` por reunião. Nada de cartões.
- Vazio: uma frase em `interface` `tinta-2` ("Nenhuma reunião ainda.") e `Button` primário "Enviar a primeira gravação", centralizados, com `space-16` acima.

## 3. Nova reunião

- `titulo-pagina` "Nova reunião"; `TextField` de título e de data lado a lado.
- `Dropzone` grande; linha de apoio com formatos aceitos e tamanho máximo.
- Ao escolher: o `Dropzone` passa a mostrar nome, tamanho (mono), progresso e "Cancelar".
- `InlineNotice` de privacidade logo abaixo: "O áudio será enviado a um serviço externo para transcrição."

## 4. Processamento

- Título da reunião, depois `StepList` com Arquivo recebido · Extraindo áudio · Transcrevendo · Transcrição pronta.
- `Button` **Ver progresso** abre painel com contagem de blocos concluídos/planejados e porcentagem; atualiza automaticamente, 100% apenas após publicação da transcrição. Sem plano confiável, mostrar indeterminado. O painel não interrompe nem reinicia o job.
- Abaixo, em `tinta-2`: "Você pode fechar esta página. A reunião aparece na lista quando estiver pronta."
- Erro: a etapa em `erro` com a mensagem em `detail` e `Button` "Tentar novamente" (ícone `retry`).

## 5. Transcrição e falantes

- Cabeçalho: título em `titulo-pagina`, data e duração (mono) em `tinta-2`; `ViewTabs` "Transcrição" / "Ata" / "Mapa mental" logo abaixo.
- Duas colunas: à esquerda a coluna de leitura (até `coluna-leitura`) sobre `superficie`, com rolagem **dentro da área das falas**, um `Utterance` por sequência do mesmo falante e `AudioPlayer` sempre visível no rodapé da coluna; à direita, dois blocos separados.
  - Bloco "Falantes" (`painel-falantes`, padding `space-6`): `subtitulo` e um `SpeakerRow` por falante. Dois ou mais falantes podem ser selecionados e unidos em uma operação, escolhendo qual identidade manter. Bloco separado "Falantes semelhantes": até duas análises por reunião, contador visível, processamento em segundo plano, sugestões persistidas no servidor ao navegar e botões para ouvir, confirmar, ignorar um grupo ou negar todos. A confirmação faz a união em lote automaticamente; nada é unido só pelo rótulo da IA. Bloco independente de ações: "AI Ajuda corrigir Transcrição", "Baixar transcrição" (secundário) e "Gerar ata" (primário). Os controles não rolam junto com as falas.
- Ao trocar um nome, todas as `SpeakerTag` daquele falante mudam na hora.
- "Gerar ata" com falantes ainda "Pessoa N": `ConfirmModal` — "Ainda há falantes sem nome. Gerar mesmo assim?"
- Abaixo de 1100 px os blocos laterais vão para baixo da coluna; a área das falas mantém rolagem interna e o player continua no rodapé da coluna.

## 6. Ata

- Mesmo cabeçalho e `ViewTabs` com "Ata" ativo.
- Gerando: `StepList` com uma etapa ("Gerando ata", `andamento`).
- Pronta: documento em `superficie` sobre `papel`, borda `borda`, raio `radius-md`, padding `space-8`, largura `coluna-leitura`. Seções em `titulo-secao`, separadas por `space-12`:
  1. Participantes — nomes editáveis.
  2. Resumo executivo — um ou dois parágrafos em `leitura`.
  3. Tópicos discutidos — títulos e comentários do que foi falado em cada assunto.
  4. Decisões — lista numerada em `leitura`, com opção de adicionar/remover.
  5. Tarefas pendentes — cartões responsivos com tarefa/ação, responsável e prazo editáveis, com opção de adicionar/remover.
- Cada seção editável (`TextField multiline` ou edição no lugar, como no `Utterance`).
- Ações acima do documento: "Baixar" (PDF ou TXT, ícone `download`), "Copiar" (ícone `copy`), "Marcar ata como revisada" (opcional) e "Gerar novamente" — este pede `ConfirmModal destructive`, pois substitui a ata atual.

## 7. Conta

- `TextField` de nome e e-mail, bloco de troca de senha (senha atual, nova senha, `Button` "Alterar senha"), alternador de tema claro/escuro e `Button` "Sair".
- O tema se aplica com `data-theme="light"` ou `data-theme="dark"` no `<html>`.

## 8. Mapa mental — extensão P008

- Terceira aba da reunião, disponível após a geração da ata. Sem ata, estado vazio com caminho para a aba Ata.
- Um cartão central traz o tema principal em poucas palavras. Até sete ramos conectados mostram assuntos-chave, cada um com pontos curtos de no máximo oito palavras. Não exibir parágrafos da ata no mapa.
- A IA só relaciona decisão/tarefa a assunto quando houver evidência clara na ata; caso contrário, usa um ramo de encaminhamentos. O mapa declara que deriva da ata e que transcrição/áudio devem ser consultados para conferir detalhes.
- Cartões usam `superficie`, bordas `borda`, texto `tinta` e linhas simples; sem gradientes, sombras, ilustrações ou cores de marca da ata. Em largura estreita, os ramos viram uma árvore vertical sem rolagem horizontal.
- O mapa é somente leitura; “Editar na ata” leva à edição existente. Uma ata desatualizada exige atualização antes de gerar o mapa. A geração e regeneração do mapa usam uma chamada de IA separada; **Baixar PNG** e **Baixar PDF** exportam os cartões já gerados em largura fixa, independentemente do viewport, sem chamada adicional. Os botões mostram progresso/erro.
