# Arquitetura da Infraestrutura de Geração do AssetFlow

Documento de referência da primeira infraestrutura de geração. Explica **por
que** cada peça existe e onde ela vive no código.

Pergunta que guiou cada decisão (plano §73):

> Se amanhã esse modelo desaparecer, consigo substituí-lo sem modificar o
> AssetFlow?

---

## 1. Camadas

```text
┌──────────────────────────────────────────────────────────────┐
│ ASSETFLOW — projetos, usuários, editor, biblioteca, UI       │
└───────────────────────────┬──────────────────────────────────┘
                            │  fala apenas com a fachada
┌───────────────────────────▼──────────────────────────────────┐
│ GenerationService            assetflow/generation/service.py │
│ submit / get_job / cancel / engines / capabilities           │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ JOB SYSTEM                              assetflow/jobs/      │
│ fila, worker, retry, cancelamento, timeout                   │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ ASSET PIPELINE          generation/pipelines/ (produto)      │
│ PromptBuilder → SemanticPrompt → Request → … → PostProcessor │
└───────────────────────────┬──────────────────────────────────┘
                            │  pede uma CAPACIDADE
┌───────────────────────────▼──────────────────────────────────┐
│ GENERATION KERNEL                    generation/kernel/      │
│ validar · resolver · despachar · normalizar · fallback       │
│                                                              │
│   EngineRegistry ─── EngineResolver ─── EngineHandle         │
└───────────────────────────┬──────────────────────────────────┘
                            │  Engine Contract (única interface)
┌───────────────────────────▼──────────────────────────────────┐
│ GAVETAS                              generation/engines/     │
│ mock-image-v1 · mock-pixel-alt-v1 · diffusers-sdxl-v1 · …    │
└──────────────────────────────────────────────────────────────┘
```

Cada seta aponta para baixo. Nenhuma camada inferior conhece a superior — e o
teste `test_architecture_boundaries.py` garante isso continuamente.

---

## 2. Os quatro conceitos que sustentam tudo

### 2.1 Capability — a unidade de roteamento

`assetflow/generation/schemas/capability.py`

O AssetFlow nunca pede "SDXL". Pede `text_to_image.pixel`. Uma capacidade é um
value object imutável `família.variante`, serializado como string no JSON.

O catálogo (`kernel/capabilities.py`) é **descritivo, não restritivo**: ele
documenta o que o produto conhece hoje e alimenta a API, mas uma gaveta futura
pode declarar uma capacidade inédita sem alterar o kernel. Uma lista fechada
ali seria acoplamento na direção contrária.

### 2.2 Engine Contract — o encaixe da gaveta

`assetflow/generation/kernel/contracts.py`

```python
class ImageGenerationEngine(ABC):
    async def initialize(config) -> None
    async def unload() -> None
    def manifest() -> EngineManifest
    def capabilities() -> tuple[Capability, ...]
    async def health_check() -> EngineHealth
    async def generate(request, context) -> EngineGenerationResult
    async def cancel(job_id) -> bool
    def prompt_adapter() -> SemanticPromptAdapter | None      # opcional
```

Uma gaveta recebe `ImageGenerationRequest` (universal) e devolve
`EngineGenerationResult` (normalizado). Ela **não** conhece projeto, usuário,
job, fila ou storage — só isso já elimina a maior parte do acoplamento
possível.

`BaseImageGenerationEngine` existe como conveniência (carrega manifesto,
rastreia jobs ativos). Herdar dela é opcional: `mock-pixel-alt-v1` implementa a
ABC crua justamente para provar que o contrato basta.

### 2.3 Manifest — como uma gaveta é descoberta

`manifest.json` dentro do pacote da gaveta, validado por `EngineManifest`.

O sistema descobre motores varrendo manifestos (`kernel/discovery.py`) e os
instancia via `importlib` a partir do campo `entrypoint`. **Nenhum `import` de
gaveta concreta existe no código do AssetFlow** — nem no `bootstrap`.

Segurança (§64): allowlist de ids em `config/engines.yaml` + prefixo de módulo
permitido + validação estrita do manifesto antes de qualquer import.

### 2.4 Engine API Version — proteção contra o futuro

`engine_api_version: "1"` no manifesto; `SUPPORTED_ENGINE_API_VERSIONS` no
código. Um motor que declare uma versão desconhecida é recusado no registro,
com erro normalizado, em vez de quebrar em runtime. Quando existir a v2, basta
acrescentá-la ao conjunto e as duas gerações coexistem.

---

## 3. Decisões que merecem justificativa

### 3.1 Dois níveis de resultado

| Tipo | Quem produz | O que carrega |
|---|---|---|
| `EngineGenerationResult` | a gaveta (via *Result Mapper*) | bytes + seed + métricas de inferência |
| `GenerationResult` | o kernel | job, motor efetivo, fallback, tempos por etapa |

A gaveta não sabe o que é um job nem uma URI; o kernel não sabe o que é um
tensor. O *Result Mapper* de cada motor (`mapper.py`) é a fronteira exata onde
a tecnologia deixa de existir para o resto do sistema.

### 3.2 `quality` em vez de `steps`

O contrato universal (§20) não pode ter `steps`, `guidance` ou `refiner`: são
conceitos de uma família de modelos. Ele tem um knob abstrato
`quality: draft|standard|high`, e **cada gaveta traduz**:

```python
# engines/diffusers_sdxl/config.py
quality_steps = {"draft": 18, "standard": 30, "high": 45}
```

Um motor de API remota mapearia o mesmo knob para outro parâmetro — ou
ignoraria. Ajustes finos e específicos vão em `engine_options[<engine_id>]`,
que qualquer outro motor simplesmente ignora.

### 3.3 Resolução lógica × resolução de render

Pixel Art não é gerada em 64×64: o motor gera em 512×512 e o **AssetFlow**
reduz ao grid lógico com regras próprias. O profile carrega os dois números;
o motor só vê o de render.

Na redução usamos média de área (`BOX`), não nearest-neighbor: nearest em
*downscale* descarta 63 de cada 64 pixels e destrói a silhueta. A nitidez
característica volta logo depois, na quantização de paleta e no corte de alpha.
Nearest-neighbor é usado onde ele é obrigatório: ao **ampliar** (thumbnails).

### 3.4 O pós-processamento é o produto

O conhecimento do AssetFlow sobre Pixel Art mora em `assetflow/pixel/`:
enquadramento, redução para a resolução lógica, paleta, alpha binário, limpeza
conservadora, validação técnica e política de aceitação.
`generation/postprocessing/pixel/` é só a ponte que liga esse módulo à cadeia
de pós-processamento — veja [PIXEL_EXACT.md](PIXEL_EXACT.md).

Isso é deliberado (§24 e §58): mesmo que um modelo produza Pixel Art
convincente sozinho, o comportamento do produto **não pode** depender do
checkpoint. Trocar o gerador não pode custar a propriedade intelectual.

Medir e reprovar são coisas separadas. Os **hard checks** são objetivos: 27
cores em um profile de 16 reprova `PX-COLOR-001`, o asset sai com
`pixel_exact: false` e status `rejected`, e o relatório diz *esperado <=16,
obtido 23*. Os **indicadores de qualidade** (pixels órfãos, microclusters,
ocupação) nunca reprovam sozinhos: viram aviso e nota. O job termina nos dois
casos — quem decide o que fazer com um asset reprovado é a camada de cima, com
o diagnóstico em mãos.

### 3.5 Prompt fora do motor, dialeto dentro

```text
Pedido humano → PromptBuilder → SemanticPrompt → Request → Engine
                                       │
                                       └→ Prompt Adapter da gaveta
```

O `SemanticPrompt` (§28) é estruturado e independente de tecnologia — é ali que
mora o que o AssetFlow aprendeu sobre personagens, props e Pixel Art. O
adapter que traduz isso para o dialeto de um modelo vive **dentro da gaveta**
(`engines/diffusers_sdxl/prompt_adapter.py`) e some junto com ela.

Quem **aplica** o adapter é o Kernel, imediatamente antes de despachar
(`_apply_prompt_adapter`). Isso concentra a tradução em um ponto só, evita que
cada motor tenha de lembrar de fazê-la, e permite registrar no histórico o
prompt que foi *efetivamente* enviado — sem nunca alterar a representação
semântica, que é o que atravessa a troca de motores.

Uma gaveta sem adapter recebe o texto neutro produzido pelo adapter genérico.

### 3.6 Fallback como comportamento de produto

O resolver devolve uma **cadeia**, não um motor. O kernel percorre a cadeia:
falhou o preferido, marca-o como degradado, tenta o próximo e registra
`fallback_used=True` mais um aviso legível para o usuário (§44).

Isso é o que permite substituir motores em produção sem janela de
indisponibilidade.

### 3.7 Retry pertence ao Job System

O motor apenas classifica o erro (`retryable`); quem decide repetir é a
`RetryPolicy` (§45). Erros determinísticos (request inválido, capacidade
inexistente, motor desabilitado) nunca são repetidos. Depois de um OOM, a nova
tentativa **reduz o lote pela metade** e o modelo é descarregado antes.

### 3.8 Lazy loading e ciclo de vida

Registrar uma gaveta não carrega modelo nenhum. O `EngineHandle` (§35/§36)
controla `REGISTERED → INITIALIZING → READY → BUSY → …`, serializa a
inicialização com lock, aplica timeout de carga e permite `unload()` para
liberar VRAM. `ModelCacheManager` (§37) entra depois, sobre esta base.

---

## 4. Fluxo completo de uma geração

```text
POST /api/generation/jobs
   → GenerationService.submit()        resolve profile, cria Job, enfileira
   → 202 {"job_id", "status": "queued"}          (resposta imediata, §53)

GenerationWorker.run_once()
   → JobManager.start()                          RUNNING, attempt++
   → PixelCharacterPipeline.run()
        → PromptBuilder → SemanticPrompt
        → ImageGenerationRequest (capability: text_to_image.pixel)
        → GenerationKernel.execute()
             → EngineResolver.resolve()          cadeia de candidatos
             → EngineHandle.acquire()            lazy load, BUSY
             → engine.generate()                 ← única chamada ao motor
             → normalização + timings + fallback
        → PostProcessingChain
             → PixelExactProcessor               ponte para `assetflow/pixel/`
                  → PixelPostProcessor           64×64, paleta, alpha binário
                  → PixelValidator               hard checks + qualidade
                  → PixelAcceptancePolicy        approved / warning / rejected
        → AssetStorageService                    logical.png + preview.png +
                                                 palette/processing/validation.json
        → GenerationRecord                       histórico (§41/§42)
   → JobManager.complete()                       COMPLETED

GET /api/generation/jobs/{id}
   → {"status": "completed", "asset": {...}}
```

---

## 5. Observabilidade

Cada geração registra `queue_ms`, `model_load_ms`, `inference_ms`,
`postprocess_ms`, `storage_ms`, `total_ms`, motor, versão do motor, modelo,
revisão, seed, prompts e avisos (§48). É esse registro que, adiante, alimenta o
Engine Benchmark (§49) e permite responder com dados "qual motor é melhor para
Pixel Art?".

No modo Pixel Art o registro vai além do tempo: cada variação guarda contagem
de cores antes e depois, órfãos, microclusters, ocupação, nota de qualidade e
`pixel_exact`. A pergunta que esses números respondem não é "qual motor gera a
imagem mais bonita", e sim **qual motor exige menos correção para virar um
asset tecnicamente válido**. Detalhes em [PIXEL_EXACT.md](PIXEL_EXACT.md).

---

## 6. Mapa: plano → código

| Plano | Onde |
|---|---|
| §6 Engine Kernel | `generation/kernel/service.py` |
| §7 Capability | `schemas/capability.py`, `kernel/capabilities.py` |
| §8 Engine Contract | `kernel/contracts.py` |
| §9 Engine Manifest | `schemas/engine.py`, `engines/*/manifest.json` |
| §10 Engine API Version | `schemas/engine.py` (`SUPPORTED_ENGINE_API_VERSIONS`) |
| §11 Engine Registry | `kernel/registry.py` |
| §12–14 Resolver, prioridade, seleção manual | `kernel/resolver.py`, `config/capabilities.yaml` |
| §15–16 Primeiro motor real | `engines/diffusers_sdxl/` |
| §17 Estrutura de diretórios | `assetflow/generation/` |
| §18 Proibição arquitetural | `tests/test_architecture_boundaries.py` |
| §19–21 Request/Result universais | `schemas/request.py`, `schemas/result.py` |
| §22 Result Mapper | `engines/*/mapper.py` |
| §23–24 Pós-processamento separado | `generation/postprocessing/` |
| §25 Generation Profiles | `generation/profiles/`, `config/profiles.yaml` |
| §26–28 Prompt Builder, adapters, SemanticPrompt | `generation/prompting/`, `schemas/semantic_prompt.py` |
| §29–31 LoRA, IP-Adapter, ControlNet | `EngineSupports`, `ReferenceImage`, `StructuralControl` (previstos) |
| §32–34 Job Queue e workers | `assetflow/jobs/` |
| §35–38 Lifecycle, lazy load, memória | `kernel/lifecycle.py`, `engines/*/loader.py` |
| §39–42 Storage e persistência | `assetflow/storage/` |
| §43–47 Health, fallback, retry, cancel, timeout | `kernel/resolver.py`, `kernel/service.py`, `jobs/` |
| §48 Observabilidade | `schemas/common.py` (`StageTimings`), `storage/records.py` |
| §51–55 API | `assetflow/api/` |
| §56–59 Pipeline Pixel e pós-processamento | `pipelines/pixel/`, `postprocessing/pixel/` |
| Plano Pixel §1–110 Pixel Exact | `assetflow/pixel/`, `config/pixel_profiles.yaml` — ver [PIXEL_EXACT.md](PIXEL_EXACT.md) |
| §60–61 Studio 2D | `pipelines/studio/` |
| §63–65 Plugins e configuração | `kernel/discovery.py`, `config/`, `settings.py` |
| §66–68 Testes de contrato e substituição | `tests/contract/`, `tests/test_engine_swap.py` |
| §69 Mock Engine | `engines/mock_image/` |
| §70 Ordem de implementação | seguida integralmente |

---

## 7. O que ficou de fora (e por quê)

Conforme §72, **não** foram desenvolvidos: animação, spritesheet, tileset
completo, editor avançado, ControlNet, IP-Adapter, treinamento de LoRA,
marketplace, desktop e model manager de usuário.

O que existe é o **encaixe** para todos eles:

- `EngineSupports.lora / controlnet / image_reference / inpainting` já fazem
  parte do manifesto;
- `ReferenceImage` e `StructuralControl` já fazem parte do request universal e
  o resolver já descarta motores que não os suportam;
- `EngineType` prevê `image_editing`, `animation` e `upscaling`;
- o catálogo de capacidades já lista `inpainting.*`, `tileset.pixel`,
  `spritesheet.pixel` e `animation.pixel` como experimentais;
- `PostProcessingChain` aceita novas etapas (cluster cleanup, outline,
  dithering, pixels órfãos) sem alterar pipeline nem motor.

Nenhum desses itens exigirá mudar o Engine Contract.

---

## 8. Próximos passos naturais

1. **Motor real em produção** — instalar `[diffusers]`, habilitar
   `diffusers-sdxl-v1` e comparar com o mock usando o histórico já persistido.
2. **Broker distribuído** — implementar `JobQueue` sobre Redis/Celery e um
   `JobStore` compartilhado (roteiro em `jobs/celery_adapter.py`).
3. **Persistência real** — trocar os repositórios em memória por banco,
   mantendo as interfaces de `storage/repository.py`.
4. **Progresso em tempo real** — publicar `JobEvent` por WebSocket/SSE (§55);
   o log de eventos já é gravado.
5. **Model Cache Manager** (§37) e **Engine Benchmark** (§49), ambos sobre a
   telemetria que já está sendo coletada.
