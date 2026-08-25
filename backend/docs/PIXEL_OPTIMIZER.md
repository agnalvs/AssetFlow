# O Pixel Optimizer

> Documento de referência do plano *"Pixel Optimizer Obrigatório no Pipeline de
> Geração"*. As docstrings do código citam este plano como `plano Optimizer §N`.
>
> Ele **substitui** o antigo `CREATION_METHODS.md`. A camada descrita lá —
> métodos de criação, `GenerationStrategy`, `pixel_agent` como alternativa ao
> motor — não existe mais, e a seção 8 explica por quê.

## 1. O problema que isto corrige

A tela pedia duas escolhas de tecnologia:

```
MÉTODO DE CRIAÇÃO                    depois, dependendo da resposta:
├─ Automático                        MOTOR      FLUX | SD-πXL | Pixel Forge
├─ Modelo de imagem  ──────────────> AGENTE     AssetFlow Pixel Agent
└─ Agente Pixel      ──────────────>            + modo de qualidade
```

O desenho estava correto sobre uma coisa — um agente não é um motor — e errado
sobre a que importava: **os dois não são alternativas**.

Um motor produz uma imagem a partir de um prompt. O agente corrige um sprite
pixel a pixel. São a primeira e a segunda metade do mesmo trabalho, e pedir
que alguém escolha entre elas é pedir uma escolha que não existe. Quem
escolhia "Agente Pixel" recebia um desenho feito do zero por um vocabulário
limitado; quem escolhia "Modelo de imagem" recebia uma imagem reduzida sem
ninguém revisar a grade. Nenhum dos dois recebia o que o AssetFlow sabe fazer.

## 2. O pipeline, agora

```
Motor
  -> PixelPostProcessor        reduz para a grade, quantiza, corta o alpha
  -> PixelValidator     V1     mede
  -> AssetFlowPixelOptimizer   revisa e corrige pixel a pixel   <- sempre
  -> PixelValidator     V2     mede de novo
  -> PixelAcceptancePolicy     decide, sobre a V2
```

Uma escolha de tecnologia, e é o motor. O que vem depois dele acontece em
**toda** geração Pixel Art, sem campo no pedido, sem controle na tela e sem um
único `if engine ==` no sistema (§25, §33, §46).

O que torna isso possível sem acoplamento: o Optimizer não é chamado por
nenhum motor. Ele vive dentro da ilha Pixel Exact, entre a validação e a
aceitação, e **nenhuma gaveta decide o que acontece depois de devolver a
imagem** (§80). Toda gaveta herda o estágio por não ter como não herdar.

## 3. As peças

```
pixel/optimizer/canvas.py     o sprite em edição, na grade real     (§14)
pixel/optimizer/reviewer.py   mede e descreve; não corrige          (§11)
pixel/optimizer/planner.py    decide o que corrigir — e o que não   (§12, §17)
pixel/optimizer/executor.py   aplica, com guarda de paleta, e loga  (§13, §16)
pixel/optimizer/palette.py    a paleta manda                        (§16, §67)
pixel/optimizer/tools/        uma ferramenta por arquivo            (§40)
pixel/optimizer/loop.py       revisar -> planejar -> corrigir       (§18, §19)
pixel/optimizer/optimizer.py  a fachada, e a regra de ouro          (§20, §38)
pixel/optimizer/contracts.py  laudo, plano, relatório               (§11, §12)
```

A separação entre **medir**, **decidir** e **executar** é a mesma que o
AssetFlow já mantém entre `PixelValidator` e `PixelAcceptancePolicy`, e existe
pelo mesmo motivo: as três falham de formas diferentes. Um sprite que saiu pior
depois da otimização precisa responder a três perguntas separadas — o
diagnóstico estava errado? o plano estava? a execução estava? — e um objeto
único não distingue nenhuma delas.

## 4. As três regras que dão forma ao módulo

### §14 — sempre na resolução lógica real

Se o asset é 32×32, o canvas é 32×32. Reparar um contorno em 1024px e depois
reduzir devolveria o problema pela mesma porta por onde ele entrou: a redução é
justamente onde silhueta e contorno se perdem.

Trabalhar na grade tem três consequências práticas: não há anti-aliasing a
remover, o alpha já é binário, e a paleta é conhecida em vez de estimada.

### §17 — preservar é uma decisão, e ela fica escrita

Um pixel isolado pode ser ruído da quantização ou pode ser **um olho**. O
planejador distingue os dois pela **cor**:

| o pixel isolado usa… | conclusão | ação |
| --- | --- | --- |
| uma cor que aparece só nele | resíduo da quantização | `erase_pixel` |
| uma cor que o sprite usa muito | vocabulário do desenho | preservar |

Ninguém desenha um detalhe com uma cor que não usa em nenhum outro lugar. O
preto do olho é o mesmo preto do contorno.

O que é preservado vai para `RepairPlan.declined`, **com o motivo**. "Não
corrigi, e aqui está por quê" é informação; silêncio não é — foi o silêncio,
não o resultado ruim, que fez uma casa virar uma mancha sem ninguém entender.

### §20 — otimizar não pode piorar

Se a nota depois for menor que a nota antes, a versão otimizada é descartada e
o sprite original volta. Um corretor que às vezes estraga é pior que nenhum
corretor, porque ninguém consegue prever qual dos dois recebeu.

A exceção é ficar tecnicamente correto: um asset que passou a ser Pixel Exact
com nota menor **melhorou**, e desfazer isso devolveria um arquivo fora da
especificação com um número mais bonito ao lado.

## 5. O que o Optimizer não faz (§79)

Ele **corrige o que um motor gerou; não gera no lugar dele**. Na prática:

- **não desenha contorno que não existe.** Contorno esfarelado é remendado;
  contorno ausente é decisão de estilo, e estilo é do profile e do motor. A
  fronteira é medida: um remendo pode cobrir no máximo 30% da fronteira do
  sprite (`MAX_OUTLINE_PATCH_RATIO`). Acima disso não há contorno a remendar —
  pintar a volta inteira engordaria o sprite em um anel, e mais um a cada volta
  do laço;
- **não preenche canvas vazio.** Inventar pixels para tapar o buraco entregaria
  um asset que ninguém pediu, com nota melhor;
- **não move o sprite.** Reenquadrar é do `PixelPostProcessor`, e o
  `_harden_spec` já tenta;
- **não aparece em lista nenhuma da interface** (§76). Ele não está no
  `EngineRegistry`, não tem `manifest.json` e não é escolhível.

## 6. As ferramentas (§40)

`set_pixel`, `erase_pixel`, `draw_pixels`, `replace_color`, `inspect_canvas`,
`inspect_region`, `repair_outline`, `connect_cluster`.

O vocabulário é de **reparo**, não de desenho: `repair_outline` existe,
`draw_circle` não. As oito cobrem os problemas que o `PixelValidator` sabe
medir hoje, e uma ferramenta sem problema medido correspondente é uma
ferramenta que ninguém saberia quando usar.

Duas guardas valem em **cada** chamada, e as duas ficam no executor:

**Coordenada inteira (§15).** `13.5` é recusado, não truncado — meio pixel não
existe na grade, e truncar em silêncio esconderia um erro de planejamento até
ele aparecer na imagem. `13.0` passa: é o que o JSON produz o tempo todo.

**A paleta manda (§16, §67).** Com `palette.mode = locked`, uma cor de fora é
**recusada** e o reparo não acontece — aproximar seria decidir por conta
própria qual cor do projeto o artista quis. Com `max_colors` e o orçamento
cheio, ela é **resolvida** para a mais próxima em uso: aqui o que importa é o
número, e recusar deixaria um buraco no sprite para respeitar uma contagem.

## 7. Os estados (§23, §45)

| status | o que significa |
| --- | --- |
| `skipped` | o Optimizer olhou e não havia o que corrigir |
| `optimized` | houve correção |
| `no_safe_repairs` | havia problema, nenhum com correção honesta |
| `exhausted` | as três voltas acabaram com problema em aberto |
| `disabled` | a instalação desligou o Optimizer |

`skipped` **não** quer dizer que o estágio foi pulado (§46). Ler assim é
reintroduzir a otimização opcional sem que ninguém tenha decidido isso.

O teto de três voltas (§19) não é economia de tempo: é o que separa "corrigir"
de "insistir". Um problema que sobrevive a três voltas não vai ceder na quarta
— ele é de outra natureza, e o lugar dele é a validação final.

## 8. O que saiu, e por quê

| saiu | motivo |
| --- | --- |
| `generation/strategies/` | não há duas estratégias a resolver (§52) |
| `generation/pixel_agent/` | o desenho pixel a pixel virou o Optimizer |
| `config/strategies.yaml` | virou `config/optimizer.yaml` |
| `GET /api/generation/strategies` | a tela pede só o catálogo de motores |
| `generation_strategy`, `pixel_agent` no pedido | §31 |
| `CreationMethodSelector.tsx` | §27 e §76 |
| `strategy`/`agent` no histórico e no asset | existe um produtor: o motor |

O que ficou do agente: o canvas, o executor, a guarda de paleta e o
vocabulário de ferramentas — todos em `pixel/optimizer/`, agora trabalhando
**sobre** a saída de um motor em vez de no lugar dela. O cliente de LLM ficou
em `assetflow/llm/`, onde virou o revisor por modelo da seção 9.

## 9. Configuração

`config/optimizer.yaml`:

```yaml
optimizer:
  enabled: true          # interruptor de INSTALAÇÃO, não de pedido
  max_iterations: 3
  reviewer:
    type: "heuristic"    # heuristic | llm
```

`enabled: false` existe para diagnóstico, e o job registra `disabled` — um
estágio que não rodou precisa aparecer no relatório, nunca sumir. Sem esse
status, um servidor com a otimização desligada produziria relatórios
indistinguíveis dos de um servidor que otimizou e não achou nada.

### O revisor por LLM (§42)

`reviewer.type: llm` troca o diagnóstico por um modelo — e **só** o
diagnóstico. O revisor determinístico enxerga o que o `PixelValidator` sabe
medir; ele nunca vai notar que a chaminé ficou solta do telhado, porque
"chaminé" não é uma medida.

O que **não** muda com ele ligado: quem decide o reparo continua sendo o
`RepairPlanner`, cada correção continua passando pela guarda de paleta e pelo
log, e a regra do §20 continua descartando a otimização que baixa a nota. O
pior caso de um laudo alucinado é um reparo inútil registrado — nunca um
sprite destruído.

Ele mora em `assetflow/llm/pixel_reviewer.py`, e não dentro de
`pixel/optimizer/`: a ilha Pixel Exact não faz rede, não lê configuração e não
conhece fornecedor. A ilha define o contrato, esta camada o implementa, e o
`bootstrap` faz a injeção.

Queda é rebaixamento, nunca falha: provedor fora do ar, JSON quebrado ou
resposta vazia caem no revisor determinístico, e `optimizer.json` passa a
registrar `reviewer: heuristic`. Uma geração não morre porque um modelo de
texto não respondeu.

```bash
ollama serve
ollama pull qwen2.5:7b
# e então, em config/optimizer.yaml:
#   reviewer: { type: llm, base_url: "http://localhost:11434/v1", model: "qwen2.5:7b" }
```

## 10. O que fica registrado

Por variação, quando houve correção (§47):

| arquivo | conteúdo |
| --- | --- |
| `postprocessed.png` | o sprite antes do Optimizer |
| `initial_validation.json` | a validação V1 |
| `optimizer.json` | laudos, planos, recusas, status |
| `optimizer_actions.json` | cada tool call, com motivo e pixels alterados |
| `logical.png` / `validation.json` | o asset entregue e a validação V2 |

Sem correção, os quatro primeiros não são gravados: seriam bytes idênticos aos
dos dois últimos, e a duplicata faria parecer que houve correção onde não
houve.

Nas métricas do job (§68): `optimizer_status`, `optimizer_iterations`,
`optimizer_tool_calls`, `optimizer_pixels_changed`, `optimizer_reverted`,
`quality_score_before_optimizer` e `quality_improvement`.

## 11. O benchmark (§69)

Todos os motores atravessam o **mesmo** Optimizer, então a diferença entre duas
linhas da tabela é a diferença entre os motores — não entre pipelines. As
colunas novas respondem à pergunta que interessa de verdade: *quanta correção a
saída deste motor exigiu?*

```bash
python scripts/benchmark_engines.py --targets flux-pixel-v1,mock-image-v1
```

Um motor que entrega sprites já limpos aparece com zero pixels corrigidos — e é
essa a informação que a tabela de notas finais, sozinha, esconderia.

## 12. Os testes

`tests/test_pixel_optimizer.py` protege, entre outras coisas:

- o pedido não tem campo para desligar a otimização (§33, §34);
- todo motor habilitado produz um asset com laudo de otimização (§57);
- o Optimizer não está no registry nem no catálogo (§58, §76);
- um pixel isolado de cor usada é preservado **com motivo** (§17);
- uma cor fora da paleta travada é recusada (§67);
- uma otimização que baixa a nota é descartada (§20);
- resolução, alpha binário e orçamento de cores sobrevivem (§63 a §66);
- o laço para no teto (§19), e `skipped` não é ausência de estágio (§46).

`tests/test_llm_pixel_reviewer.py` cobre o revisor por modelo, sem tocar a
rede: o laudo que nomeia o que o validador não mede, a queda que rebaixa em
vez de falhar, a coordenada fora da grade que é descartada sem levar o laudo
junto, e — o mais importante — o laudo alucinado que **não** consegue mexer no
sprite.
