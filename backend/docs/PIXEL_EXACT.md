# Pixel Exact — a tecnologia de Pixel Art do AssetFlow

Documento de referência do módulo `assetflow/pixel/`. Explica **por que** cada
peça existe e onde ela vive no código. Complemento de
[ARCHITECTURE.md](ARCHITECTURE.md), que descreve a infraestrutura de geração:
lá o assunto é *trocar o motor sem tocar no produto*; aqui é *garantir que o
arquivo entregue seja mesmo Pixel Art*.

Pergunta que guiou cada decisão:

> O arquivo que o usuário baixou **é** Pixel Art, ou só **parece** Pixel Art
> quando visto pequeno na tela?

---

## 1. A regra nova: "parecer Pixel Art não é suficiente"

Um modelo de difusão sabe produzir uma imagem 1024×1024 com aparência de
sprite: blocos grandes, cores chapadas, contorno escuro. Aberta no navegador
ela convence. Aberta em um editor de sprites, ela é o oposto do que foi pedido
— milhares de cores, bordas com alpha intermediário, "pixels" de 16×16 pixels
reais que não se alinham a grade nenhuma. Não dá para editar, não dá para
animar, não encaixa em tile, e o alpha parcial vira franja cinza assim que a
engine amplia o sprite.

Por isso o modo Pixel Art do AssetFlow tem um contrato próprio. Um asset só
sai marcado como **Pixel Exact** quando as seis propriedades abaixo são
verdade **no arquivo**, medidas depois de tudo pronto:

```text
1. resolução lógica real       o PNG tem 64×64 pixels, não 512×512
2. 1 pixel lógico = 1 pixel    nenhum "quadradinho" desenhado dentro do PNG
3. paleta controlada           N cores no máximo, ou exatamente as N pedidas
4. alpha binário               o canal alpha só contém 0 ou 255
5. PNG lossless                nenhum formato com perda toca no asset
6. validação técnica aprovada  todos os hard checks obrigatórios passaram
```

Duas consequências dão forma ao módulo inteiro:

- **isso não pode depender do checkpoint.** Mesmo que um modelo passe a
  entregar Pixel Art perfeita sozinho, o AssetFlow continua conferindo e
  corrigindo — senão a propriedade do produto seria propriedade do modelo, e
  trocar de motor custaria a garantia (mesma razão do §24/§58 do plano
  principal).
- **medir e corrigir são coisas diferentes.** Quem corrige não pode ser quem
  aprova; caso contrário, um defeito seria "consertado" no mesmo passo em que
  deveria ser denunciado.

```text
PixelPostProcessor   PODE alterar pixels        (plano Pixel §6)
PixelValidator       NUNCA altera pixels        (plano Pixel §37 e §104)
PixelAcceptancePolicy decide, sem medir nada     (plano Pixel §59)
```

---

## 2. Onde o módulo vive

`assetflow/pixel/` é uma **tecnologia do produto**, não uma gaveta. Ele fica na
estante, ao lado do kernel de geração, e a proibição do plano Pixel §5 e §105
vale para o pacote inteiro: nenhum módulo daqui conhece SDXL, FLUX, diffusers,
`engine_id` ou checkpoint. A assinatura pública é literalmente

```text
(imagem, PixelOutputSpec)  ->  (imagem Pixel Exact, relatórios)
```

Ele nem sabe que existe um motor — o que o torna utilizável fora do pipeline
de geração: pelo endpoint de diagnóstico, por um script de benchmark, por um
editor futuro.

```text
┌──────────────────────────────────────────────────────────────┐
│ PIPELINE DE ASSET            generation/pipelines/pixel/     │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│ PostProcessingChain              generation/postprocessing/  │
│   PixelExactProcessor            .../pixel/exact.py  (ponte) │
│   spec_from_profile              .../pixel/spec.py           │
└───────────────────────────┬──────────────────────────────────┘
                            │  (imagem, PixelOutputSpec)
┌───────────────────────────▼──────────────────────────────────┐
│ PIXEL EXACT                              assetflow/pixel/    │
│   PixelAssetProcessor  ─ fachada          service.py         │
│     PixelPostProcessor ─ estágios         processing/        │
│     PixelValidator     ─ checks/análises  validation/        │
│     PixelAcceptancePolicy ─ decisão       acceptance/        │
│     PreviewGenerator / PixelExporter      preview/, stages/  │
│     PixelProfileRegistry                  profiles/          │
│     imaging.py — as primitivas numpy/PIL de todo mundo       │
└──────────────────────────────────────────────────────────────┘
```

A ponte é `PixelExactProcessor` (`generation/postprocessing/pixel/exact.py`,
~100 linhas) e ela existe para que a dependência ande em um sentido só. Se os
estágios do Pixel fossem espalhados na cadeia genérica, o módulo passaria a
depender de `ImageBuffer`/`PostProcessContext` e deixaria de servir a qualquer
outro consumidor (plano Pixel §68 e §105). A ponte faz três coisas:

1. resolve o `PixelOutputSpec` (`spec_from_profile`) e, se não houver um, se
   declara inaplicável — é o caso do modo Studio, onde a pergunta "isto é
   Pixel Exact?" não faz sentido;
2. chama `PixelAssetProcessor.run()` e devolve a imagem lógica ao buffer;
3. traduz o relatório para o vocabulário de issues do asset: **falha de hard
   check vira `error`, indicador de qualidade vira `warning`** — a distinção do
   plano Pixel §38 sobrevive à tradução.

---

## 3. O fluxo de um asset

```text
Raw Image (bytes do motor)
   │
   ├─ PixelPostProcessor.process(image, spec)        pode alterar pixels
   │     input → canvas → logical_reducer → alpha → palette → cleanup
   │     └→ ProcessingReport   (o que foi feito, etapa por etapa)
   │
   ├─ PixelValidator.validate(logical, spec)         não altera nada
   │     HARD CHECKS      → pixel_exact: true/false
   │     QUALITY ANALYSIS → métricas, avisos e nota
   │     └→ PixelValidationReport
   │
   ├─ (no máximo 1 tentativa extra, com spec endurecido — §61)
   │
   ├─ PixelAcceptancePolicy.decide(report, threshold)
   │     └→ AcceptanceDecision  (APPROVED | QUALITY_WARNING | REJECTED)
   │
   ├─ PreviewGenerator.generate(logical, spec)       ampliação inteira
   ├─ PixelExporter.export(...)                      {nome: bytes}
   │
   └─ AssetStorageService                            NNN.png + NNN_*.png/json
```

### 3.1 Os estágios do PixelPostProcessor

A ordem é a do plano Pixel §8 e nenhuma troca é inocente:

| # | Estágio | O que faz | Por que nesta posição |
|---|---|---|---|
| 1 | `pixel.input_normalizer` | orientação EXIF, RGBA, fundo sólido opcional | tudo depois assume RGBA e orientação final; aqui é **proibido** resize, blur, sharpen ou paleta |
| 2 | `pixel.canvas_normalizer` | acerta o **aspect ratio** recortando/preenchendo — nunca escala | esticar 1024×768 até 64×64 achataria o personagem em 25% |
| 3 | `pixel.logical_reducer` | leva à resolução lógica final (`BOX` para reduzir) | é o marco: **depois daqui nenhum resampling suavizado pode tocar no arquivo** (§20) |
| 4 | `pixel.alpha_normalizer` | corta o alpha em `threshold`: 0 ou 255 | antes da paleta, para que pixel invisível não gaste uma das N cores |
| 5 | `pixel.palette_quantizer` | fixa o conjunto exato de cores (median cut ou paleta travada) | precisa do alpha já binário para enxergar só o que é visível |
| 6 | `pixel.conservative_cleaner` | corrige **só** ruído de altíssima confiança | por último, porque só copia cor de vizinho já dentro da paleta fechada |

`BOX` (média de área) para reduzir e `NEAREST` só para ampliar: reduzir 512→64
com nearest ficaria com 1 de cada 64 pixels e a silhueta passaria a depender do
alinhamento da grade, não do desenho. Ao ampliar não existe informação nova a
inventar — ampliar é replicar.

O `PixelExporter` **não** está na lista de estágios, e isso é proposital: o
contrato de um estágio é `(imagem, contexto) -> imagem`, e o exporter devolve
*bytes*, precisando de relatórios que só existem depois da validação. Colocá-lo
na cadeia faria a camada de processamento depender da camada de validação.

Cada estágio pode se declarar inaplicável (`cleanup.mode: "off"`, por
exemplo). Nesse caso ele entra no `ProcessingReport` como `applied: false` com
`skipped_reason` — **pulado é diferente de não ter acontecido nada**.

### 3.2 A segunda tentativa (plano Pixel §61)

Se a validação reprovar, `PixelAssetProcessor` tenta **uma** correção
adicional, com um spec endurecido, e para. O teto é
`attempts.max_processing_attempts` (padrão 2, máximo 5). Existem exatamente
três endurecimentos, e só para falhas cuja causa é conhecida:

| Falha | Endurecimento | Raciocínio |
|---|---|---|
| `PX-EMPTY-001` | `alpha.threshold = 1` | o sprite veio semitransparente e o corte de alpha apagou tudo |
| `PX-COLOR-001` | `dithering.enabled = false` | dithering espalha cores intermediárias e come o orçamento de paleta |
| `PX-BOUND-001` | `canvas.mode = "contain"` + `trim_transparent = true` | o conteúdo encosta na borda: recortar a caixa do sprite e reencaixar com folga |

Para qualquer outra falha o `_harden_spec` devolve `None` e o laço **para
imediatamente**: repetir com o mesmo spec queimaria uma tentativa para chegar
ao mesmo resultado, e insistir às cegas é o que o plano proíbe.

Detalhe que importa: a revalidação sempre usa o **spec original**, nunca o
endurecido. O contrato a cumprir é o que o profile pediu; o spec endurecido é
só um meio de chegar lá.

### 3.3 A decisão, e o que acontece com um asset reprovado

```text
falha em hard check           -> REJECTED
hard pass e nota >= limiar    -> APPROVED
hard pass e nota <  limiar    -> QUALITY_WARNING
```

`AcceptanceDecision.accepted` cobre `APPROVED` e `QUALITY_WARNING`. Os outros
três estados do plano §58 (`RAW`, `PROCESSING`, `TECHNICALLY_VALID`) descrevem
o ciclo de vida do asset na camada de cima e não saem da política.

**Um asset reprovado não derruba o job.** Ele é gravado, os relatórios são
gravados junto, e `pixel_exact`, `quality_score` e `status` viajam na variação
até a API (`AssetVariant`) e o histórico (`GenerationRecord`). Quem decide o
que fazer é o usuário — o frontend só exibe o selo `PIXEL EXACT ✓` quando
`variant.pixel_exact === true`. Esconder a reprovação seria pior: o operador
perderia justamente a informação que o módulo existe para produzir.

---

## 4. Hard checks — os requisitos objetivos

Falhou um, `pixel_exact = false`. Não existe média que salve (plano Pixel §38 e
§39). Um check **pulado** (`SKIPPED`) não conta como aprovação nem como
reprovação: o profile simplesmente não exigiu aquilo.

| Código | Nome | O que mede | Pulado quando |
|---|---|---|---|
| `PX-DIM-001` | Logical Dimensions | o PNG tem exatamente `logical_size` | `require_exact_dimensions: false` |
| `PX-ALPHA-001` | Binary Alpha | os valores do canal alpha são subconjunto de `{0, 255}` | `require_binary_alpha: false` |
| `PX-COLOR-001` | Maximum Colors | cores únicas **entre pixels opacos** ≤ `max_colors` | `require_palette_limit: false`, ou o profile não define teto de cores |
| `PX-PALETTE-001` | Locked Palette Compliance | toda cor opaca pertence à paleta travada | `require_locked_palette: false`, ou paleta derivada da imagem (`max_colors`) |
| `PX-EMPTY-001` | Non Empty | pixels opacos ≥ `max(min_foreground_pixels, ceil(min_foreground_ratio × canvas))` | `require_non_empty: false` |
| `PX-BOUND-001` | Boundary Clipping | conteúdo opaco encostando na borda do canvas | `boundary_touch: "ignore"` |

Notas que evitam leitura errada do relatório:

- **pixel transparente não é cor.** `PX-COLOR-001` e `PX-PALETTE-001` ignoram o
  RGB que existe atrás de alpha 0: ele é invisível e não pode gastar uma
  entrada da paleta.
- **`PX-EMPTY-001` existe porque o vazio passa em tudo.** Um PNG 64×64
  totalmente transparente tem a dimensão certa, alpha binário e zero cores —
  aprovado em três checks, e inútil.
- **`PX-BOUND-001` só reprova com `boundary_touch: "fail"`.** Com `"warn"` ele
  **passa** e explica na mensagem; o aviso visível para o usuário quem emite é
  o `SpriteOccupancyAnalyzer` (`PX-WARN-BORDER`), porque hard check só aprova
  ou reprova — nunca produz aviso. Um tile *precisa* sangrar até a borda, e por
  isso o profile `pixel_tileset_16` usa `"ignore"`.
- **paleta de projeto não resolvida reprova.** Se o `palette_id` não existe na
  tabela `palettes:`, o registry deixa o spec como está (com um aviso no log) e
  o quantizador cai para o modo AUTO — ou seja, o asset sairia bonito e **sem**
  a paleta do projeto. `PX-PALETTE-001` falha nesse caso, com o `palette_id` no
  relatório. A alternativa — pular o check — transformaria um erro de
  configuração em incoerência visual silenciosa entre personagem, inimigo e
  tile, descoberta meses depois.
- **um check que estoura vira `FAIL`, não exceção.** O validador captura o erro
  e registra a falha — uma imagem estranha não pode derrubar o job.

---

## 5. Análise de qualidade — indicadores, nunca vereditos

Seis analisadores rodam sempre, produzem métricas e podem emitir avisos.
**Nenhum deles reprova nada** (plano Pixel §47).

| Analisador | Mede | Aviso |
|---|---|---|
| `orphan_pixels` | pixels opacos cujos 8 vizinhos têm cor RGB diferente | `PX-WARN-ORPHAN` acima de 2% do sprite |
| `clusters` | componentes conexos **por cor**; fatia deles com 1, 2 ou 3 pixels | `PX-WARN-MICROCLUSTER` acima de 25% |
| `occupancy` | foreground, caixa do conteúdo e contato com a borda | `PX-WARN-OCCUPANCY-LOW`, `-HIGH`, `PX-WARN-BORDER` |
| `palette_usage` | quantos pixels cada cor final pinta; quais cores são raras | `PX-WARN-PALETTE-RARE` |
| `color_redundancy` | pares de cores a distância RGB < 12 (indistinguíveis) | `PX-WARN-COLOR-REDUNDANCY` |
| `outline` | tamanho, cores e fragmentação do contorno | `PX-WARN-OUTLINE-FRAGMENTED` acima de 0,15 |

Nenhum deles corrige o que encontra. Um pixel isolado pode ser um olho, um
brilho especular ou a ponta de uma espada; fundir duas cores parecidas é
alterar a imagem, e alterar a imagem é do outro lado da fronteira do plano §104.

### 5.1 A fórmula da nota

A nota começa em 100 e **desconta**. Cada bloco tem uma franquia (abaixo dela
não há desconto), uma taxa e um teto — o teto impede que um único indicador
ruim zere sozinho a nota de um asset que acerta todo o resto.

| Penalidade | Franquia | Taxa | Teto |
|---|---|---|---|
| `orphan` | ratio 0,01 | 400 | 20 |
| `microcluster` | ratio 0,20 | 100 | 20 |
| `occupancy` | faixa `[min_occupancy, max_occupancy]` do profile | distância normalizada pelo espaço fora da faixa **daquele lado** | 15 |
| `redundancy` | — | 2 por par | 10 |
| `outline` | fragmentação 0,20 | 50 | 10 |
| `rare_colors` | — | 1 por cor rara | 5 |

```text
score = max(0, min(100, floor(100 − Σ penalidades arredondadas)))
```

A soma usa os valores já arredondados para que o relatório **feche**:
`100 - sum(penalties.values())` reproduz a nota, e `penalties` guarda só as
penalidades maiores que zero. O piso é `floor`, não `round`, para que meio
ponto perdido continue sendo um ponto a menos. Como os tetos somam 80, a nota
mínima que a calibração atual produz na prática é 20.

A normalização da ocupação merece a linha extra, porque a escolha óbvia está
errada. Ocupação é uma fração de 0 a 1: abaixo de `min_occupancy` só cabem
`min_occupancy` pontos percentuais de erro, e acima de `max_occupancy` só
cabem `1 - max_occupancy`. Normalizar pela **largura da faixa** — o que o
código fazia até a calibração atual — mede o desvio em um eixo e a régua em
outro, e o teto vira enfeite: com a faixa padrão `[0.05, 0.95]`, um sprite
inteiramente vazio (o pior desvio que pode existir) descontava 0,83 dos 15
pontos. Normalizando pelo espaço do lado violado, a penalidade passa a ser a
fração do desvio máximo possível naquele profile — zero na borda da faixa,
teto no extremo do eixo — e o efeito pretendido continua de pé: o tile do §66,
que exige de 50% a 100%, tem meio eixo para errar embaixo e nenhum em cima,
enquanto o profile de personagem, que aceita a partir de 5%, só chega perto do
teto quem chega perto do vazio.

### 5.2 A nota é experimental — e nunca se mistura com `pixel_exact`

Todos os pesos, franquias e limiares desta seção (e o limiar de aprovação 70)
**nasceram de estimativa, não de medição**. Eles são configuração e constantes
nomeadas em um arquivo só (`validation/scoring.py`) exatamente para poderem ser
recalibrados com o benchmark rodando, sem tocar em nenhum analisador. Por isso
todo relatório carrega `validator_version` e a lista `analyzers`: duas notas só
são comparáveis quando saíram da mesma calibração e dos mesmos analisadores.

E a regra que o plano §57 e §107 chamam de essencial:

```text
pixel_exact    ->  verdade técnica, binária, decidida pelos hard checks
quality_score  ->  indicador estrutural, contínuo, decidido pelo scorer
```

As duas **nunca se somam nem se compensam**. Um asset pode ser
`PIXEL EXACT: sim / QUALITY: 58` — tecnicamente correto e artisticamente
problemático — e outro pode ser `PIXEL EXACT: não / QUALITY: 90` — bonito e
fora da especificação. Juntar as duas em um número só esconderia um erro fatal
atrás de uma média boa e destruiria justamente a informação que o operador
precisa para decidir o que fazer.

---

## 6. Os arquivos gerados por variação

O `PixelExporter` produz um dicionário `{nome: bytes}` na ordem fixa de
`ARTIFACT_NAMES`; quem grava é o `AssetStorageService`. Para a variação de
índice `N`, tudo cai no mesmo diretório do job, com o prefixo `NNN_` ao lado da
própria variação:

```text
projects/<project>/jobs/<job>/
    000.png                 ← o ASSET: a imagem lógica (64×64)
    000_thumb.png           ← thumbnail do profile de geração (nearest, opcional)
    000_raw.png             ← saída crua do motor, byte a byte
    000_preview.png         ← ampliação inteira, só para visualizar (512×512)
    000_palette.json        ← paleta medida no arquivo entregue + frequências
    000_processing.json     ← ProcessingReport: o que cada estágio fez
    000_validation.json     ← PixelValidationReport + a chave "acceptance"
    001.png, 001_raw.png, …
    asset.json              ← metadados do asset inteiro
```

Decisões por trás dessa lista:

- **`logical.png` não vira arquivo irmão.** Ele *é* a variação `NNN.png`; o
  pipeline descarta a entrada `logical.png` do dicionário para não gravar os
  mesmos bytes duas vezes com dois nomes.
- **`raw.png` é gravado sem reencode.** O valor dele é ser exatamente o que o
  motor devolveu; passá-lo pelo Pillow o tornaria uma cópia *nossa* da saída do
  motor e o benchmark do §71 perderia o sentido.
- **`palette.json` descreve o arquivo, não o pedido.** As cores vêm de contar o
  PNG final, em ordem de frequência decrescente com empate resolvido pelo
  hexadecimal — lista estável, cor dominante primeiro.
- **`acceptance` mora dentro de `validation.json`**, como chave anexada, e não
  como campo do relatório: o Validator mede, a política decide, e juntar as
  duas coisas no mesmo modelo acabaria com essa fronteira.
- **os JSON são `ensure_ascii=False`, `indent=2`, sem ordenar chaves**: são
  lidos por gente, em português, e a ordem declarada nos contratos já é fixa
  (portanto determinística) e é a ordem em que o relatório faz sentido.
- **um artefato que falha ao gravar não derruba o job** — vira aviso no log. O
  asset é o `NNN.png`; os irmãos são material de depuração.
- `preview_uri` da variação aponta para `NNN_preview.png`, em um campo
  **separado** de `uri`. Ver a armadilha em §8.

---

## 7. Como configurar

### 7.1 `config/pixel_profiles.yaml` — o contrato de saída

É a **fonte dos valores concretos dos profiles oficiais** (plano Pixel §64).
Cada bloco vira um `PixelOutputSpec`, e a chave do bloco é o `id` do profile.
Um profile novo do §66 (sprite sheet, tileset maior, portrait, ícone) entra
acrescentando um bloco — **sem tocar em nenhum `.py`**. Os modelos mantêm
defaults conservadores para compatibilidade com profiles antigos que ainda não
declaram `pixel_profile`; esses defaults não definem os profiles oficiais.

Os profiles que já existem, e o que cada desvio ensina:

| Profile | Tamanho | Cores | Desvios |
|---|---|---|---|
| `pixel_character_64_strict` | 64×64 | 16 | o exemplo literal do plano §65 |
| `pixel_character_32_strict` | 32×32 | 12 | menos pixels, menos espaço para nuance; preview 16× para dar a mesma tela |
| `pixel_prop_64_strict` | 64×64 | 16 | `min_occupancy: 0.03` — uma moeda ocupa pouco canvas de propósito |
| `pixel_tileset_16` ⚠ | 16×16 | 8 | `canvas: stretch` (o tile preenche a célula), `cleanup: off` (1 pixel é uma feição inteira), `boundary_touch: ignore` e `min_occupancy: 0.50` (o tile *precisa* sangrar até a borda) |

⚠ **`pixel_tileset_16` é um contrato sem Generation Profile.** Nenhum bloco de
`profiles.yaml` aponta para ele, então ele **não é pedível** por
`POST /api/generation/jobs` — hoje só o alcançam o endpoint de diagnóstico
(§7.4) e `scripts/pixel_report.py --profile pixel_tileset_16`. Não é
esquecimento: o resto do sistema trata tile como não lançado — a capacidade
`tileset.pixel` está marcada `experimental` em `kernel/capabilities.py`, não
existe pipeline de tile e a interface só conhece Pixel Art e 2D Normal.

Ele fica aqui porque tile é o caso que mais estica o contrato (`stretch`,
`cleanup: off`, `boundary_touch: ignore` e ocupação alta *exigida* em vez de
tolerada), e mantê-lo vivo e testado
([`test_golden.py`](../tests/pixel/test_golden.py)) é o que prova que o
`PixelOutputSpec` já cobre o §66 antes de existir produto para ele. Expor o
tile de verdade custa um prompt builder próprio — um tile quer o oposto de um
personagem: sem fundo transparente, sem margem, preenchendo o quadro — mais o
bloco correspondente em `profiles.yaml`. Nada disso muda uma linha do
`pixel_profiles.yaml`.

A chave `palettes:` no fim do arquivo é a tabela nomeada do modo PROJECT
(§11): um profile pede `palette_id: forest_world_v1` e o `PixelProfileRegistry`
o resolve para uma paleta LOCKED concreta **ainda no boot**, para que
personagem, inimigo e tile do mesmo mundo compartilhem exatamente as mesmas
cores.

Um profile inválido é **ignorado com log de erro**, nunca derruba o boot: um
erro de digitação em um profile experimental não pode impedir o backend de
subir.

### 7.2 `pixel_profile` em `config/profiles.yaml` — o encaixe

O Generation Profile aponta o contrato Pixel pelo id:

```yaml
pixel_character_64:
  display_name: "Personagem Pixel Art 64×64"
  capability: "text_to_image.pixel"
  pipeline: "pixel.character"
  pixel_profile: "pixel_character_64_strict"   # ← o contrato técnico
```

Quando esse campo está presente, o profile Pixel é a **fonte única da verdade
técnica** do arquivo final — resolução lógica, paleta, alpha, canvas, preview e
quais requisitos são obrigatórios. O Generation Profile não contribui com nada
disso, justamente para não existirem dois lugares dizendo qual é o limiar de
alpha. Ver a armadilha em §8.

Profiles antigos, sem `pixel_profile`, continuam funcionando: `spec_from_profile`
deriva um spec dos campos que eles já tinham (`output.logical_*`,
`palette.size`, `postprocessing.alpha_threshold`, `pixel_cleanup`,
`validate_grid`, `validate_color_count`, `thumbnail_scale`) e o marca com
`id: "derived:<profile>"`. Se o `pixel_profile` apontar para um id inexistente,
o mesmo caminho de derivação assume, com um `WARNING` no log.

### 7.3 Precedência

```text
profile Pixel (config/pixel_profiles.yaml)
    <  overrides do pedido (AssetOutputOverrides, no POST do job)
```

Só três campos do pedido fazem sentido no contrato de saída, e são exatamente
os que `_apply_overrides` aceita: `logical_width`/`logical_height`,
`palette_size` (só quando a paleta é `max_colors` — pedir "12 cores" não pode
furar uma paleta travada) e `transparent`. É o que permite pedir um sprite
32×32 com 8 cores sem criar um profile novo para cada combinação.

### 7.4 `ASSETFLOW_DEV_ENDPOINTS` — o endpoint de diagnóstico

`POST /api/dev/pixel/analyze` recebe uma imagem em base64 e devolve o
relatório, sem passar por um job e **sem persistir nada**. É o que permite
medir "quão longe do Pixel Exact" está a saída de um motor novo antes de
integrá-lo.

```bash
ASSETFLOW_DEV_ENDPOINTS=1   # padrão: desligado
```

Desligado, a rota devolve 404 e some da documentação. O corpo aceita
`profile` (id de `pixel_profiles.yaml`) **ou** `spec` inline, e o interruptor
`process`: `true` processa antes de validar (o caminho real do pipeline),
`false` valida a imagem exatamente como ela chegou. O fluxo normal de geração
continua sendo `POST /api/generation/jobs` (§77) — este endpoint não pode virar
uma porta paralela de processamento em produção.

---

## 8. Armadilhas conhecidas

- **Nada de `BILINEAR`, `BICUBIC` ou `LANCZOS` depois da resolução lógica.** O
  `LogicalPixelReducer` é o marco do plano §20: a partir dele, qualquer filtro
  suavizado — inclusive blur, sharpen e "suavização de borda" — reintroduz as
  cores intermediárias e o alpha parcial que a paleta e o corte de alpha
  acabaram de eliminar, e o asset deixa de ser Pixel Exact. Toda operação de
  imagem passa por `assetflow/pixel/imaging.py` justamente para que essa
  proibição seja verificável em **um** arquivo: `resize_box` reduz,
  `resize_nearest`/`scale_nearest` ampliam, e não existe terceira opção.
- **O preview nunca é o asset.** `preview.png` é uma ampliação inteira e
  nearest da imagem lógica, para que uma pessoa consiga olhar um sprite de
  64×64 em uma tela de 1440p. Entregá-lo no lugar do asset é entregar um PNG
  512×512 fingindo ser um sprite 64×64 — a violação nº 1 do plano §103. Por
  isso o `PreviewGenerator` devolve a imagem **separada** (e devolve `None`,
  não uma cópia, quando o profile dispensa preview), o exporter o grava em
  outra chave e a variação o expõe em `preview_uri`, nunca em `uri`.
- **A escala do preview é inteira, e é `spec.preview.scale`** — não
  `preview_size` dividido pelo tamanho real da imagem. `scale(7.8125)`
  distribuiria 64 pixels lógicos em 500 pixels de tela e alguns blocos sairiam
  com 7 colunas, outros com 8: o sprite pareceria defeituoso e o artista
  culparia a arte, não o zoom.
- **Uma tentativa extra, no máximo.** `max_processing_attempts` (padrão 2) é o
  teto contra loop infinito do §61, e o laço ainda para antes disso quando não
  há endurecimento conhecido para a falha. Aumentar esse número não melhora
  asset ruim: as três correções conhecidas estão em `_harden_spec` e o resto
  precisa de um motor diferente, não de mais uma passagem do mesmo algoritmo.
- **A limpeza é conservadora por contrato.** `CleanupSpec.mode` é
  `Literal["off", "conservative"]`: não existe modo agressivo para alguém ligar
  "só para subir a nota" (§106). Um pixel isolado pode ser um olho.
- **`quality_score` não é `pixel_exact`.** Ver §5.2. Um relatório com nota 90
  pode estar reprovado, e um com nota 58 pode estar perfeito tecnicamente.

---

## 9. O que o módulo NÃO resolve (plano Pixel §95)

O Pixel Exact garante que o **arquivo** está correto. Ele não tem, e não vai
ter, opinião sobre o **desenho**:

- **anatomia** — braço torto, mão com seis dedos, cabeça fora de proporção;
- **design** — se o personagem combina com a direção de arte do projeto;
- **composição** — enquadramento, pose, leitura da silhueta.

Nada disso é medível por contagem de cores, alpha ou componentes conexos, e
fingir que é seria pior do que não medir: um número inventado vira decisão
automática. Um asset pode ser `PIXEL EXACT: sim` e ainda assim ser arte ruim —
esse julgamento é do artista, e o módulo entrega a ele um arquivo tecnicamente
íntegro para trabalhar em cima.

Também estão explicitamente fora da versão 1.0, cada um por um motivo:

| Fora de escopo | Por quê |
|---|---|
| remoção automática de fundo | é segmentação, não normalização: exigiria um modelo próprio e o erro só apareceria depois da redução lógica, quando não há como voltar |
| alpha `limited` (0/85/170/255) | previsto no §24 para vidro e fumaça; não pertence ao perfil estrito, e a proibição está no contrato (`AlphaSpec.mode` é `Literal["binary"]`) |
| limpeza agressiva | destruiria detalhe intencional para melhorar uma nota (§106) |
| reconstrução de contorno | o `OutlineAnalyzer` só detecta; reforçar contorno é desenhar por cima do artista com base em heurística — e dentro do Validator, que por contrato não altera um pixel |
| regeneração automática | `attempts.max_regeneration_attempts` existe no contrato como encaixe, mas ainda não tem consumidor: pedir uma imagem nova é falar com o motor, e o módulo Pixel não conhece motor nenhum |

---

## 10. Mapa: plano Pixel → código

| Plano Pixel | Onde |
|---|---|
| §3 regra de ouro (1 pixel lógico = 1 pixel) | `processing/stages/logical_reducer.py`, `checks/dimensions.py` |
| §5 desacoplamento de tecnologia | `assetflow/pixel/` inteiro; ponte em `postprocessing/pixel/exact.py` |
| §6–§9 PixelPostProcessor | `processing/service.py` |
| §8 ordem dos estágios | `processing/service.py::default_transforms` |
| §10 PixelOutputSpec | `contracts/output_spec.py` |
| §11 modos de paleta (AUTO/LOCKED/PROJECT) | `contracts/output_spec.py::PaletteSpec`, `profiles/registry.py` |
| §12–§14 entrada e canvas | `stages/input_normalizer.py`, `stages/canvas_normalizer.py` |
| §15–§20 resolução lógica e a proibição de resample | `stages/logical_reducer.py`, `imaging.py` |
| §21–§24 alpha binário | `stages/alpha_normalizer.py`, `checks/alpha.py` |
| §25–§28 paleta e dithering | `stages/palette_quantizer.py` |
| §29–§31, §106 limpeza conservadora | `stages/conservative_cleaner.py` |
| §32, §70–§75 artefatos e relatórios | `stages/exporter.py`, `contracts/*_report.py` |
| §33–§35, §80–§81 preview | `preview/generator.py` |
| §36–§46 hard checks | `validation/service.py`, `validation/checks/` |
| §47–§55 análise de qualidade | `validation/analyzers/` |
| §56, §60 nota | `validation/scoring.py` |
| §58–§60 status e política de aceitação | `acceptance/policy.py` |
| §61 limite de tentativas | `service.py::_harden_spec` |
| §64–§66 configuração e profiles | `config/pixel_profiles.yaml`, `profiles/registry.py` |
| §67–§68 fachada e encaixe | `service.py`, `postprocessing/pixel/exact.py`, `.../spec.py` |
| §76 versionamento dos relatórios | `version.py` |
| §77–§78 API e endpoint de diagnóstico | `api/routers/dev_pixel.py` |
| §93–§94 observabilidade e benchmark | `service.py::_observability`, `storage/records.py` |
| §103–§108 as regras inegociáveis | espalhadas nas docstrings, com a citação da seção |
