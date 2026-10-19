O produto entrega um documento. A interface é uma mesa de trabalho editorial — papel, tinta e uma única cor de destaque — e não um painel de SaaS. Sóbrio, editorial, confiável, silencioso.

## Princípios

- O conteúdo é o documento: transcrição e ata em coluna estreita (`coluna-leitura`, 680 px), serifada, sobre `superficie`. A interface ao redor recua.
- Linhas, não sombras: toda separação é uma borda de 1 px (`linha`) em `borda`. Nenhum token de sombra existe, de propósito.
- Uma cor de destaque (`destaque`) para a ação principal, links, foco e item ativo. Todo o resto é papel e tinta.
- Muito espaço em branco; grade de 8 px.
- Proibido: gradientes, glassmorphism, ilustrações decorativas, emojis, cartões coloridos, barra colorida à esquerda de cartões (a barra vertical existe só nas falas, na cor do falante).

## Conteúdo e tom

- Português do Brasil, direto, frases curtas. Sem exclamações, sem linguagem de marketing.
- Botões no infinitivo: "Enviar", "Gerar ata", "Baixar", "Nova reunião", "Tentar novamente".
- Rótulos em caixa normal ("Tempo de fala"), nunca em maiúsculas espaçadas.
- Erros dizem o que aconteceu e o que fazer: "Não foi possível transcrever o áudio. Tente novamente."
- Login: erro genérico, sem dizer qual campo errou — "E-mail ou senha incorretos".
- Falantes ainda não nomeados aparecem como "Pessoa 1", "Pessoa 2".
- Textos de referência: "Você pode fechar esta página. A reunião aparece na lista quando estiver pronta." · "Ainda há falantes sem nome. Gerar mesmo assim?" · "O áudio será enviado a um serviço externo para transcrição."

## Cor

- Fundo da página `papel`; documento, campos e modais em `superficie`; barra lateral, hover e linhas alternadas em `superficie-alt`.
- Texto principal `tinta`; apoio e rótulos `tinta-2`; timestamps e placeholders `tinta-fraca`.
- `destaque` / `destaque-hover` para o botão primário, links e item ativo; `destaque-suave` atrás de seleção e avisos neutros. Texto sobre `destaque` é `sobre-destaque` (branco no claro, escuro no escuro).
- Estados: `estado-sucesso`, `estado-processando`, `estado-erro`, `estado-neutro`, cada um sobre o seu `-fundo`. Estado nunca só por cor: sempre texto e, quando couber, ícone (`StatusTag`, `StepList`).
- Falantes: `falante-1` a `falante-8`, só na barra vertical da fala e no ponto da etiqueta; o texto continua em `tinta`. Do 9º falante em diante as cores se repetem com o ponto em contorno. Como os falantes se distinguem também pelo nome, a cor nunca é o único identificador.
- Tema claro é o padrão; o tema escuro troca todos os tokens pelo par `dark`. Use os tokens, nunca os hex.

### Cores do documento da ata

O sistema é neutro; só a ata, que é o documento entregue, usa esta paleta editorial complementar. Ela não depende de identidade institucional externa:

- `scribrief-azul` (`#2E6CB1`): faixa de 3 px no topo do documento, rótulo "Ata de reunião", numeração das decisões.
- `scribrief-marinho` (azul-marinho complementar, `#122357`): título da reunião e títulos de seção da ata, texto do cabeçalho da tabela de tarefas.
- `scribrief-dourado` (`#CB9F35`): só o filete fino sob o cabeçalho do documento; nunca em texto.
- `scribrief-azul-suave`: fundo do cabeçalho da tabela de tarefas.
- Nada disso aparece fora do documento da ata: botões, navegação e estados continuam em `destaque` e nos tokens neutros. Não usar símbolos de terceiros.

### Pontos de atenção de contraste

Na integração de 2026-10-08 foram adotadas as correções propostas abaixo: `tinta-fraca` claro `#6F6B63` e escuro `#8F8A80`; campos usam `borda-controle` claro `#9A9488` e escuro `#7B756B`. O restante da direção visual foi preservado.

Valores do brief mantidos exatos; correções sugeridas para decidir:

- `tinta-fraca` fica abaixo de 4,5:1 — claro 3,3:1 sobre `papel`, 3,6:1 sobre `superficie`, 3,1:1 sobre `superficie-alt`; escuro 3,9:1 sobre `superficie`. Como timestamps são informação, proposta: claro `#6F6B63` (4,9:1 sobre `papel`), escuro `#8F8A80` (4,9:1 sobre `superficie`). Até decidir, não use `tinta-fraca` em texto que o usuário precisa ler para agir.
- `borda` tem 1,4:1 sobre `superficie` nos dois temas: serve para divisórias, mas como contorno de campo fica abaixo de 3:1. O rótulo acima de cada campo é obrigatório para compensar; se quiser contorno visível, um `borda-controle` claro `#9A9488` daria 3:1.
- Branco sobre `destaque` escuro daria 2,2:1, por isso `sobre-destaque` é `#161513` no tema escuro (8,3:1).
- O brief não define estados nem falantes no tema escuro; os valores `dark` desses tokens são propostos aqui: todos passam 6:1 sobre `superficie` escura (texto de estado sobre o próprio fundo, 6,4:1 ou mais).

## Tipografia

- Três famílias do Google Fonts: Source Serif 4 (`--font-serif`) para documento e títulos; IBM Plex Sans (`--font-sans`) para toda a interface; IBM Plex Mono (`--font-mono`) para dados.
- Estilos: `titulo-pagina` 32/40 600 · `titulo-secao` 22/30 600 · `leitura` 18/30 400 (serifa) · `subtitulo` 16/24 600 · `interface` 15/22 400 · `rotulo` 13/18 500 (sans) · `dado-mono` 13/18 400.
- Timestamps, durações, tamanhos de arquivo e IDs sempre em `dado-mono` com `font-variant-numeric: tabular-nums`.
- Texto de leitura nunca passa de `coluna-leitura` (~70 caracteres).

## Espaço e layout

- Espaçamentos só da escala: `space-1` 4 · `space-2` 8 · `space-4` 16 · `space-6` 24 · `space-8` 32 · `space-12` 48 · `space-16` 64.
- Estrutura: barra lateral fixa à esquerda (`barra-lateral`, 240 px, fundo `superficie-alt`, divisória à direita) com "Nova reunião" e a lista de reuniões; área principal com conteúdo até `conteudo-max` (1120 px), centralizado.
- Abaixo de 900 px a barra lateral vira gaveta, aberta pelo ícone `menu`; a tela de transcrição passa o painel Falantes para baixo da coluna.
- Toda área clicável tem no mínimo `controle-altura` (40 px). Linhas de lista no mínimo `linha-lista-altura` (56 px).

## Forma

- Raios: `radius-sm` 4 px (campos, etiquetas de falante, área de upload), `radius-md` 6 px (botões, modais, documento, cartão de login), `radius-pill` só na etiqueta de estado.
- Bordas de 1 px (`linha`) em `borda`. Sem sombras em lugar nenhum; o modal se separa do fundo pela borda e por um véu de `tinta` a 40%.

## Foco e acessibilidade

- Foco de teclado sempre visível: contorno sólido de `foco-largura` (2 px) na cor `foco` (alias de `destaque`) com `foco-afastamento` (2 px). 7:1 ou mais sobre `papel` e `superficie` nos dois temas.
- Texto com 4,5:1 no mínimo (ver pontos de atenção acima).
- A tela de transcrição é toda navegável por teclado: timestamps são botões, nomes de falante são campos, o player tem botão, linha do tempo e seletor.
- Respeite `prefers-reduced-motion`: com ele, o indicador da etapa em andamento para.

## Movimento

- Transições de 120 a 180 ms, apenas em opacidade e cor. Sem animação de entrada de página, sem deslocamentos.
- O único movimento contínuo do produto é o indicador da etapa em andamento (`StepList`).

## Iconografia

- Ícones outline de traço 1,5 px (`icone-traco`), 18 a 20 px (`icone`), em `currentColor` — herdam a cor do texto ao lado. Componente `Icon`; nomes em `Icon.names`.
- O conjunto do sistema é próprio e mínimo (check, alert, clock, upload, download, play, pause, search, copy, close, listen, merge, file, menu, plus, retry, pending, chevron). O brief não escolhe biblioteca; se o produto adotar uma, mantenha traço fino e estilo outline.
- Sem emojis, sem ilustrações, sem ícones grandes em avisos.
- Não há logotipo: o nome do produto aparece em Source Serif 4 600, como texto.

## Componentes

Scribrief (React 18). Ações: `Button`, `ConfirmModal`. Formulários: `TextField`, `Dropzone`. Estado: `StatusTag`, `InlineNotice`, `StepList`. Navegação: `MeetingRow`, `ViewTabs`. Transcrição: `Utterance`, `SpeakerTag`, `SpeakerRow`, `AudioPlayer`. Fundamentos: `Icon`. A composição de cada tela está na seção Telas.
