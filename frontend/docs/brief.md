# Brief de design: frontend do sistema de transcrição e ata de reuniões

## O que é o produto

Aplicação web onde o usuário faz login, envia a gravação de uma reunião (áudio ou vídeo), recebe a transcrição separada por falante, troca "Pessoa 1, Pessoa 2" pelos nomes reais e, se quiser, gera uma ata com resumo executivo, ata, decisões e tarefas pendentes.

- Público: profissionais que participam de reuniões e precisam registrar o que foi decidido.
- Uso principal: desktop. Precisa funcionar em celular, mas a leitura e edição da transcrição é pensada para tela grande.
- Idioma da interface: português do Brasil.

## Direção visual

A ideia central: **o produto entrega um documento**. A interface deve parecer uma mesa de trabalho editorial, calma e legível, e não um painel de SaaS cheio de cartões e gradientes.

- Fundo com tom de papel, texto em tom de tinta, uma única cor de destaque.
- Muito espaço em branco, linhas finas no lugar de sombras.
- Conteúdo longo (transcrição e ata) em coluna de leitura estreita, com tipografia serifada.
- Controles e navegação discretos, em sans-serif.
- Sem gradientes, sem glassmorphism, sem ilustrações decorativas, sem emojis.
- Cantos pouco arredondados (4 a 6 px). Bordas de 1 px.

Palavras-chave: sóbrio, editorial, confiável, silencioso.

## Cores

### Tema claro (padrão)

| Papel | Hex | Uso |
|---|---|---|
| Papel | `#F7F5F0` | Fundo da página |
| Superfície | `#FFFFFF` | Área de documento, campos, modais |
| Superfície alternativa | `#EFECE5` | Barra lateral, linhas alternadas, hover |
| Borda | `#DDD8CE` | Divisórias e contornos |
| Tinta | `#1C1B19` | Texto principal |
| Tinta secundária | `#5C5952` | Texto de apoio, rótulos |
| Tinta fraca | `#8A867D` | Timestamps, placeholders |
| Destaque | `#0F5C4D` | Botão primário, links, foco, item ativo |
| Destaque hover | `#0B4539` | Hover e pressionado do destaque |
| Destaque suave | `#E3EFEB` | Fundo de seleção e de avisos neutros |

### Tema escuro

| Papel | Hex |
|---|---|
| Papel | `#161513` |
| Superfície | `#1F1E1B` |
| Superfície alternativa | `#2A2825` |
| Borda | `#3A3733` |
| Tinta | `#ECE9E2` |
| Tinta secundária | `#B0ABA1` |
| Tinta fraca | `#7F7A71` |
| Destaque | `#5FBFA8` |
| Destaque hover | `#7FD0BC` |
| Destaque suave | `#1D332E` |

### Cores de estado

| Estado | Texto | Fundo | Uso |
|---|---|---|---|
| Sucesso | `#2E6B3A` | `#E6F1E7` | Transcrição concluída, ata pronta |
| Processando | `#8A5A0B` | `#FBF0D9` | Extraindo áudio, transcrevendo, gerando ata |
| Erro | `#A1302B` | `#FBE9E7` | Falha no upload ou no processamento |
| Neutro | `#5C5952` | `#EFECE5` | Enviado, aguardando |

Estado nunca é comunicado só por cor: sempre com texto e, quando couber, ícone.

### Cores dos falantes

Cada falante recebe uma cor fixa, usada em uma barra vertical fina à esquerda da fala e na etiqueta do nome. O texto da fala continua em Tinta.

| Falante | Hex |
|---|---|
| 1 | `#0F5C4D` |
| 2 | `#B4532A` |
| 3 | `#3B5BA5` |
| 4 | `#8A5A0B` |
| 5 | `#7A3E8E` |
| 6 | `#3F6B2A` |
| 7 | `#A1305A` |
| 8 | `#4A5560` |

A partir do nono falante, as cores se repetem com a etiqueta em contorno em vez de preenchida.

## Tipografia

Todas disponíveis no Google Fonts.

| Família | Uso |
|---|---|
| **Source Serif 4** | Títulos de página, texto da transcrição, texto da ata |
| **IBM Plex Sans** | Interface: botões, menus, formulários, tabelas, rótulos |
| **IBM Plex Mono** | Timestamps, duração, tamanho de arquivo, IDs |

### Escala

| Estilo | Família | Tamanho / altura de linha | Peso |
|---|---|---|---|
| Título de página | Source Serif 4 | 32 / 40 | 600 |
| Título de seção | Source Serif 4 | 22 / 30 | 600 |
| Subtítulo | IBM Plex Sans | 16 / 24 | 600 |
| Texto de leitura | Source Serif 4 | 18 / 30 | 400 |
| Texto de interface | IBM Plex Sans | 15 / 22 | 400 |
| Rótulo | IBM Plex Sans | 13 / 18 | 500 |
| Dado mono | IBM Plex Mono | 13 / 18 | 400 |

- Coluna de leitura com largura máxima de cerca de 70 caracteres (por volta de 680 px).
- Rótulos em caixa normal, sem letras maiúsculas com espaçamento.
- Números de timestamps com algarismos tabulares.

## Espaçamento e layout

- Grade de 8 px. Espaçamentos: 4, 8, 16, 24, 32, 48, 64.
- Estrutura geral: barra lateral fixa à esquerda (240 px) com a lista de reuniões e o botão "Nova reunião"; área principal à direita.
- Em telas menores que 900 px, a barra lateral vira gaveta.
- Largura máxima da área de conteúdo: 1120 px, centralizada.

## Telas

### 1. Login

- Fundo Papel, cartão central estreito (400 px) em Superfície com borda fina.
- Nome do produto em Source Serif 4, uma linha de descrição, campos de e-mail e senha, botão "Entrar".
- Mensagem de erro genérica ("E-mail ou senha incorretos"), sem revelar qual dos dois está errado.
- Sem imagem lateral, sem ilustração.

### 2. Lista de reuniões (tela inicial)

- Título "Reuniões" e botão primário "Nova reunião".
- Lista em linhas, não em cartões. Cada linha: título, data, duração (mono), número de falantes, etiqueta de estado.
- Busca por título e filtro por estado.
- Estado vazio: uma frase e o botão "Enviar a primeira gravação".

### 3. Nova reunião (upload)

- Campo de título e data.
- Área de arrastar e soltar grande, com borda tracejada: "Arraste um arquivo de áudio ou vídeo, ou clique para escolher".
- Linha de apoio com formatos aceitos e tamanho máximo.
- Depois de escolher: nome do arquivo, tamanho (mono), barra de progresso do envio e botão "Cancelar".
- Aviso curto de privacidade: o áudio será enviado a um serviço externo para transcrição.

### 4. Processamento

- Lista vertical de etapas, com a atual destacada:
  1. Arquivo recebido
  2. Extraindo áudio
  3. Transcrevendo
  4. Transcrição pronta
- Cada etapa mostra concluída, em andamento ou pendente. A etapa em andamento tem indicador de atividade discreto.
- Texto: "Você pode fechar esta página. A reunião aparece na lista quando estiver pronta."
- Em caso de erro: mensagem clara do que falhou e botão "Tentar novamente".

### 5. Transcrição e falantes (tela principal do produto)

Duas colunas.

**Coluna de leitura (principal)**

- Cabeçalho com título da reunião, data e duração.
- Falas em blocos: barra vertical na cor do falante, etiqueta com o nome, timestamp em mono à direita, texto em Source Serif 4.
- Falas seguidas do mesmo falante ficam agrupadas sob uma única etiqueta.
- Clicar no timestamp posiciona o player de áudio naquele ponto.
- Texto da fala editável ao clicar, para corrigir erros de transcrição.
- Player de áudio fixo no rodapé da coluna: tocar/pausar, linha do tempo, velocidade.

**Painel lateral "Falantes"**

- Uma linha por falante: ponto colorido, campo de texto com o nome atual ("Pessoa 1"), tempo total de fala (mono).
- Botão "Ouvir trecho" em cada falante, para o usuário reconhecer a voz antes de nomear.
- Ao editar o nome, a mudança aparece na hora em todas as falas.
- Opção "Unir com outro falante" para quando a mesma pessoa foi identificada duas vezes.
- Ações no fim do painel: "Baixar transcrição" (secundário) e "Gerar ata" (primário).
- Se ainda houver falantes com nome genérico ao clicar em "Gerar ata", mostrar confirmação: "Ainda há falantes sem nome. Gerar mesmo assim?"

### 6. Ata

- Abas ou alternador no topo da reunião: "Transcrição" e "Ata".
- Enquanto gera: mesma linguagem visual da tela de processamento, com uma etapa só.
- Ata pronta, em coluna de leitura com aparência de documento (Superfície sobre Papel), com quatro seções:
  1. **Resumo executivo**: um ou dois parágrafos.
  2. **Ata**: texto corrido com os pontos discutidos.
  3. **Decisões**: lista numerada.
  4. **Tarefas pendentes**: tabela com colunas Tarefa, Responsável e Prazo.
- Todas as seções editáveis.
- Ações: "Baixar" (Markdown ou PDF), "Copiar" e "Gerar novamente" (com confirmação, pois substitui a ata atual).

### 7. Conta

- Nome, e-mail, troca de senha, alternador de tema claro/escuro, botão "Sair".

## Componentes

- **Botão primário**: fundo Destaque, texto branco, altura 40 px, raio 6 px.
- **Botão secundário**: fundo transparente, borda 1 px Borda, texto Tinta.
- **Botão destrutivo**: texto e borda na cor de Erro; fundo de Erro só na confirmação.
- **Campo de texto**: fundo Superfície, borda 1 px Borda, rótulo acima do campo, altura 40 px.
- **Etiqueta de estado**: pílula pequena com texto e fundo das cores de estado.
- **Etiqueta de falante**: ponto colorido e nome em IBM Plex Sans 13 / 500.
- **Linha de lista**: altura mínima 56 px, divisória inferior, hover em Superfície alternativa.
- **Modal de confirmação**: Superfície, borda fina, título, uma frase, dois botões.
- **Aviso em linha**: faixa com fundo de estado e texto curto, sem ícones grandes.
- **Ícones**: traço fino (1,5 px), estilo outline, tamanho 18 a 20 px.

## Acessibilidade

- Contraste mínimo de 4,5:1 para texto.
- Foco de teclado sempre visível: contorno de 2 px na cor Destaque com 2 px de afastamento.
- Toda a tela de transcrição navegável por teclado, incluindo edição de nomes e player.
- Áreas clicáveis com pelo menos 40 px de altura.
- Respeitar `prefers-reduced-motion`.

## Movimento

- Transições curtas (120 a 180 ms), apenas em opacidade e cor.
- Sem animações de entrada de página.
- O único movimento contínuo é o indicador da etapa em andamento.

## Tom dos textos

- Direto e em frases curtas. Verbos no infinitivo nos botões: "Enviar", "Gerar ata", "Baixar".
- Erros dizem o que aconteceu e o que fazer: "Não foi possível transcrever o áudio. Tente novamente."
- Sem exclamações e sem linguagem de marketing.

## O que entregar

1. Tela de login
2. Lista de reuniões (com dados e vazia)
3. Nova reunião (antes e durante o envio)
4. Processamento (em andamento e com erro)
5. Transcrição e falantes
6. Ata pronta
7. Versão em tema escuro da tela de transcrição