# Múltiplos motores e seleção de modelo

> Documento de referência do plano *"Seleção de Modelos e Múltiplos Motores
> Pixel Art"*. As docstrings do código citam este arquivo como `plano de
> motores §N`, onde `N` é a seção **daquele plano**, não deste documento.

> **Leia junto:** [PIXEL_OPTIMIZER.md](PIXEL_OPTIMIZER.md). A escolha de motor
> descrita aqui é a **única** escolha de tecnologia do AssetFlow. O que vem
> depois do motor — a revisão pixel a pixel — não é escolhível: acontece em
> toda geração Pixel Art.
>
> O "Texel-style Agent", que este documento já chamou de gaveta
> `texel-style-v1` e depois de método de criação, não é nem um nem outro. Ele
> virou o `AssetFlowPixelOptimizer`, em `pixel/optimizer/`.

O AssetFlow deixou de ser uma interface com um gerador e passou a ser uma
plataforma com motores intercambiáveis. Este documento explica o que mudou,
onde cada peça mora e como acrescentar a próxima gaveta.

---

## 1. O que a pessoa vê

Depois de escolher o método **Modelo de imagem**, a tela mostra o seletor de
motor:

```
Motor:  [ Automático ▾ ]
        Automático
        FLUX Pixel
        SD-πXL              (indisponível)
        Pixel Forge         (indisponível)
        SDXL Diffusers
```

Escolhido um motor, aparece um resumo do que ele faz bem e o que ele custa. Em
**Automático**, aparece o motor que o AssetFlow escolheu e **por quê**, antes
de gerar:

```
Motor resolvido: FLUX Pixel
Motivo: personagem com espaço para detalhe: a difusão lê melhor o pedido,
        e o Pixel Exact garante o grid depois
```

Depois de gerar, o resultado diz quem gerou — e, se o motor pedido não pôde
atender, diz isso em vez de entregar outro em silêncio.

**Nenhum id de motor está escrito no frontend.** A lista inteira vem de
`GET /api/generation/engines/catalog`. Uma gaveta nova aparece no seletor sem
que nenhum arquivo de React mude — e o Pixel Optimizer **nunca** aparece nele,
porque não é um motor.

---

## 2. As gavetas

**Todas as seis estão implementadas e registradas.** A coluna "estado padrão"
diz se elas vêm *ligadas*, e isso é outra coisa: uma gaveta desabilitada tem
código, manifesto, bloco em `engines.yaml` e teste de contrato — falta só a
dependência externa que o `engines.yaml` aponta.

| id | família | estado padrão | falta o quê para ligar |
|---|---|---|---|
| `gpt-image-v1` | difusão (API) | desabilitada | uma credencial em `OPENAI_API_KEY` |
| `diffusers-sdxl-v1` | difusão | **habilitada** | nada (baixa ~7GB no 1º job) |
| `mock-image-v1` | procedural | **habilitada** | nada — é gaveta de referência |
| `flux-pixel-v1` | difusão | desabilitada | GPU + `pip install -e ".[diffusers]"` + `enabled: true` |
| `sdpixl-v1` | otimização | desabilitada | clone do SD-πXL + `options.command` |
| `pixel-forge-v1` | sprites nativos | desabilitada | binário Rust compilado + `options.binary` |
| `mock-pixel-alt-v1` | procedural | desabilitada | nada — só existe para testar troca de motor |

Para ver o estado real da sua instalação, sem adivinhar:

```bash
python scripts/benchmark_engines.py --list
```

Ou, pela API, `GET /api/generation/engines/catalog?include_hidden=true` — é a
mesma lista que o seletor da tela consome, com `available` e
`unavailable_reason` por gaveta. Uma gaveta ligada mas mal configurada diz
exatamente o que falta: o Pixel Forge, por exemplo, responde *"aponte
`options.binary` em engines.yaml para o executável compilado do projeto"*.

As três de produção nascem desligadas porque dependem de algo que a máquina
pode não ter — e uma gaveta habilitada que não roda entra na **cadeia de
fallback**, transformando cada falha do motor principal em uma segunda falha,
mais lenta.

Sem nenhuma delas configurada, a geração Pixel Art **não funciona** fora do
ambiente de desenvolvimento — o que roda ali são as gavetas `mock-*`, que
produzem um padrão determinístico e não arte. Este é o preço de o AssetFlow
não ter mais um caminho que desenha sozinho: o Pixel Optimizer corrige o que
um motor produziu, e sem motor não há o que corrigir
([PIXEL_OPTIMIZER.md](PIXEL_OPTIMIZER.md) §5).

### FLUX Pixel (`flux_pixel/`)

FLUX.2-klein-4B com a LoRA de Pixel Art. Ele entrega a **base visual** —
composição, silhueta, cor, leitura do pedido — e **não** promete exatidão
técnica: grid, alpha binário e contagem de cores continuam sendo do Pixel
Exact, depois dele.

Antes de habilitar, confira os dois ids no HuggingFace (`model.id` e
`options.lora.id` em `engines.yaml`). Um repositório pode mudar de nome, e o id
errado só aparece como falha de download no primeiro job — a mensagem de erro
do loader diz exatamente qual id foi tentado.

Falha ao aplicar a **LoRA** não derruba a gaveta: ela fica `degraded`, o erro
vira aviso no resultado e o modelo-base continua gerando. Recusar o motor
inteiro porque um adaptador de dezenas de MB não baixou trocaria uma
degradação visível por uma indisponibilidade total.

### GPT Image (`gpt_image/`)

A única gaveta que roda **sem GPU, sem download e sem clone**: só rede e uma
credencial. Também a primeira remota — todas as outras carregam um modelo ou
executam um binário local.

Ela **não gera Pixel Art**, e isso não é um defeito dela:

> O provedor exige no mínimo **655.360 pixels** por imagem. Um sprite 32×32 tem
> 1.024 — 640 vezes menos. Não existe pedido de sprite a fazer.

O que ela entrega é a **proposta visual**; a grade é do Pixel Exact, depois
dela. É a tese da arquitetura levada ao limite: o motor precisa ser bom em
*entender o pedido*, não em *acertar a grade*.

```
logical 32×32  ->  render 832×832  ->  GPT Image  ->  redução  ->  32×32
```

**A escala é sempre inteira.** `sizing.py` escolhe o menor render que é
múltiplo exato do grid e satisfaz as quatro regras do provedor (arestas
múltiplas de 16, 655.360–8.294.400 pixels, aresta ≤ 3840, proporção ≤ 3:1).
Não é preciosismo: a redução que vem depois é **por blocos**, e com 900×900
para um grid de 32 cada pixel lógico cobriria 28,125 pixels de origem — as
bordas de bloco cairiam no meio de um pixel e a silhueta chegaria contaminada.

| grid | render | escala |
|---|---|---|
| 16×16 | 816×816 | 51 |
| 32×32 | 832×832 | 26 |
| 48×48 | 816×816 | 17 |
| 64×64 | 832×832 | 13 |
| 32×48 | 672×1008 | 21 |

Proporção acima de 3:1 é **recusada** com a razão — uma barra de vida 128×8 é
16:1, e gerar em 3:1 para esticar depois entregaria um asset deformado sem
avisar ninguém.

**Três capacidades ausentes, todas declaradas.** O provedor não tem `seed` e
não tem negative prompt; o fundo transparente está em *preview*. As duas
primeiras viram **aviso no job** — quem pediu uma seed precisa saber que o
resultado não é reprodutível —, e o negative é incorporado ao texto como
`Avoid:` em vez de ser descartado.

**Ligar:**

```bash
setx OPENAI_API_KEY "sk-..."           # Windows (vale na sessão seguinte)
export OPENAI_API_KEY="sk-..."         # bash
export ASSETFLOW_ENGINES_ENABLED="gpt-image-v1"
```

A chave vem **sempre** do ambiente. O `engines.yaml` guarda só o nome da
variável — ele é versionado, e uma chave de API em um arquivo do repositório é
um incidente, não um detalhe.

**Custo.** Cada imagem é cobrada, e `output.variations` vira `n` na chamada: um
candidate pool de 8 custa 8 imagens. O selo `pago` existe no catálogo para que
isso apareça na tela antes de alguém pedir oito variações.

O adapter fala HTTP direto, sem SDK. O teste de fronteiras *permitiria* o
pacote `openai` aqui dentro; a escolha de não usá-lo evita uma dependência de
instalação e faz qualquer endpoint compatível funcionar trocando `base_url`.

### SD-πXL (`sdpixl/`) e Pixel Forge (`pixel_forge/`)

As duas são **pontes para processos externos**, não bibliotecas importadas. O
motivo é o mesmo nos dois casos e é de arquitetura: importar o SD-πXL
amarraria o backend ao ambiente Python dele; o Pixel Forge é Rust e o plano é
explícito em não acoplar o backend àquele runtime.

#### Como ligar uma delas

O caminho do executável é **diferente em cada máquina**, e `engines.yaml` é
versionado. Então ele vai no ambiente, não no arquivo — senão todo `git pull`
vira conflito, ou o caminho de outra pessoa entra no seu ambiente:

```bash
# Pixel Forge
export ASSETFLOW_ENGINES_ENABLED="pixel-forge-v1"
export ASSETFLOW_ENGINE_PIXEL_FORGE_V1_OPTIONS='{
  "binary": "D:/ferramentas/pixel-forge/target/release/pixel-forge.exe",
  "args": ["--prompt", "{prompt}", "--seed", "{seed}",
           "--size", "{size}", "--out", "{output}"]
}'

# SD-πXL
export ASSETFLOW_ENGINES_ENABLED="sdpixl-v1"
export ASSETFLOW_ENGINE_SDPIXL_V1_OPTIONS='{
  "command": ["python", "main.py", "--prompt", "{prompt}",
              "--size", "{logical_width}", "--output", "{output}"],
  "working_dir": "D:/ferramentas/sd-pixl"
}'
```

O nome da variável sai do id da gaveta em maiúsculas, com `-` virando `_`. O
merge é **por chave**: apontar só o `binary` mantém `args`, `output_glob` e
timeout do YAML.

Os `args`/`command` dependem da CLI do projeto que você compilou ou clonou —
rode o `--help` dele e traduza para os placeholders. Eles são substituídos
**por argumento já separado**, nunca por shell.

> **O Pixel Forge é condicionado por classe, não por prompt.** A CLI dele é
> `generate <classe> --size 32 --seed N --output arquivo.png`, e `<classe>` vem
> de um vocabulário fechado pelo **modelo treinado** (`character`, `weapon`,
> `tree`, `building`, …). Mandar `{prompt}` naquela posição é erro de
> invocação, não um pedido genérico.
>
> Por isso existe o placeholder `{class}`: o AssetFlow traduz o **sujeito** e o
> **tipo** do pedido para uma classe — nessa ordem, porque "uma casa de pedra"
> é um `prop` para o AssetFlow e um `building` para o Pixel Forge, e é
> `building` a resposta útil. Os mapas `class_map`/`subject_map` em
> `options` ajustam isso ao seu modelo; eles só precisam existir quando o
> padrão erra.
>
> Nota de realidade: o projeto **não distribui pesos treinados**. Compilar o
> binário não basta — sem um `.safetensors` não há o que gerar, e treinar é
> parte do trabalho (`cargo run --release -- train ...`).

Confira antes de gerar:

```bash
python scripts/benchmark_engines.py --list
```

Se ela aparecer como disponível ali, está ligada. Se não, a mensagem diz o que
falta.

O YAML continua servindo para o que **não** é específico da máquina:

```yaml
sdpixl-v1:
  options:
    process_timeout_s: 7200
```

Placeholders disponíveis: `{prompt}`, `{negative}`, `{width}`, `{height}`,
`{logical_width}`, `{logical_height}`, `{max_colors}`, `{seed}`, `{steps}`,
`{output}`, `{output_dir}`, `{workspace}` (o Pixel Forge troca `{steps}` por
`{size}` e `{model}`).

A substituição acontece **por argumento já separado**, nunca por shell: um
prompt com aspas continua sendo um argumento, e não um comando novo.

As duas pontes têm código separado e não compartilham nada. É a regra 3 do
teste de fronteiras — uma gaveta não importa outra —, e ela vale aqui: um
módulo comum faria mexer no timeout do SD-πXL, que leva horas, alterar o Pixel
Forge, que responde em segundos.

> **Um defeito que já esteve aqui.** As duas ficaram *permanentemente*
> inutilizáveis, mesmo configuradas, por um ciclo de três peças: com
> `lazy_load`, a gaveta só recebia a configuração dela no primeiro job; o
> `health_check()` respondia antes disso e dizia "não configurado"; e o
> `EngineHandle` transformava esse "indisponível" em estado `FAILED` — que o
> resolver recusa, de modo que a inicialização nunca chegava a acontecer.
>
> A correção foi separar duas coisas que estavam juntas: **receber a
> configuração** (barato, acontece ao criar a instância) e **inicializar**
> (pode baixar gigabytes, continua preguiçoso). Um "indisponível" anterior à
> inicialização também deixou de reprovar o motor: ali ele significa "ainda
> não perguntei direito", não "quebrado". `tests/test_process_bridges.py`
> tranca os dois lados.

---

## 3. Como um motor é escolhido

Três camadas, nesta ordem:

```
1. seleção manual        a pessoa escolheu   ->  é usado, ou o job falha
2. AutoEnginePolicy      "Automático"        ->  preferência + motivo
3. roteamento por        último recurso      ->  capabilities.yaml
   capacidade
```

A decisão vira o campo `engine` do **Final Resolved Spec**, resolvido uma vez
na submissão, com precedência como qualquer outro campo:

```
padrão global < profile < inferência < interface < prompt < correção manual
```

`AutoEnginePolicy` (`config/engine_policy.yaml`) é uma lista de regras
avaliadas em ordem — da mais específica para a mais geral. Cada regra declara
critérios (tipo de asset, tamanho lógico, paleta, qualidade, modo), uma ordem
de preferência e um **motivo em português**, que é o que a tela mostra.

A política nunca obriga e nunca inventa: ela só sugere motores registrados,
habilitados e que declarem a capacidade pedida. Regra que casou mas não tem
motor de pé cede a vez à próxima.

### As quatro regras de governança (plano §25)

1. **O motor escolhido é respeitado.** Se não puder atender, o job falha
   dizendo por quê — nunca vira outro motor em silêncio.
2. **Fallback só em `auto`**, ou quando alguém pediu explicitamente. Em
   seleção manual, `allow_fallback` nasce `False`.
3. **A resposta mostra os três**: motor pedido, motor usado, versão e modelo
   (`JobResponse.engine_selection`).
4. **O validador usa o spec**, nunca defaults internos.

---

## 4. O que fica gravado (plano §18)

Cada variação gerada deixa, ao lado do PNG:

| arquivo | o que responde |
|---|---|
| `raw_prompt.txt` | a frase, exatamente como foi escrita |
| `parsed_spec.json` | o que o AssetFlow entendeu **e** o texto que o motor recebeu |
| `resolved_spec.json` | o contrato executado, com a origem de cada campo |
| `engine_selection.json` | motor pedido × usado, motivos, cadeia, rejeições, pipeline Pixel |
| `engine_output.json` | motor, versão, versão do adapter, modelo, revisão, LoRA |
| `processing.json` | o que o Pixel Exact fez |
| `validation.json` | o veredito técnico |
| `optimizer.json` | o que o Pixel Optimizer revisou, corrigiu e recusou |
| `palette.json`, `preview.png`, `raw.png` | paleta medida, ampliação, saída crua |

`parsed_spec.json` guarda os dois lados (semântica e texto) porque o defeito
costuma estar na distância entre um e outro. `engine_output.json` guarda os
cinco campos de identidade porque quatro não bastam: o mesmo modelo com outro
adapter, ou com outra LoRA, produz outro asset.

---

## 5. Benchmark (plano §19 a §21)

```bash
python scripts/benchmark_engines.py --list
python scripts/benchmark_engines.py --targets flux-pixel-v1,mock-image-v1
python scripts/benchmark_engines.py --cases tree_32 --json data/benchmark/r.json
```

O alvo é **um motor**. Todos atravessam o mesmo Pixel Optimizer, então a
diferença entre duas linhas da tabela é a diferença entre os motores — e as
colunas de otimização respondem à pergunta que interessa: quanta correção a
saída de cada um exigiu (plano Optimizer §69).

A suíte (`config/benchmark_suite.yaml`) é fixa e versionada, com seed por caso:
comparar motores com prompts diferentes não compara nada.

O runner usa o **caminho normal** do sistema — prompt adapter,
pós-processamento, validação — porque o que interessa comparar é o asset
entregue, não a saída crua do motor. A seleção é manual e sem fallback: um
caso atendido por outro motor — ou por outro método — conta como **falha** do
alvo pedido, senão o relatório credita a um caminho o trabalho de outro.

**Os dois eixos ficam separados**, e essa é a regra central do §21:

* **técnico** — medido pelo AssetFlow: resolução entregue, cores, alpha,
  órfãos, microclusters, nota do validador, quanto o pós-processamento teve de
  corrigir, tempo, taxa de falha;
* **visual** — composição, design, legibilidade: campo do relatório que só uma
  pessoa preenche. O módulo carrega o campo e não o adivinha.

A métrica mais reveladora do eixo técnico é `correction_ratio`: quanto o
pós-processamento precisou apertar a paleta do motor. Perto de 0%, o motor já
entende pixel art; perto de 100%, o AssetFlow reconstruiu a saída dele.

---

## 6. Acrescentar uma gaveta

Nada em `assetflow/` precisa mudar. O caminho é:

1. crie `generation/engines/<nome>/` com `manifest.json` e `engine.py`;
2. no manifesto, declare `capabilities`, `supports`, `limits` e o bloco
   `catalog` (família, tiers, resumo, tópicos, selos) — é o `catalog` que
   preenche o seletor da tela sozinho;
3. implemente `ImageGenerationEngine` (ou herde de
   `BaseImageGenerationEngine`);
4. acrescente o id à `discovery.allowlist` e um bloco em `engines.yaml`;
5. se fizer sentido, cite o motor em `capabilities.yaml` e/ou em
   `engine_policy.yaml`.

O teste de contrato gera os casos sozinho a partir do manifesto — **motor novo
é testado sem escrever teste novo**. Gavetas cujas dependências não estão
instaladas, ou que se declaram indisponíveis no `health_check()`, são puladas
em vez de falhadas.

Se a gaveta entrega a resolução lógica exata (como o SD-πXL e o Pixel Forge),
declare `catalog.exact_resolution: true`: o contrato passa a aceitar que a
saída venha no grid, em vez de no tamanho de render.

---

## 7. Onde cada coisa mora

```
generation/kernel/catalog.py       a vitrine: manifesto + estado -> entrada de catálogo
generation/kernel/auto_policy.py   o que "Automático" prefere, e por quê
generation/kernel/resolver.py      capacidade -> cadeia de candidatos (+ dica do auto)
generation/spec/resolver.py        a decisão de motor entra no Final Resolved Spec
generation/spec/engine_advisor.py  o Protocol que separa spec de estante
generation/benchmark/              suíte, runner e métricas
generation/engines/<gaveta>/       cada motor, isolado
config/engine_policy.yaml          as regras do modo Automático
config/benchmark_suite.yaml        os casos comparativos
```

O catálogo mora no kernel, e não em `assetflow/engines/catalog/` como o plano
§23 sugere, porque ele é uma **leitura** da estante que já existe (registry +
manifestos). Movê-lo para fora exigiria importar o registry de baixo para
cima, invertendo a dependência que o teste de fronteiras protege. A estrutura
muda; a regra do plano — nenhum motor concreto importado fora de `engines/` —
continua valendo, e continua verificada por teste.
