# AssetFlow — Backend de Geração

Primeira infraestrutura real de geração de imagens do AssetFlow, implementada
segundo o *Plano de Implementação do Primeiro Motor de Geração*.

O produto desta etapa **não é a primeira imagem gerada**. É a arquitetura:

> um sistema de geração independente do modelo utilizado.

---

## A ideia em uma frase

**O AssetFlow é a estante. Os motores são gavetas.**

Nenhuma parte do sistema — frontend, API, jobs, pipelines, editor, biblioteca —
sabe qual tecnologia produz os pixels. Todos falam em **capacidade**
(`text_to_image.pixel`) e recebem um **resultado normalizado**.

```text
Cliente → API → Generation Service → Job Queue → Generation Kernel
                                                      ↓
                                        Registry + Resolver (capability)
                                                      ↓
                        ┌──────────────┬──────────────┬──────────────┐
                     Mock Engine    Pixel Alt      SDXL Engine   Motor futuro
                        └──────────────┴──────────────┴──────────────┘
                                                      ↓
                                            Resultado normalizado
                                                      ↓
                                  Asset Pipeline → Pós-processamento
                                                      ↓
                                            Storage → Projeto
```

---

## Começando

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate no Linux/macOS
pip install -e ".[dev]"

pytest                             # 350 testes sem GPU e sem rede (+8 pulados)
uvicorn assetflow.main:app --reload
```

Documentação interativa da API: <http://127.0.0.1:8000/docs>

Gerar o primeiro asset:

```bash
curl -X POST http://127.0.0.1:8000/api/generation/jobs \
  -H "Content-Type: application/json" \
  -d '{
        "project_id": "project_001",
        "profile": "pixel_character_64",
        "prompt": "young warrior with blue armor",
        "attributes": {"view": "side", "pose": "idle"},
        "output": {"variations": 4}
      }'
# → 202 {"job_id": "job_...", "status": "queued"}

curl http://127.0.0.1:8000/api/generation/jobs/job_...
# → {"status": "completed", "asset": {"variants": [...]}}
```

Por padrão quem gera é a gaveta `mock-image-v1` — sem IA, sem GPU. É
proposital: a arquitetura precisa estar provada **antes** de o modelo entrar
(plano §69).

---

## Estrutura

```text
backend/
├── config/                       # configuração externa — nada hardcoded
│   ├── engines.yaml              # quais gavetas existem e como são configuradas
│   ├── capabilities.yaml         # ordem de preferência por capacidade
│   └── profiles.yaml             # o que gerar (resolução lógica, paleta...)
│
├── assetflow/
│   ├── generation/
│   │   ├── schemas/              # contratos universais (request, result, manifest, job)
│   │   ├── kernel/               # A ESTANTE
│   │   │   ├── contracts.py      #   Engine Contract  ← o arquivo mais importante
│   │   │   ├── capabilities.py   #   catálogo de capacidades
│   │   │   ├── lifecycle.py      #   estados + lazy loading
│   │   │   ├── discovery.py      #   descoberta por manifest.json
│   │   │   ├── registry.py       #   quais gavetas existem
│   │   │   ├── resolver.py       #   qual gaveta atende cada capacidade
│   │   │   └── service.py        #   execução, fallback, timeout, normalização
│   │   ├── engines/              # AS GAVETAS (ver engines/README.md)
│   │   ├── prompting/            # SemanticPrompt, PromptBuilders, adapters
│   │   ├── profiles/             # Generation Profiles
│   │   ├── pipelines/            # lógica de produto (Pixel, Studio, Raw)
│   │   ├── postprocessing/       # regras proprietárias de Pixel Art
│   │   └── service.py            # fachada única do sistema de geração
│   │
│   ├── jobs/                     # fila, worker, retry, cancelamento
│   ├── storage/                  # imagens, thumbnails, metadados, histórico
│   ├── api/                      # FastAPI (casca fina)
│   ├── settings.py               # YAML + variáveis de ambiente
│   └── bootstrap.py              # composition root
│
└── tests/                        # inclui contrato de engine e Swap Engine Test
```

---

## Trocar de motor sem tocar em código

### Ligar/desligar

```yaml
# config/engines.yaml
engines:
  mock-pixel-alt-v1:
    enabled: true
```

ou em runtime:

```bash
curl -X POST /api/generation/engines/mock-pixel-alt-v1/enable
curl -X POST /api/generation/engines/mock-image-v1/disable
```

### Mudar quem atende uma capacidade

```yaml
# config/capabilities.yaml
routing:
  text_to_image.pixel:
    engines:
      - pixel-specialist-v3     # novo motor entra no topo
      - diffusers-sdxl-v1       # antigo vira fallback
```

Fim. Nada muda em frontend, projetos, banco de assets, editor, biblioteca ou
exportação. O teste `tests/test_engine_swap.py` cobra exatamente isso.

### Adicionar uma gaveta nova

Ver [`assetflow/generation/engines/README.md`](assetflow/generation/engines/README.md).

---

## Gavetas instaladas

| id | O que é | Padrão |
|---|---|---|
| `mock-image-v1` | Referência determinística sem IA. Valida a arquitetura inteira sem GPU. | habilitada |
| `mock-pixel-alt-v1` | Implementação independente (não herda nada da primeira). Prova a substituição. | desabilitada |
| `diffusers-sdxl-v1` | Primeira gaveta real (Diffusers/SDXL). | desabilitada |

Para usar a gaveta real:

```powershell
# 1. torch com CUDA — instale ANTES dos extras, do índice certo
pip install "torch==2.6.0" --index-url https://download.pytorch.org/whl/cu126
# 2. o resto
pip install -e ".[diffusers]"        # diffusers, transformers, accelerate
```

A escolha do índice não é livre — depende do seu Python e da sua GPU:

| Índice | Python 3.13 | Pascal (GTX 10xx, `sm_61`) |
|---|---|---|
| `cu121` | ❌ não publica wheels | — |
| `cu124` | apenas torch 2.6.0 | ✅ |
| `cu126` | 2.6 → 2.13 | ✅ na série 2.6 |
| `cu128` | 2.7+ | ❌ suporte removido |

Se sua GPU for Ampere ou mais nova, `pip install torch` sem índice já basta.
Confira depois com:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_arch_list())"
```

```yaml
# config/engines.yaml
engines:
  diffusers-sdxl-v1:
    enabled: true
    model:
      id: stabilityai/stable-diffusion-xl-base-1.0
    device: { type: cuda }
    precision: { type: fp16 }
```

Sem as dependências instaladas, a gaveta continua **listada** na API, reporta
`unavailable` no health check e o resolver usa outra — o sistema não quebra.

### Manter os downloads pesados no disco do projeto

O modelo já vai para o disco do projeto: a gaveta recebe `workspace_dir` da
configuração e o usa como `cache_dir` do Diffusers
(`backend/data/engines/<engine_id>/`).

O que o AssetFlow **não** controla são os caches do pip, do HuggingFace Hub e
o `TEMP` da instalação — todos apontam para o perfil do usuário por padrão.
Antes de instalar o torch, redirecione:

```powershell
. .\scripts\use-local-cache.ps1          # note o ponto: precisa ser dot-sourced
```

```text
PIP_CACHE_DIR          ...\backend\data\cache\pip           (~2,5 GB com torch)
HF_HOME                ...\backend\data\cache\huggingface   (~7 GB por modelo)
TORCH_HOME             ...\backend\data\cache\torch
TMP / TEMP             ...\backend\data\cache\tmp
```

Vale só na janela atual; use `-Persist` para gravar no perfil do usuário.
Tudo cai em `backend/data/`, que é ignorado pelo git — apagar a pasta libera
o espaço inteiro de volta.

---

## API

| Método | Rota | Para quê |
|---|---|---|
| `GET` | `/api/generation/engines` | lista as gavetas e seu estado |
| `GET` | `/api/generation/engines/{id}` | detalhe de uma gaveta |
| `POST` | `/api/generation/engines/{id}/enable\|disable\|reload` | administração em runtime |
| `GET` | `/api/generation/capabilities` | capacidades e quem as atende |
| `GET` | `/api/generation/profiles` | Generation Profiles disponíveis |
| `POST` | `/api/generation/jobs` | cria job (202, resposta imediata) |
| `GET` | `/api/generation/jobs/{id}` | status, progresso e asset |
| `POST` | `/api/generation/jobs/{id}/cancel` | cancelamento cooperativo |
| `GET` | `/api/assets/files/{key}` | download do arquivo gerado |
| `GET` | `/api/assets/history` | histórico de gerações do projeto |
| `GET` | `/api/health` | saúde do backend e das gavetas |

---

## Configuração por ambiente

Todas as variáveis usam o prefixo `ASSETFLOW_` e têm precedência sobre o YAML:

| Variável | Efeito |
|---|---|
| `ASSETFLOW_CONFIG_DIR` / `ASSETFLOW_DATA_DIR` | onde ficam configuração e dados (inclusive o cache dos modelos) |
| `ASSETFLOW_ENGINES_ENABLED` / `ASSETFLOW_ENGINES_DISABLED` | liga/desliga gavetas (lista separada por vírgula) |
| `ASSETFLOW_WORKER_EMBEDDED` | `false` para separar API e worker (recomendado com GPU) |
| `ASSETFLOW_WORKER_CONCURRENCY` | jobs simultâneos por worker |
| `ASSETFLOW_JOB_TIMEOUT_S` / `ASSETFLOW_JOB_MAX_ATTEMPTS` | timeout e retry |
| `ASSETFLOW_QUEUE_ROUTES` | filas por capacidade, ex.: `text_to_image.pixel=generation.pixel` |
| `ASSETFLOW_CORS_ORIGINS` | origens permitidas |

---

## Ver o que o motor está gerando

Os testes provam que o sistema funciona, mas escrevem em diretórios
temporários. Para **olhar** o resultado, use o script de preview:

```bash
python scripts/preview_engine.py                     # a gaveta ligada hoje
python scripts/preview_engine.py --engine all        # compara todas as gavetas
python scripts/preview_engine.py --profile pixel_character_32 -n 4 --seed 7
python scripts/preview_engine.py --profile studio_character \
    --prompt "cartoon knight with a red cape"
```

Ele imprime, por variação, o tamanho lógico, a contagem de cores, a seed, os
tempos por etapa e o **caminho absoluto** do PNG — mais um `_thumb.png`
ampliado, porque 64×64 é pequeno demais para julgar a olho.

Saída em `backend/data/preview/` (ignorado pelo git). Motores indisponíveis
são pulados com o motivo:

```text
── gerando com diffusers-sdxl-v1 ──
  ⊘ indisponível: dependências ausentes: torch, diffusers, transformers
── gerando com mock-image-v1 ──
  #0   64x64  lógico 64x64   14 cores  seed 7
      .../jobs/job_ae98.../000.png
```

Também dá para inspecionar pela API (`uvicorn assetflow.main:app --reload`) —
o job devolve a URI de cada variação e `/api/assets/files/{key}` entrega o PNG.

---

## Testes

```bash
pytest                                       # tudo
pytest -v                                    # nome de cada caso
pytest tests/test_pixel_pipeline.py -v -s    # o que o pós-processamento fez
pytest tests/contract                        # contrato obrigatório de toda gaveta
pytest tests/test_engine_swap.py             # Definition of Done arquitetural
pytest tests/test_architecture_boundaries.py # regras de ouro §73/§74
```

Destaques:

- **`tests/contract/test_engine_contract.py`** — gera casos automaticamente
  para **cada manifesto encontrado**. Uma gaveta nova entra na suíte sozinha;
  se declarar dependências ausentes, é pulada em vez de falhar.
- **`tests/test_engine_swap.py`** — gera um asset com o Engine A, desliga A,
  liga B e gera de novo. Passa somente se nenhum código de negócio mudar.
- **`tests/test_third_party_engine.py`** — escreve uma gaveta "de fora" (com
  tecnologia fictícia e dialeto de prompt próprio) e a encaixa na estante sem
  alterar uma linha do AssetFlow.
- **`tests/test_architecture_boundaries.py`** — analisa a AST de todo o pacote
  e falha se alguém importar `torch`/`diffusers` fora de uma gaveta, importar
  uma gaveta concreta de fora de `engines/`, ou fizer o kernel depender de
  camadas superiores.

---

## Documentação adicional

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisões, camadas e o mapa
  plano → código.
- [`assetflow/generation/engines/README.md`](assetflow/generation/engines/README.md)
  — guia de quem escreve uma gaveta.
