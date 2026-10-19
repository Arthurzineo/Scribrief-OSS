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
- FFmpeg é instalado pelo Debian na imagem backend. Sua configuração e a presença de componentes GPL/LGPL devem ser verificadas por build; entregar imagens/binários exige acompanhar as obrigações de licença e fonte correspondentes. Veja [FFmpeg Legal](https://www.ffmpeg.org/legal.html).

Este resumo **não substitui** um SBOM/licence scan das imagens finais nem os avisos completos dos pacotes transitivos. Antes de tornar o repositório público ou distribuir imagens pré-construídas, conferir a árvore final, todas as licenças e a proveniência do frontend. O pacote fonte construído localmente não inclui `node_modules` nem `.venv`.
