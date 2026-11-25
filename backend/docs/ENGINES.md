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
> governança) continuou inteira: ela foi escrita para não depender de motor
> nenhum.

> **Fase A do plano do app** ([PLANO_APP_DESENHISTA.md](PLANO_APP_DESENHISTA.md)).
> A desenhista virou o gerador único do app. Saíram o seletor de motor da tela,
> o modo "Automático" (`kernel/auto_policy.py`, `config/engine_policy.yaml`,
> `spec/engine_advisor.py`) e o fallback para mock. As gavetas de referência
> continuam existindo, só nos testes. O que segue descreve o estado depois
> dessa fase.

O AssetFlow deixou de ser uma interface com um gerador e passou a ser uma
plataforma com motores intercambiáveis. Este documento explica o que mudou,
onde cada peça mora e como acrescentar a próxima gaveta.

---

## 1. O que a pessoa vê

Nada de motor. A tela não tem seletor nem crédito de motor: o app tem um
gerador só, a `desenhista-v1`, que desenha a partir de uma receita escrita pelo
Claude na conversa, pelo servidor MCP ([MCP.md](MCP.md)). A tela não manda
receita, e por isso o botão "Gerar" está desligado até a fila da Fase B do
plano do app, com uma frase dizendo isso.

**Nenhum id de motor está escrito no frontend.** O catálogo continua em
`GET /api/generation/engines/catalog`, para diagnóstico — e o Pixel Optimizer
**nunca** aparece nele, porque não é um motor.

---

## 2. As gavetas

| id | família | estado padrão | para quê |
|---|---|---|---|
| `desenhista-v1` | agêntica | **habilitada** | o Claude desenha: receita de camadas → sprite na grade lógica ([DESENHISTA.md](DESENHISTA.md)) |
| `mock-image-v1` | procedural | habilitada **nos testes** | gaveta de referência: exercita a arquitetura sem GPU |
| `mock-pixel-alt-v1` | procedural | desabilitada | só existe para testar troca de motor |

A desenhista entrega a grade lógica 1:1 (`catalog.exact_resolution: true`),
não usa seed e entrega uma variação por pedido. Nenhuma das três precisa de
GPU.

As de referência produzem um padrão determinístico, não arte. Elas declaram
`catalog.dev_only` e só são **registradas** no ambiente de testes
(`AppEnvironment.TEST`, que o `tests/conftest.py` e o
`scripts/preview_engine.py` ligam por código; `ASSETFLOW_APP_ENV=test` é
recusado). Em `development` e em `production`, o app tem só a desenhista. Não
há caminho que desenhe sozinho: o Pixel Optimizer corrige o que um motor
produziu, e sem motor não há o que corrigir
([PIXEL_OPTIMIZER.md](PIXEL_OPTIMIZER.md) §5).

Para ver o estado real da sua instalação, sem adivinhar:
`GET /api/generation/engines/catalog?include_hidden=true`, com `available` e
`unavailable_reason` por gaveta. Uma gaveta ligada mas mal configurada diz exatamente o que falta.

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

Duas camadas, nesta ordem:

```
1. seleção manual        quem pediu nomeou   ->  é usado, ou o job falha
                         o motor (o MCP)
2. roteamento por        ninguém nomeou      ->  capabilities.yaml
   capacidade            ("auto")
```

A decisão vira o campo `engine` do **Final Resolved Spec**, resolvido uma vez
na submissão, com precedência como qualquer outro campo:

```
padrão global < profile < inferência < interface < prompt < correção manual
```

Em `auto`, o `engine_id` do spec fica vazio, e o kernel percorre a rota da
capacidade. No app, as três rotas Pixel (`text_to_image.pixel`,
`character.pixel`, `prop.pixel`) listam só a `desenhista-v1`, o fallback está
desligado e `allow_unlisted_engines: false` impede que uma gaveta fora da lista
entre na cadeia. Os testes de mecanismo trocam essa política pela deles
(`ROTEAMENTO_DE_TESTE`, no `tests/conftest.py`), com os mocks e o fallback.

A política do modo "Automático" (`AutoEnginePolicy`), que preferia um motor
por regras e explicava o motivo, saiu na Fase A do plano do app: com um
gerador só, não havia o que escolher, e era ela que, com o fallback, deixava um
mock gerar quando a desenhista recusava um pedido sem receita.

### Lotes e seed

O kernel divide um pedido de N variações em lotes que respeitam o
`limits.max_variations` da gaveta, variando a seed de lote para lote. Uma
gaveta com `supports.seed: false` não tem como variar: os lotes seriam cópias.
Por isso, para ela, um pedido acima do limite **falha** com
`InvalidGenerationRequest`, antes de a gaveta carregar — em vez de entregar N
imagens iguais. A regra lê o manifesto e não cita gaveta nenhuma
(`kernel/service.py`, `_run_candidate`).

### As quatro regras de governança (plano §25)

1. **O motor escolhido é respeitado.** Se não puder atender, o job falha
   dizendo por quê — nunca vira outro motor em silêncio.
2. **Fallback só em `auto`**, ou quando alguém pediu explicitamente. Em
   seleção manual, `allow_fallback` nasce `False`. No app, a configuração
   desliga o fallback de todo; a regra age nos testes.
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
   `catalog` (família, tiers, resumo, tópicos, selos) — é o que o catálogo da
   API mostra;
3. implemente `ImageGenerationEngine` (ou herde de
   `BaseImageGenerationEngine`);
4. acrescente o id à `discovery.allowlist` e um bloco em `engines.yaml`;
5. cite o motor numa rota de `capabilities.yaml` — com
   `allow_unlisted_engines: false`, gaveta fora da rota não é usada em
   `auto`;
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
generation/kernel/resolver.py      capacidade -> cadeia de candidatos
generation/spec/resolver.py        a decisão de motor entra no Final Resolved Spec
generation/engines/<gaveta>/       cada motor, isolado
config/capabilities.yaml           as rotas por capacidade (no app: só a desenhista)
```

O catálogo mora no kernel, e não em `assetflow/engines/catalog/` como o plano
§23 sugere, porque ele é uma **leitura** da estante que já existe (registry +
manifestos). Movê-lo para fora exigiria importar o registry de baixo para
cima, invertendo a dependência que o teste de fronteiras protege. A estrutura
muda; a regra do plano — nenhum motor concreto importado fora de `engines/` —
continua valendo, e continua verificada por teste.
