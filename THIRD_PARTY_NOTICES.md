# Avisos de terceiros — Scribrief (candidato beta)

O código original do Scribrief é licenciado sob `AGPL-3.0-only` conforme `LICENSE`.
Copyright (C) 2026 Arthur Gonçalves e contribuidores, na medida dos direitos que detenham.
O pacote candidato **ainda não é uma certificação jurídica** de proveniência completa.

## Fontes distribuídas com o frontend

O frontend carrega fontes locais, sem chamada do navegador ao Google Fonts:

| Fonte/pacote | Versão | Licença | Aviso integral |
|---|---:|---|---|
| IBM Plex Sans (`@fontsource/ibm-plex-sans`) | 5.3.0 | SIL OFL 1.1 | `third_party_licenses/IBM_Plex_Sans.OFL.txt` |
| IBM Plex Mono (`@fontsource/ibm-plex-mono`) | 5.3.0 | SIL OFL 1.1 | `third_party_licenses/IBM_Plex_Mono.OFL.txt` |
| Source Serif 4 (`@fontsource/source-serif-4`) | 5.3.1 | SIL OFL 1.1 | `third_party_licenses/Source_Serif_4.OFL.txt` |

Os avisos de copyright originais estão nos textos OFL acima. O design usa ícones SVG desenhados em código, não arquivos de ícones ou imagens de terceiros no ZIP do frontend recebido.

## Bibliotecas, imagens e binários

- React, React DOM, React Router, jsPDF e html2canvas: MIT (versões exatas em `frontend/package-lock.json`).
- Django, DRF, Celery, OpenAI SDK e demais pacotes Python: versões e hashes em `backend/requirements.txt`; licenças por pacote devem ser preservadas nas distribuições que incluírem suas cópias.
- Valkey: BSD-3-Clause; PostgreSQL: PostgreSQL License; Nginx: BSD-2-Clause; Python: PSF License. As imagens de contêiner incluem pacotes adicionais e respectivas licenças.
- FFmpeg é instalado do Debian **durante o build local** da imagem backend; o repositório de código-fonte não inclui o executável. A imagem candidata examinada em 2026-10-22 contém FFmpeg 7.1.5 do Debian, compilado com `--enable-gpl` (portanto, FFmpeg sob GPL v2 ou posterior, não apenas LGPL). O Scribrief o chama como processo externo por argumentos de linha de comando; não incorpora seu código. Publicar somente o repositório-fonte com o Dockerfile não equivale a distribuir esse binário. **Se imagens Docker pré-construídas forem distribuídas**, incluir avisos/licenças e cumprir a oferta do código-fonte correspondente ao FFmpeg e às demais dependências incluídas, observando a versão/binário exatos. Veja [FFmpeg Legal](https://www.ffmpeg.org/legal.html), [licença do FFmpeg](https://ffmpeg.org/doxygen/trunk/md_LICENSE.html) e [fontes Debian](https://sources.debian.org/copyright/license/ffmpeg/).

Este resumo **não substitui** um SBOM/licence scan das imagens finais nem os avisos completos dos pacotes transitivos. O titular Arthur Gonçalves confirmou que pode publicar o frontend recebido como open source; isso registra a autorização, não uma verificação independente da origem de cada trecho. Antes de publicar, conferir a árvore final e os segredos; antes de **distribuir imagens pré-construídas**, conferir também licenças/fontes dos binários incluídos. O pacote fonte não inclui `node_modules` nem `.venv`.
