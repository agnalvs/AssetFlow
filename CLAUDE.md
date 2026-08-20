# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Código, comentários, docstrings e mensagens de commit estão em **português**.
Mantenha esse padrão — inclusive nas mensagens de erro voltadas ao usuário.

## Comandos

Backend (a partir de `backend/`, com a venv ativa):

```bash
pytest -q                                # suíte completa (~795 passed, 10 skipped)
pytest tests/test_kernel.py -q           # um arquivo
pytest tests/test_kernel.py::test_fallback_when_preferred_engine_fails -q   # um teste
ruff check .                             # lint (sem config própria: defaults do ruff)

# API
.venv\Scripts\python.exe -m uvicorn assetflow.main:app --port 8000 \
    --reload --reload-dir assetflow --reload-dir config
```

`ruff check .` tem **128 achados pré-existentes** (nenhuma config própria, então
valem os defaults, bem mais rígidos que o estilo do projeto). Compare com esse
baseline antes de concluir que uma alteração sua introduziu lint novo — e, se
mexer nele, atualize o número aqui: o baseline só serve enquanto estiver certo.

O `--reload-dir` é obrigatório: sem ele o uvicorn vigia `backend/` inteiro, e
`backend/data/` é onde os PNGs gerados são gravados — cada geração reiniciaria
o servidor no meio do próprio job.

Para **olhar** o que uma gaveta produz (os testes escrevem em tmp):

```bash
python scripts/preview_engine.py --engine mock-image-v1 -n 2
python scripts/preview_engine.py --engine mock-image-v1 --profile studio_character
```

Sempre nomeie a gaveta. `--engine all` e `--engine config` (o padrão) alcançam
`diffusers-sdxl-v1`, que está `enabled: true` — e a primeira execução baixa
~7GB do HuggingFace. Use-os só quando essa for a intenção.

Frontend (a partir de `frontend/`):

```bash
npm ci          # não `npm install` — reproduz o package-lock
npm run dev     # :5173, com proxy de /api para :8000
npm run build   # tsc -b && vite build
npm run typecheck
```

Instalação completa, incluindo a armadilha do torch CPU-only no Windows: veja
[SETUP.md](SETUP.md).

## Arquitetura

O README.md (986 linhas) é a **especificação do produto**, e o código inteiro
referencia suas seções como `plano §N` em docstrings. Ao mexer em algo marcado
assim, leia a seção citada antes.

### A regra que organiza tudo

O AssetFlow é uma plataforma de geração de assets que **não pode estar acoplada
a nenhuma tecnologia de IA específica**. Toda a estrutura existe para isso:

```
Engine   (gaveta)  sabe -> gerar imagem     conhece SDXL, torch, diffusers
Pipeline           sabe -> gerar asset      conhece Pixel Art, personagem, paleta
```

Um pipeline **nunca** importa uma gaveta. Ele pede uma **capacidade**
(`text_to_image.pixel`) ao Kernel, que resolve qual motor atende.

### Fluxo de um pedido

```
API (/api/generation/jobs)
  -> JobManager + JobQueue          jobs/
  -> GenerationWorker               jobs/worker.py     <- teto job_timeout_s
  -> Pipeline (pixel.character)     generation/pipelines/
       aplica o Generation Profile  generation/profiles/  (config/profiles.yaml)
  -> GenerationKernel               generation/kernel/service.py
       EngineResolver               capability -> cadeia ordenada de candidatos
       fallback automático          se o preferido falhar/estiver indisponível
  -> Engine.generate()              generation/engines/<id>/
  -> Postprocessing                 generation/postprocessing/  (resize, paleta, alpha)
  -> AssetStorageService            storage/
```

Peças-chave:

- **`bootstrap.py`** — composition root, o único módulo que conhece todas as
  peças ao mesmo tempo. Não importa gaveta concreta: elas entram por descoberta
  de `manifest.json`.
- **`generation/kernel/discovery.py`** — acha gavetas pelo manifesto, não por
  `import` escrito à mão. É o que permite somar/remover motores sem tocar em
  código.
- **`generation/kernel/resolver.py`** — capability → `[preferido, fallback, …]`.
- **`settings.py`** — precedência **env (`ASSETFLOW_*`) > YAML > padrão**.
  Nada de motor/modelo/device/precisão fica hardcoded.

### Pixel Exact (`backend/assetflow/pixel/`)

No modo Pixel Art, "parecer Pixel Art" não basta: o asset só é entregue como
Pixel Exact com resolução lógica real, alpha binário, paleta dentro do limite e
validação técnica aprovada. Essa tecnologia mora em `assetflow/pixel/` — na
estante, **fora das gavetas**: ela recebe `(imagem, PixelOutputSpec)` e não
conhece motor, job nem storage. O encaixe com a cadeia de pós-processamento é
o `PixelExactProcessor` (`generation/postprocessing/pixel/exact.py`), a única
peça que conhece as duas pontas. Detalhes em
[backend/docs/PIXEL_EXACT.md](backend/docs/PIXEL_EXACT.md).

### Configuração (`backend/config/`)

- `engines.yaml` — quais gavetas existem, modelo, device, precisão, offload.
  Um profile de hardware ativo + alternativas comentadas.
- `profiles.yaml` — Generation Profiles: descrevem **o que** produzir
  (resolução lógica, paleta, variações), nunca **com qual motor**.
- `pixel_profiles.yaml` — contratos Pixel Exact (`PixelOutputSpec`): fonte dos
  valores concretos dos profiles oficiais. Um `pixel_profile` do
  `profiles.yaml` aponta para um bloco daqui. Defaults conservadores ainda
  existem nos modelos para compatibilidade com profiles antigos sem essa
  referência.
- `capabilities.yaml` — catálogo descritivo, não restritivo.

### Fronteiras verificadas por teste

`tests/test_architecture_boundaries.py` falha o build se alguém acoplar o
sistema a uma tecnologia de IA. Ele proíbe, via AST:

1. Importar `torch`/`diffusers`/`transformers`/`openai`/… fora de
   `generation/engines/<gaveta>/`.
2. Importar uma gaveta concreta de fora de `engines/`.
3. Uma gaveta importar outra gaveta.
4. `engines/__init__.py` importar qualquer gaveta (a estante não depende das gavetas).
5. Kernel e schemas dependerem de camadas superiores (jobs, api, storage).
6. Símbolos de fornecedor (`StableDiffusionXLPipeline`, …) fora das gavetas.

`tests/contract/test_engine_contract.py` gera casos automaticamente a partir
dos manifestos descobertos: **toda gaveta nova é testada sem escrever teste
novo**. Gavetas cujas dependências não estão instaladas são puladas, não
falhadas.

### Frontend

React 18 + Vite + TS. A interface conhece **Pixel Art** e **2D Normal** e mais
nada — esses rótulos viram capacidades em `src/types.ts`. Nenhum componente
sabe o que é um motor; se o backend cair no fallback, a tela não fica sabendo,
continua acompanhando o mesmo `job_id`. Todo acesso à API passa por
`src/services/generationApi.ts` (`BASE_URL = "/api/generation"`, mesma origem,
sem CORS).

O front **não abre por `file://` nem por Live Server**: `main.tsx` é TS+JSX e
os imports são bare specifiers que só o Vite resolve.

## Armadilhas conhecidas

- **`job_timeout_s` (padrão 900s) engole tudo.** O worker envolve o pipeline
  inteiro em `asyncio.wait_for`, e o *carregamento do modelo* acontece dentro
  dessa janela. Os `timeouts` do `engines.yaml` são deadlines internos — se o
  teto do worker for menor, ele mata antes e os valores do YAML nunca são
  atingidos. Ao alargar um, alargue o outro (`ASSETFLOW_JOB_TIMEOUT_S`).
- **`backend/data/` é volátil e ignorado pelo git** — assets gerados, histórico
  e o cache do modelo (vários GB) moram lá. Nunca faça `rmtree` na pasta toda.
- **Diferenças de hardware vão em env var, não no YAML.** `engines.yaml` é
  versionado e compartilhado; editar direto gera conflito de merge a cada pull.
- **Com `pixel_profile` declarado, o profile Pixel é a fonte única da verdade
  técnica.** Mexer em `output.logical_*` ou `palette.size` só no `profiles.yaml`
  não muda um pixel do arquivo gerado — muda apenas a vitrine da API
  (`GET /api/generation/profiles`). O que vale é o bloco correspondente em
  `pixel_profiles.yaml`; mude os dois juntos (existe teste para essa
  coerência).
