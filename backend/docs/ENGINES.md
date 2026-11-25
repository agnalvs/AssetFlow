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

> **Fase 0 do plano desenhista.** As gavetas de difusão (`diffusers-sdxl-v1`,
> `flux-pixel-v1`), as pontes para projetos externos (`sdpixl-v1`,
> `pixel-forge-v1`), a de API paga (`gpt-image-v1`) e o benchmark entre
> motores saíram do repositório. Na Fase 1 entrou a `desenhista-v1`, que
> recebe o desenho do Claude como uma receita — ver
> [PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md) e
> [DESENHISTA.md](DESENHISTA.md). A infraestrutura descrita aqui (catálogo,
> política do modo Automático, governança) continuou inteira: ela foi escrita
> para não depender de motor nenhum.

O AssetFlow deixou de ser uma interface com um gerador e passou a ser uma
plataforma com motores intercambiáveis. Este documento explica o que mudou,
onde cada peça mora e como acrescentar a próxima gaveta.

---

## 1. O que a pessoa vê

A tela mostra o seletor de motor, preenchido pelo catálogo:

```
Motor:  [ Automático ▾ ]
        Automático
        <cada gaveta visível no catálogo>
        <outra gaveta>      (indisponível)
```

Escolhido um motor, aparece um resumo do que ele faz bem e o que ele custa. Em
**Automático**, aparece o motor que o AssetFlow escolheu e **por quê**, antes
de gerar:

```
Motor resolvido: <nome do motor>
Motivo: <o `reason` da regra de engine_policy.yaml que casou>
```

Depois de gerar, o resultado diz quem gerou — e, se o motor pedido não pôde
atender, diz isso em vez de entregar outro em silêncio.

**Hoje o seletor do modo Pixel Art tem "Automático" e "Desenhista (Claude via
MCP)".** A desenhista apareceu ali sozinha, pelo manifesto, sem mudança no
frontend. As gavetas de referência ficam fora da vitrine (`catalog.hidden`).

A desenhista só desenha a partir de uma receita, e a tela não manda receita —
quem manda é o servidor MCP, pela conversa com o Claude ([MCP.md](MCP.md)).
Escolhida no seletor, ela falha com a mensagem dela (regra 1: motor escolhido
é motor usado). Em "Automático", ela recusa e o fallback entra — em
desenvolvimento, nos mocks; em produção não há mocks, e a mensagem chega à
tela.

**Nenhum id de motor está escrito no frontend.** A lista inteira vem de
`GET /api/generation/engines/catalog`. Uma gaveta nova aparece no seletor sem
que nenhum arquivo de React mude — e o Pixel Optimizer **nunca** aparece nele,
porque não é um motor.

---

## 2. As gavetas

| id | família | estado padrão | para quê |
|---|---|---|---|
| `desenhista-v1` | agêntica | **habilitada** | o Claude desenha: receita de camadas → sprite na grade lógica ([DESENHISTA.md](DESENHISTA.md)) |
| `mock-image-v1` | procedural | **habilitada** | gaveta de referência: valida a arquitetura sem GPU |
| `mock-pixel-alt-v1` | procedural | desabilitada | só existe para testar troca de motor |

A desenhista entrega a grade lógica 1:1 (`catalog.exact_resolution: true`),
não usa seed e entrega uma variação por pedido. Nenhuma das três precisa de
GPU.

As de referência produzem um padrão determinístico, não arte. Elas declaram
`catalog.dev_only` e **deixam de ser registradas** com
`ASSETFLOW_APP_ENV=production` — em produção sobra só a desenhista. Não há
caminho que desenhe sozinho: o Pixel Optimizer corrige o que um motor
produziu, e sem motor não há o que corrigir
([PIXEL_OPTIMIZER.md](PIXEL_OPTIMIZER.md) §5).

Para ver o estado real da sua instalação, sem adivinhar:
`GET /api/generation/engines/catalog?include_hidden=true` — é a mesma lista
que o seletor da tela consome, com `available` e `unavailable_reason` por
gaveta. Uma gaveta ligada mas mal configurada diz exatamente o que falta.

> **Um defeito que já esteve aqui, e cuja correção continua no kernel.** As
> antigas pontes para executáveis externos ficaram *permanentemente*
> inutilizáveis, mesmo configuradas, por um ciclo de três peças: com
> `lazy_load`, a gaveta só recebia a configuração dela no primeiro job; o
> `health_check()` respondia antes disso e dizia "não configurado"; e o
> `EngineHandle` transformava esse "indisponível" em estado `FAILED` — que o
> resolver recusa, de modo que a inicialização nunca chegava a acontecer.
>
> A correção foi separar duas coisas que estavam juntas: **receber a
> configuração** (barato, acontece ao criar a instância) e **inicializar**
> (pode ser caro, continua preguiçoso). Um "indisponível" anterior à
> inicialização também deixou de reprovar o motor: ali ele significa "ainda
> não perguntei direito", não "quebrado" (`kernel/lifecycle.py`). Vale para
> qualquer gaveta que dependa de configuração da máquina.

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

A lista entregue tem **uma** regra, `pixel_geral`: todo pedido Pixel Art
prefere a `desenhista-v1`. Sem regra que case (o modo 2D Normal), a política
se cala e o roteamento por capacidade decide.

### Lotes e seed

O kernel divide um pedido de N variações em lotes que respeitam o
`limits.max_variations` da gaveta, variando a seed de lote para lote. Uma
gaveta com `supports.seed: false` não tem como variar: os lotes seriam cópias.
Por isso, para ela, um pedido acima do limite **falha** com
`InvalidGenerationRequest`, antes de a gaveta carregar — em vez de entregar N
imagens iguais. A regra lê o manifesto e não cita gaveta nenhuma
(`kernel/service.py`, `_run_candidate`).

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

## 5. Benchmark (removido)

O benchmark entre motores (`scripts/benchmark_engines.py`,
`generation/benchmark/` e `config/benchmark_suite.yaml`) saiu na Fase 0 do
plano desenhista: com uma gaveta real só, não há o que comparar. O que ele
media continua gravado em todo job — as métricas do Pixel Exact e do Optimizer
(`optimizer_pixels_changed`, `quality_score_before_optimizer`,
`quality_improvement`, …) e os arquivos da seção 4.

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
   `engine_policy.yaml`;
6. se a gaveta precisar de biblioteca própria, declare um extra com o nome
   dela no `pyproject.toml` — e importe essa biblioteca só de dentro da
   gaveta (o teste de fronteiras cobra).

O teste de contrato gera os casos sozinho a partir do manifesto — **motor novo
é testado sem escrever teste novo**. Gavetas cujas dependências não estão
instaladas, ou que se declaram indisponíveis no `health_check()`, são puladas
em vez de falhadas.

Se a gaveta só gera com uma entrada própria — a desenhista precisa de
receita —, ponha um `exemplo_contrato.json` ao lado do `manifest.json`. O
conteúdo vira `engine_options[<id>]` no pedido do contrato, e todos os casos
rodam com uma entrada válida.

Se a gaveta entrega a resolução lógica exata (desenha direto na grade),
declare `catalog.exact_resolution: true`: o contrato passa a aceitar que a
saída venha no grid, em vez de no tamanho de render.

Opções que dependem da máquina (caminhos, limites) entram por
`ASSETFLOW_ENGINE_<ID>_OPTIONS` como JSON, com merge por chave sobre o
`engines.yaml` — que é versionado e não deve receber caminho de ninguém.

---

## 7. Onde cada coisa mora

```
generation/kernel/catalog.py       a vitrine: manifesto + estado -> entrada de catálogo
generation/kernel/auto_policy.py   o que "Automático" prefere, e por quê
generation/kernel/resolver.py      capacidade -> cadeia de candidatos (+ dica do auto)
generation/spec/resolver.py        a decisão de motor entra no Final Resolved Spec
generation/spec/engine_advisor.py  o Protocol que separa spec de estante
generation/engines/<gaveta>/       cada motor, isolado
config/engine_policy.yaml          as regras do modo Automático
```

O catálogo mora no kernel, e não em `assetflow/engines/catalog/` como o plano
§23 sugere, porque ele é uma **leitura** da estante que já existe (registry +
manifestos). Movê-lo para fora exigiria importar o registry de baixo para
cima, invertendo a dependência que o teste de fronteiras protege. A estrutura
muda; a regra do plano — nenhum motor concreto importado fora de `engines/` —
continua valendo, e continua verificada por teste.
