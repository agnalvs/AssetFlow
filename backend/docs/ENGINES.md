# Múltiplos motores e seleção de modelo

> Documento de referência do plano *"Seleção de Modelos e Múltiplos Motores
> Pixel Art"*. As docstrings do código citam este arquivo como `plano de
> motores §N`, onde `N` é a seção **daquele plano**, não deste documento.

O AssetFlow deixou de ser uma interface com um gerador e passou a ser uma
plataforma com motores intercambiáveis. Este documento explica o que mudou,
onde cada peça mora e como acrescentar a próxima gaveta.

---

## 1. O que a pessoa vê

A tela de geração ganhou um seletor de motor com cinco opções:

```
Motor:  [ Automático ▾ ]
        Automático
        FLUX Pixel
        SD-πXL              (indisponível)
        Pixel Forge         (indisponível)
        Texel-style Agent
```

Escolhido um motor, aparece um resumo do que ele faz bem e o que ele custa. Em
**Automático**, aparece o motor que o AssetFlow escolheu e **por quê**, antes
de gerar:

```
Motor resolvido: Texel-style Agent
Motivo: prop pequeno com paleta curta: motores especializados em sprites
        desenham direto na grade, sem perder a silhueta na redução
```

Depois de gerar, o resultado diz quem gerou — e, se o motor pedido não pôde
atender, diz isso em vez de entregar outro em silêncio.

**Nenhum id de motor está escrito no frontend.** A lista inteira vem de
`GET /api/generation/engines/catalog`. Uma gaveta nova aparece no seletor sem
que nenhum arquivo de React mude.

---

## 2. As gavetas

| id | família | estado padrão | do que depende |
|---|---|---|---|
| `flux-pixel-v1` | difusão | desabilitada | GPU, `diffusers`, `peft`, download do modelo |
| `sdpixl-v1` | otimização | desabilitada | clone do SD-πXL + `options.command` |
| `pixel-forge-v1` | sprites nativos | desabilitada | binário Rust + `options.binary` |
| `texel-style-v1` | agente | **habilitada** | nada |
| `diffusers-sdxl-v1` | difusão | habilitada | GPU, `diffusers`, download do modelo |
| `mock-*` | procedural | referência | nada (fora da vitrine) |

Três nascem desabilitadas porque dependem de algo que a máquina pode não ter —
e uma gaveta habilitada que não roda entra na **cadeia de fallback**,
transformando cada falha do motor principal em uma segunda falha, mais lenta.

`texel-style-v1` é a exceção: ela só depende de Python, roda em
milissegundos e é determinística por seed. É por isso que ela também é a
gaveta mais confiável da estante para servir de fallback.

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

### SD-πXL (`sdpixl/`) e Pixel Forge (`pixel_forge/`)

As duas são **pontes para processos externos**, não bibliotecas importadas. O
motivo é o mesmo nos dois casos e é de arquitetura: importar o SD-πXL
amarraria o backend ao ambiente Python dele; o Pixel Forge é Rust e o plano é
explícito em não acoplar o backend àquele runtime.

O comando é configuração, com placeholders:

```yaml
sdpixl-v1:
  options:
    command: ["python", "main.py", "--prompt", "{prompt}", "--size",
              "{logical_width}", "--output", "{output}"]
    working_dir: "D:/ferramentas/sd-pixl"
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

### Texel-style Agent (`texel_style/`)

A única gaveta que **não** pinta grande para depois reduzir. Ela desenha na
resolução lógica, pixel a pixel, com ferramentas:

```
FinalResolvedSpec
  -> PlanningAgent   plano de desenho: canvas, paleta, regiões, tool calls
  -> ToolExecutor    draw_pixel, fill_rect, draw_circle, noise_fill_rect...
  -> PixelCanvas     o estado
  -> ReviewLoop      inspeciona e corrige: órfãos, contorno, paleta
  -> exportação      PNG no grid + histórico das tool calls
```

Três propriedades que vêm de graça por trabalhar na grade: não existe
anti-aliasing para remover, o alpha já é binário, e a paleta é conhecida antes
de pintar (não estimada depois de quantizar).

**Sobre licença** (plano §2.4): o Texel Studio é *source-available*, com
restrição contra hospedagem como SaaS concorrente. Esta gaveta não incorpora,
importa nem revende aquele projeto — é implementação própria, inspirada na
arquitetura tool-based dele. O que foi adotado é o vocabulário de ferramentas,
que descreve bem o problema.

O planejador é **determinístico e por receitas**, sem LLM. É escolha, não
limitação: a mesma seed produz o mesmo sprite (o que torna o motor comparável
no benchmark), roda sem rede e é legível. Trocar por um planejador com LLM
exige apenas devolver um `DrawingPlan` — executor, review loop e exportação
não mudam.

Receitas: árvore, pedra, poção, baú, tile/bloco, espada, moeda, personagem
simples e um fallback genérico. Acrescentar um sujeito é acrescentar termos em
`RECIPE_KEYWORDS` e uma função ao lado das outras.

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
| `engine_selection.json` | motor pedido × motor usado, motivo, cadeia, rejeições |
| `engine_output.json` | motor, versão, versão do adapter, modelo, revisão, LoRA |
| `processing.json` | o que o Pixel Exact fez |
| `validation.json` | o veredito técnico |
| `palette.json`, `preview.png`, `raw.png` | paleta medida, ampliação, saída crua |

`parsed_spec.json` guarda os dois lados (semântica e texto) porque o defeito
costuma estar na distância entre um e outro. `engine_output.json` guarda os
cinco campos de identidade porque quatro não bastam: o mesmo modelo com outro
adapter, ou com outra LoRA, produz outro asset.

---

## 5. Benchmark (plano §19 a §21)

```bash
python scripts/benchmark_engines.py --list
python scripts/benchmark_engines.py --engines texel-style-v1,flux-pixel-v1
python scripts/benchmark_engines.py --cases tree_32 --json data/benchmark/r.json
```

A suíte (`config/benchmark_suite.yaml`) é fixa e versionada, com seed por caso:
comparar motores com prompts diferentes não compara nada.

O runner usa o **caminho normal** do sistema — prompt adapter,
pós-processamento, validação — porque o que interessa comparar é o asset
entregue, não a saída crua do motor. A seleção é manual e sem fallback: um
caso atendido por outro motor conta como **falha** do motor pedido, senão o
relatório credita a um motor o trabalho de outro.

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

Se a gaveta entrega a resolução lógica exata (como o Texel-style e o SD-πXL),
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
