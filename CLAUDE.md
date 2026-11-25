# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Código, comentários, docstrings e mensagens de commit estão em **português**.
Mantenha esse padrão — inclusive nas mensagens de erro voltadas ao usuário.

## Comandos

Backend (a partir de `backend/`, com a venv ativa):

```bash
pytest -q                                # suíte completa (1186 passed, 1 skipped)
pytest tests/test_kernel.py -q           # um arquivo
pytest tests/test_kernel.py::test_fallback_when_preferred_engine_fails -q   # um teste
ruff check .                             # lint (sem config própria: defaults do ruff)

# API
.venv\Scripts\python.exe -m uvicorn assetflow.main:app --port 8000 \
    --reload --reload-dir assetflow --reload-dir config
```

`ruff check .` tem **154 achados pré-existentes** (nenhuma config própria, então
valem os defaults, bem mais rígidos que o estilo do projeto). Compare com esse
baseline antes de concluir que uma alteração sua introduziu lint novo — e, se
mexer nele, atualize o número aqui: o baseline só serve enquanto estiver certo.

O `--reload-dir` é obrigatório: sem ele o uvicorn vigia `backend/` inteiro, e
`backend/data/` é onde os PNGs gerados são gravados — cada geração reiniciaria
o servidor no meio do próprio job.

**Alteração em `config/*.yaml` exige reiniciar o backend.** O reload do uvicorn
só casa `*.py`, e `config/` não tem nenhum — então `--reload-dir config` não
cobre o que o nome sugere. `--reload-include "*.yaml"` só funciona com o pacote
`watchfiles`, que o projeto não instala. Um servidor rodando configuração velha
não dá nenhum sinal disso; `GET /api/generation/engines/<id>` mostra o que ele
realmente carregou.

Para **olhar** o que uma gaveta produz (os testes escrevem em tmp):

```bash
python scripts/preview_engine.py --engine mock-image-v1 -n 2
python scripts/preview_engine.py --engine mock-image-v1 --profile studio_character
python scripts/preview_engine.py --engine desenhista-v1 \
    --receita assetflow/generation/engines/desenhista/exemplos/pocao_16x16.json \
    --profile pixel_prop_64 --prompt "poção vermelha 16x16"
```

Sempre nomeie a gaveta: o script liga só a gaveta nomeada e gera com ela. A
`desenhista-v1` só gera com `--receita` (um JSON no formato de
[backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md)); com ele, o padrão
passa a ser uma variação.

O benchmark entre motores (`scripts/benchmark_engines.py`) saiu na Fase 0 do
plano desenhista; as métricas de otimização continuam gravadas em todo job.

Frontend (a partir de `frontend/`):

```bash
npm ci          # não `npm install` — reproduz o package-lock
npm run dev     # :5173, com proxy de /api para :8000
npm run build   # tsc -b && vite build
npm run typecheck
```

Instalação completa: veja [SETUP.md](SETUP.md). Não há modelo para baixar nem
GPU para configurar — `pip install -e ".[dev]"` basta.

## Plano em andamento

O projeto está executando o plano
[backend/docs/PLANO_DESENHISTA_MCP.md](backend/docs/PLANO_DESENHISTA_MCP.md),
uma fase por vez, um commit por fase, no branch `desenhista-mcp`. O motor passa
a ser o Claude, por um servidor MCP: a gaveta `desenhista-v1` recebe uma
receita curta e a transforma em sprite na grade lógica. A base de práticas que
vira `config/pixel_knowledge/` está em
[backend/docs/PIXEL_KNOWLEDGE.md](backend/docs/PIXEL_KNOWLEDGE.md). Leia os dois
antes de mexer numa fase.

Feito:

- **Fase 0** (limpeza) — saíram as gavetas de difusão (`diffusers-sdxl-v1`,
  `flux-pixel-v1`), as pontes externas (`sdpixl-v1`, `pixel-forge-v1`), a de
  API paga (`gpt-image-v1`), o benchmark entre motores e o extra `diffusers`
  do `pyproject.toml`. O modo Studio (2D Normal) ficou, dormente: nenhum motor
  real o atende.
- **Fase 1** (gaveta desenhista) — `engines/desenhista/`, id `desenhista-v1`,
  família `agentic`. Recebe a receita em
  `engine_options["desenhista-v1"]["receita"]` e entrega a grade lógica 1:1.
  Formato, espelho por camada, erros e avisos:
  [backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md). O rasterizador
  mora **dentro** da gaveta: o teste de fronteiras proíbe gaveta importar
  `assetflow.pixel`, então o `PixelCanvas` não é reusado.

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

Quatro conceitos que **nunca** se misturam:

```
ENGINE         qual tecnologia/modelo gera uma imagem
POSTPROCESSOR  normaliza/corrige propriedades técnicas do arquivo
OPTIMIZER      revisa o sprite na grade final e corrige pixel a pixel
VALIDATOR      mede e aprova/reprova
```

Os quatro acontecem **sempre**, nesta ordem, e só o primeiro é escolhível. Já
existiu aqui um quinto — `STRATEGY`, "como o asset será criado" —, e ele
descrevia uma bifurcação que não existe: o motor produz a imagem e o Optimizer
corrige a imagem produzida. Ver
[backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md) §1.

Um pipeline **nunca** importa uma gaveta. Ele pede uma **capacidade**
(`text_to_image.pixel`) ao Kernel, que resolve qual motor atende.

### Fluxo de um pedido

```
API (/api/generation/jobs)
  -> GenerationService.submit       resolve o FinalResolvedSpec  <- uma única vez
       AutoEnginePolicy             em "auto", escolhe o MOTOR + o motivo
  -> JobManager + JobQueue          jobs/
  -> GenerationWorker               jobs/worker.py     <- teto job_timeout_s
  -> Pipeline (pixel.character)     generation/pipelines/
       lê o FinalResolvedSpec       generation/spec/  (nunca o reinterpreta)
  -> GenerationKernel               generation/kernel/service.py
       EngineResolver               capability -> cadeia ordenada de candidatos
       fallback automático          se o preferido falhar/estiver indisponível
  -> Engine.generate()              generation/engines/<id>/
  -> Postprocessing                 generation/postprocessing/
       PixelPostProcessor           grade lógica, paleta, alpha binário
       PixelValidator      V1       mede
       AssetFlowPixelOptimizer      revisa e corrige pixel a pixel  <- SEMPRE
       PixelValidator      V2       mede de novo
       PixelAcceptancePolicy        decide, sobre a V2
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
- **`generation/kernel/catalog.py`** — a vitrine: manifesto + estado viram a
  lista que o seletor de motor da interface consome.
- **`generation/kernel/auto_policy.py`** — o que o modo "Automático" prefere,
  a partir de regras em `config/engine_policy.yaml`.
- **`settings.py`** — precedência **env (`ASSETFLOW_*`) > YAML > padrão**.
  Nada de motor/modelo/device/precisão fica hardcoded.

### Do texto ao contrato (`backend/assetflow/generation/spec/`)

Entre a frase que a pessoa escreve e o motor existe **um** objeto, resolvido
uma vez e imutável durante o job: o `FinalResolvedSpec`.

```
Texto do usuário
  -> ExplicitConstraintExtractor   "32x32", "8 cores", "sem fundo"
  -> AssetTypeClassifier           config/asset_taxonomy/*.yaml
  -> ConstraintResolver            precedência oficial
  -> FinalResolvedSpec             contrato do job
```

A precedência é a regra inteira, e ela está escrita uma vez, em
`SPEC_PRECEDENCE` (`schemas/resolved_spec.py`), da menor para a maior:

```
padrão global < profile < inferência < interface < prompt < correção manual
```

**Ninguém recalcula um campo que já existe no spec.** Pipeline,
pós-processamento, validação e interface leem; nenhum deles reinterpreta o
prompt nem volta a consultar o profile por resolução lógica, paleta, fundo ou
tipo de asset. Foi a ausência dessa regra que produzia os dois defeitos que o
módulo existe para fechar: `tree` virando `character` (o tipo vinha do profile,
não do sujeito) e 32×32 virando 64×64 (cada camada perguntava ao profile em um
momento diferente).

Três consequências práticas ao mexer aqui:

- **O spec é resolvido no `GenerationService.submit`** e viaja dentro do `Job`.
  O worker não resolve nada: ele repassa `job.resolved_spec`. Resolver de novo
  no worker reabriria a porta que o plano fechou.
- **Nada é corrigido em silêncio.** Pedido impossível vira
  `InvalidGenerationRequest` com a razão em português — e essa mensagem é a
  única do backend que a interface exibe crua, porque é escrita para ser lida.
- **A taxonomia é configuração.** Acrescentar "candelabro" ao vocabulário de
  props é editar `config/asset_taxonomy/prop.yaml`, nunca um `.py`. Nos arquivos,
  `markers` (termos que nomeiam o tipo — "tileset", "fundo") ganham de
  `keywords` (termos que nomeiam o sujeito — "grass", "espada"): é o que faz
  "grass tileset" ser um tileset.

Três eixos que **nunca** se colapsam, e o terceiro é novo (pesquisa PixelLab):

```
asset.type            que papel cumpre no jogo   ->  character
asset.category        que tipo de coisa é        ->  creature
character.body_type   que forma o corpo tem      ->  quadruped
```

Um goblin é `creature` de corpo humanoide; um lobo, `creature` quadrúpede. Sem
o terceiro, o motor desenha o lobo em pé — o mesmo erro que fazia uma árvore
virar `character`, um nível abaixo. O vocabulário está em
`config/asset_taxonomy/character.yaml`, seção `body_types`.

E cada campo declara **o que o AssetFlow promete sobre ele** (`SPEC_CONSTRAINTS`,
ao lado de `SPEC_PRECEDENCE`): `hard` é garantido e reprova; `semantic` é medido;
`style` é orientação que o Optimizer melhora; `engine_hint` não tem promessa
visual. A precedência diz de onde veio o valor; a classe diz o que acontece se o
resultado não bater com ele. Sem as duas, a tela mostra "32×32" e "contorno
seletivo" com o mesmo peso.

Os testes permanentes dos dois bugs estão em `tests/test_resolved_spec.py`.
Detalhes em [backend/docs/RESOLVED_SPEC.md](backend/docs/RESOLVED_SPEC.md) — é
o documento que as docstrings citam como `plano T→J §N`.

### Seleção de motor

A tela pergunta **uma** coisa de tecnologia: com qual motor. A pessoa escolhe —
**Automático** ou uma das gavetas visíveis no catálogo — e a escolha é
respeitada. Quatro regras organizam isso:

1. **motor escolhido é motor usado.** Não podendo atender, o job falha dizendo
   por quê; nunca vira outro em silêncio;
2. **fallback só em `auto`**, ou quando alguém pediu explicitamente — em
   seleção manual, `allow_fallback` nasce `False`;
3. **a resposta mostra os três**: motor pedido, motor usado, versão e modelo;
4. a decisão vira o campo **`engine` do `FinalResolvedSpec`**, resolvido por
   precedência como qualquer outro campo — e nenhuma camada posterior a
   reabre.

Em `auto`, quem responde é a `AutoEnginePolicy` (`config/engine_policy.yaml`):
regras por tipo de asset, tamanho lógico, paleta e qualidade, cada uma com um
**motivo em português** que a tela exibe antes de gerar. Ela sugere, nunca
obriga: um motor preferido que caia é substituído pelo fallback, porque em
`auto` ninguém tinha escolhido.

**Estado atual (depois da Fase 1):** as gavetas são `desenhista-v1` (habilitada,
visível no catálogo) e as de referência, `mock-image-v1` (habilitada) e
`mock-pixel-alt-v1` (desabilitada), ambas `catalog.hidden`. No modo Pixel Art,
o seletor da tela mostra "Automático" e "Desenhista (Claude via MCP)". A regra
geral `pixel_geral` do `engine_policy.yaml` prefere a desenhista em todo
pedido Pixel Art.

A desenhista só atende quem manda **receita**, e a tela não manda. Por isso:
escolhida à mão na tela, ela falha com a mensagem em português (motor
escolhido é motor usado); em "Automático", ela recusa e o fallback cai nos
mocks em desenvolvimento — fora dele não há mocks, e a mensagem chega à tela.

**Gaveta sem seed não vira lotes.** O kernel divide um pedido em lotes pelo
`max_variations` da gaveta, variando a seed. Para uma gaveta com
`supports.seed: false`, isso só copiaria a imagem: o kernel recusa o pedido
acima do limite com `InvalidGenerationRequest`, antes de carregar a gaveta
(`kernel/service.py`, `_run_candidate`). A regra lê o manifesto; nenhum id é
citado.

**O frontend continua sem conhecer motor**: a lista vem de
`GET /api/generation/engines/catalog`, com nome, resumo, selos e
disponibilidade. Nenhum id está escrito no React — é o que faz uma gaveta nova
aparecer no seletor sozinha.

Detalhes, incluindo como acrescentar a próxima gaveta:
[backend/docs/ENGINES.md](backend/docs/ENGINES.md).

### Pixel Optimizer (`backend/assetflow/pixel/optimizer/`)

Depois que o motor gera e o pós-processamento reduz para a grade, **toda**
geração Pixel Art passa pelo `AssetFlowPixelOptimizer`: ele revisa o sprite na
resolução lógica real e corrige o que tiver correção segura — pixel órfão,
contorno esfarelado, cor fora do orçamento.

Ele **não é escolhível**, e a ausência é a arquitetura. O AssetFlow já teve um
seletor de "método de criação" com "Modelo de imagem" e "Agente Pixel" lado a
lado, e os dois não são alternativas: o motor produz a imagem, o Optimizer
corrige a imagem produzida. Não há campo no pedido para desligá-lo, não há
controle na tela e não existe um `if engine ==` em lugar nenhum — o estágio
mora dentro da ilha Pixel Exact, e nenhuma gaveta decide o que acontece depois
de devolver a imagem.

Três regras que valem ao mexer aqui:

- **sempre na grade real.** Reparar em 1024px e reduzir depois devolveria o
  problema pela porta por onde ele entrou;
- **preservar é uma decisão registrada.** Um pixel isolado pode ser um olho: se
  a cor dele aparece em quantidade no sprite, ele é vocabulário do desenho e
  fica — com o motivo escrito em `RepairPlan.declined`;
- **otimizar não pode piorar.** Se a nota cai, a correção é descartada e o
  sprite original volta.

Configuração em `config/optimizer.yaml` (teto de iterações, revisor,
interruptor de instalação). Detalhes em
[backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md).

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

- `engines.yaml` — quais gavetas existem (allowlist) e como cada uma é
  configurada: `desenhista-v1` e as duas de referência.
- `profiles.yaml` — Generation Profiles: descrevem **o que** produzir
  (resolução lógica, paleta, variações), nunca **com qual motor**.
- `pixel_profiles.yaml` — contratos Pixel Exact (`PixelOutputSpec`): fonte dos
  valores concretos dos profiles oficiais. Um `pixel_profile` do
  `profiles.yaml` aponta para um bloco daqui. Defaults conservadores ainda
  existem nos modelos para compatibilidade com profiles antigos sem essa
  referência.
- `capabilities.yaml` — catálogo descritivo, não restritivo. Com o modo
  "Automático", ele é o **último recurso**: quem responde primeiro é
  `engine_policy.yaml`.
- `engine_policy.yaml` — as regras do motor no modo "Automático" (plano de
  motores §16): tipo + tamanho + paleta → motor preferido + motivo. Ausente
  ou sem regras, `auto` volta a ser só o
  roteamento por capacidade.
- `optimizer.yaml` — o estágio que **toda** geração Pixel atravessa (plano
  Optimizer §33 e §42): teto de iterações, revisor e o interruptor de
  instalação. Não há aqui uma chave por pedido: a otimização não é opção de
  quem pede. `enabled: false` é para diagnóstico, e o job registra `disabled`.
- `asset_taxonomy/*.yaml` — vocabulário semântico por tipo de asset, em
  português e inglês. Um arquivo por tipo; o nome do arquivo não importa, o
  campo `type:` sim. Diretório ausente não quebra o boot: o classificador
  emudece e o tipo do profile volta a prevalecer.

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
falhadas. Uma gaveta que precise de entrada própria para gerar (a desenhista
precisa de receita) põe um `exemplo_contrato.json` ao lado do manifesto: o
conteúdo vira `engine_options[<id>]` no pedido do contrato.

### Frontend

React 18 + Vite + TS. A interface conhece **Pixel Art** e **2D Normal** e mais
nada — esses rótulos viram capacidades em `src/types.ts`.

Sobre motores, a regra mudou de forma e não de espírito: a tela **oferece** a
escolha (seletor + resumo de cada motor + "Motor resolvido: X, motivo Y" no
automático), mas continua sem **conhecer** motor nenhum. Tudo vem de
`GET /api/generation/engines/catalog`, e nenhum id de motor está escrito no
frontend — se estivesse, cada gaveta nova exigiria uma alteração aqui. Além deles ela mostra
o `FinalResolvedSpec` que o backend devolve: o painel "O que o AssetFlow
entendeu" tem a aba **Interpretação** (o contrato em português, com a origem de
cada valor) e a aba **JSON final** (o mesmo objeto, editável). Editar ali vira
`spec_overrides` — correção manual, o nível mais alto da precedência. Os
controles de tipo/resolução/paleta/fundo viram `output`, o nível da interface;
um controle em "Automático" **não envia campo nenhum**, e é assim que o
classificador e o profile continuam podendo responder. Nenhum componente
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
  e, em instalações anteriores à Fase 0, o cache de modelos (vários GB) moram
  lá. Nunca faça `rmtree` na pasta toda.
- **Diferenças de hardware vão em env var, não no YAML.** `engines.yaml` é
  versionado e compartilhado; editar direto gera conflito de merge a cada pull.
  Além de `ASSETFLOW_ENGINES_ENABLED`/`_DISABLED`, as **opções** de cada gaveta
  entram por `ASSETFLOW_ENGINE_<ID>_OPTIONS` como JSON (id em maiúsculas, `-`
  vira `_`), com merge por chave sobre o YAML. É assim que entra tudo o que
  muda de máquina para máquina (caminhos, limites):

  ```bash
  ASSETFLOW_ENGINE_MOCK_IMAGE_V1_OPTIONS='{"simulated_latency_ms": 0}'
  ```
- **Credencial nunca vai no YAML.** Uma gaveta que precise de chave lê do
  ambiente, e o `engines.yaml` guarda no máximo o **nome** da variável. O
  caminho do desenhista não usa chave nenhuma.
- **`ASSETFLOW_APP_ENV=production` remove as gavetas de referência.** Os
  mocks declaram `catalog.dev_only` e deixam de ser **registrados** fora de
  desenvolvimento — não são apenas escondidos. Em produção sobra só a
  `desenhista-v1`, que exige receita: um "Gerar" da tela falha com a mensagem
  dela, e não existe um caminho alternativo que desenhe sozinho — o Pixel
  Optimizer corrige o que um motor produziu. O padrão é `development`.
- **A suíte roda com as gavetas de referência, não com as entregues.** O
  `container` de teste desabilita tudo fora de `REFERENCE_ENGINES`
  (`tests/conftest.py`). A maior parte dos testes exercita *mecanismo* —
  roteamento, troca de motor, fallback — e mecanismo se testa com motores
  previsíveis; amarrá-los ao conjunto que o projeto por acaso entrega
  habilitado os quebraria a cada gaveta nova. Um teste que precise de uma
  gaveta de produto a habilita pelo nome (`container.registry.enable(...)`).
- **O que o `FinalResolvedSpec` já resolveu não se resolve de novo.** Ler
  `profile.output.logical_width` dentro do pipeline, do pós-processamento ou da
  validação é reintroduzir o bug do 32×32: o profile é só uma das seis camadas,
  e a mais fraca depois do padrão global. O caminho é `context.resolved`.
- **Com `pixel_profile` declarado, o profile Pixel é a fonte única da verdade
  técnica** — *de partida*. O `FinalResolvedSpec` do job entra por cima dele
  (resolução lógica, paleta e fundo) em `postprocessing/pixel/spec.py`, que é o
  único ponto onde isso acontece. Mexer em `output.logical_*` ou `palette.size` só no `profiles.yaml`
  não muda um pixel do arquivo gerado — muda apenas a vitrine da API
  (`GET /api/generation/profiles`). O que vale é o bloco correspondente em
  `pixel_profiles.yaml`; mude os dois juntos (existe teste para essa
  coerência).
