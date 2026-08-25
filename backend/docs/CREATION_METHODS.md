# Métodos de criação, motores e agentes

> Documento de referência do plano *"Correção da Arquitetura de Geração"*. As
> docstrings do código citam este plano como `plano de correção §N`.

## 1. O problema que isto corrige

A tela tinha um seletor só, chamado **Motor**:

```
MOTOR
├─ Automático
├─ SDXL Diffusers Engine
├─ FLUX Pixel
├─ Pixel Forge
├─ SD-πXL
└─ Texel-style Agent        <- este não é um motor
```

Os quatro primeiros são modelos que recebem um prompt e devolvem uma imagem. O
último **planeja, desenha com ferramentas, olha o resultado e volta atrás** —
uma estratégia inteira, com outro tempo de resposta e outros controles.

Oferecê-los juntos dizia à pessoa que os cinco eram intercambiáveis. E, do
lado do código, punha um agente no `EngineRegistry`, onde a única pergunta
possível é "qual tecnologia gera esta imagem?".

## 2. A separação, em uma linha cada

```
STRATEGY       como o asset será criado
ENGINE         qual tecnologia/modelo gera uma imagem
AGENT          sistema que toma decisões e usa ferramentas
POSTPROCESSOR  normaliza/corrige propriedades técnicas
VALIDATOR      mede e aprova/reprova
```

Nunca misturar. É a regra final do plano (§51), e é o que os testes de
`tests/test_generation_strategy.py` protegem.

## 3. A tela

```
MÉTODO DE CRIAÇÃO                 MÉTODO DE CRIAÇÃO
├─ Automático                     ├─ Automático
├─ Modelo de imagem  ──┐          └─ Agente Pixel  ──┐
└─ Agente Pixel        │                             │
                       ▼                             ▼
                  MOTOR                          AGENTE
                  ├─ Automático                  └─ AssetFlow Pixel Agent
                  ├─ FLUX Pixel
                  ├─ SD-πXL                      QUALIDADE
                  ├─ Pixel Forge                 ├─ Automático
                  └─ SDXL                        ├─ Rápido
                                                 ├─ Balanceado
                                                 └─ Detalhado
```

Em **Automático** não aparece nenhum dos dois. Depois da resolução, a tela
mostra o que foi escolhido e **por quê**:

```
Estratégia escolhida: Agente Pixel
Motivo: sprite pequeno: desenhar na própria grade preserva a silhueta,
        que é o que se lê em 32×32
```

Qual controle aparece depois do método **não** é decidido no frontend: vem do
backend, em `selects_engine` e `selects_agent` de cada método. Um
`if id === "pixel_agent"` no React poria uma regra de arquitetura na camada
errada.

## 4. O caminho de um pedido

```
FinalResolvedSpec
        │
        ▼
GenerationStrategyResolver          strategy.mode: model | pixel_agent
        │
   ┌────┴─────────────────┐
   ▼                      ▼
ModelGenerationStrategy   PixelAgentStrategy
   │                      │
   ▼                      ▼
EngineResolver            PlanningAgent -> DrawingPlan
   │                      │
   ▼                      ▼
FLUX / SDXL /             PixelToolExecutor -> PixelCanvas
SD-πXL / Pixel Forge      │
   │                      ▼
   │                      PixelReviewer -> reparo (pelas ferramentas)
   └──────────┬───────────┘
              ▼
       PixelPostProcessor
              ▼
        PixelValidator          <- obrigatório nos dois caminhos (§30)
              ▼
       PixelAcceptancePolicy
              ▼
            Asset
```

O `PixelValidator` roda igual nos dois caminhos, e é isso que torna a
comparação justa. No caminho do agente o pós-processamento tende a não ter o
que corrigir — a saída já está no grid, com alpha binário e a paleta dentro do
orçamento.

## 5. Onde cada coisa mora

```
generation/strategies/base.py       o contrato de uma estratégia   (§12)
generation/strategies/registry.py   quais existem                  (§35)
generation/strategies/resolver.py   `auto` vira uma delas, e diz por quê (§11, §40)
generation/strategies/model.py      prompt -> motor -> imagem      (§13)

generation/pixel_agent/strategy.py  o encaixe do agente            (§15)
generation/pixel_agent/agent.py     planeja, desenha, revisa       (§15)
generation/pixel_agent/planner.py   o plano de desenho             (§17)
generation/pixel_agent/executor.py  aplica as ferramentas          (§19)
generation/pixel_agent/canvas.py    a grade pixel-native           (§20)
generation/pixel_agent/palette.py   as cores e o guarda delas      (§22)
generation/pixel_agent/reviewer.py  inspeciona e descreve          (§23, §24)
generation/pixel_agent/session.py   quanto esforço cabe            (§25)
generation/pixel_agent/contracts/   plano, comandos, laudo
generation/pixel_agent/tools/       uma ferramenta por arquivo     (§16)

config/strategies.yaml              o que "Automático" prefere     (§40)
config/engine_policy.yaml           qual motor, dentro de `model`  (§16)
```

`auto` **não** está no `GenerationStrategyRegistry`, e não é esquecimento: ele
não é um jeito de criar, é a ausência de escolha. O registro recusa registrá-lo.

## 6. Regras do agente que o código garante

**§20 — canvas pixel-native.** Resolução lógica 32×32 significa canvas 32×32.
Cada coordenada é um pixel lógico, e o PNG entregue tem esse tamanho — o
pós-processamento encontra origem e alvo iguais e não reamostra nada.

**§21 — nada de coordenada fracionária.** `12.5` é recusado, não truncado.
Meio pixel não existe na grade, e truncar em silêncio esconderia um erro de
planejamento até ele aparecer na imagem. `12.0` passa: é inteiro escrito como
float, o que acontece o tempo todo em JSON.

**§22 — paleta fechada.** Com 16 cores no orçamento não existe décima sétima.
O `PaletteManager` fica no executor, então a regra vale **durante** o desenho:
uma cor nova é resolvida para a mais próxima em uso, na hora, em vez de virar
um remapeamento cego depois de tudo pintado.

**§24 — o revisor não altera o canvas.** Ele devolve `ReviewInstructions` com
problemas e ações recomendadas; quem executa é o agente, sempre pelas
ferramentas. É o que mantém a promessa de que o log de tool calls reconstrói o
resultado — inclusive as correções.

**§25 — o laço tem limite.** `fast` 2, `balanced` 4, `detailed` 6 iterações,
configuráveis em `strategies.yaml`. Ele também para cedo quando o laudo não
tem mais nada acionável.

Uma ordem que custou um teste: **limpar antes, contornar depois**. Contornar
primeiro envolve o pixel solto que a limpeza ia remover — ele deixa de ser
órfão, sobrevive, e vira um borrão de cinco pixels.

## 7. O planejador: receitas ou modelo de linguagem

O agente tem duas partes, e só uma delas já teve limite de vocabulário:

```
PLANNER                      decide O QUE desenhar      <- trocável
CANVAS + TOOLS + REVIEWER    garante COMO fica          <- sempre o mesmo
```

O segundo bloco nunca teve limite: ele desenha o que o plano mandar, na grade
exata, dentro do orçamento de cores, com contorno e log reconstruível. O
limite era o planejador.

| planejador | vocabulário | custo | quando usar |
|---|---|---|---|
| `recipes` (padrão) | 9 objetos | microssegundos, sem rede | os objetos que ele conhece; reserva |
| `llm` | **qualquer sujeito** | uma chamada de modelo | tudo o mais |

### Ligar o planejador por LLM

Qualquer API compatível com OpenAI serve. O caminho gratuito é local:

```bash
ollama serve
ollama pull qwen2.5:7b
```

```yaml
# config/strategies.yaml
pixel_agent:
  planner:
    type: "llm"
    base_url: "http://localhost:11434/v1"
    model: "qwen2.5:7b"
```

Com OpenAI ou outro serviço pago, a chave vai em **variável de ambiente** — o
YAML é versionado, e o que fica nele é só o nome da variável:

```yaml
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o-mini"
    api_key_env: "ASSETFLOW_PLANNER_API_KEY"
```

Reinicie o backend depois de editar: `config/*.yaml` não entra no reload.

### O que esperar

Um modelo de linguagem posicionando retângulos e círculos produz sprites
**simples e legíveis** — não arte detalhada. Para uma chave, uma placa, um
barril, um livro, uma escrivaninha, ele tende a ganhar de um modelo de
difusão reduzido a 32×32, porque cada pixel foi posto de propósito. Para um
personagem com rosto e roupa em 64×64, a difusão ganha — e é para isso que
existe o método "Modelo de imagem".

Modelos maiores planejam melhor. Um 7B já produz sprites utilizáveis para
objetos simples; abaixo disso, espere muitos planos recusados.

### Tudo que vem do modelo é entrada não confiável

O parse recusa, com motivo específico: coordenada fora do canvas, coordenada
fracionária, ferramenta inventada, cor malformada, JSON com prosa em volta,
plano sem nenhuma chamada. E o motivo **volta ao modelo** como crítica na
segunda tentativa — é o que resolve a maior parte dos planos malformados.

Recusar em vez de recortar é deliberado: uma coordenada fora significa que o
modelo entendeu o tamanho errado, e recortar produziria uma forma achatada
contra a borda que ninguém pediu.

Esgotadas as tentativas, ou com o provedor fora do ar, o agente cai nas
receitas **e avisa no job**. Uma queda silenciosa seria o mesmo defeito de
entregar uma forma genérica sem explicação.

### Sem SDK de fornecedor

A chamada é `urllib` da biblioteca padrão, não o pacote `openai`. O teste de
fronteiras proíbe SDKs de fornecedor fora de `generation/engines/<gaveta>/`, e
a proibição está certa: ela é o que impede o AssetFlow de trocar a dependência
de um modelo de imagem pela de um provedor de LLM. Falar HTTP puro mantém o
planejador livre de fornecedor de fato, e não só por organização de pastas.

## 8. O vocabulário das receitas

Com `type: recipes` — o padrão — o planejador desenha por receitas, e o
vocabulário é finito:

```
tree     rock     potion    chest    tile
house    sword    coin      character         generic (fallback)
```

Um sujeito fora dessa lista cai em `generic` — um volume sólido com luz e
sombra, que não tenta adivinhar o que é o objeto. Isso é honesto, e sozinho
era **insuficiente**: um pedido de "house" saía como uma forma genérica e nada
na tela dizia por quê. Quem via o resultado não tinha como distinguir "o
sistema quebrou" de "este objeto está fora do vocabulário".

Duas coisas fecham essa lacuna:

**A escolha automática não manda para o agente o que ele não sabe desenhar.**
`PixelAgentStrategy.accepts()` consulta `planner.recognizes()`, e um sujeito
desconhecido faz o `auto` cair em "Modelo de imagem". Quem decide isso é a
estratégia, não o resolvedor: o resolvedor não teria como saber que as
receitas não cobrem "house".

Com o planejador por LLM, `recognizes()` responde **sim para tudo** — e o
desvio deixa de acontecer. É a mesma pergunta, com outra resposta, porque
mudou quem planeja.

**A escolha manual é respeitada e explicada.** Quem escolhe "Agente Pixel"
recebe o agente, e o job traz o aviso:

> o Agente Pixel ainda não sabe desenhar 'X': ele produziu uma forma genérica.
> Para este objeto, o método 'Modelo de imagem' tende a dar um resultado melhor

Os avisos do backend agora chegam à tela (`GenerationNotices`). Eles não
chegavam, e essa era a causa real do sintoma: o sistema **sabia** o que tinha
acontecido e não contava.

### Acrescentar um sujeito

1. termos em `RECIPE_KEYWORDS` (`planner.py`), em português e inglês;
2. uma paleta em `PALETTES` (`palette.py`), se as cores forem próprias;
3. uma função `_recipe_<nome>` ao lado das outras;
4. o nome no dicionário de `PlanningAgent.__init__`.

A ordem de `RECIPE_KEYWORDS` importa: a primeira receita cujo termo aparecer
no sujeito vence. Termos que nomeiam o **objeto** vêm antes dos que nomeiam o
**material** — é por isso que `house` vem antes de `tile` ("casa de tijolos")
e `tile` antes de `rock` ("stone tile").

## 9. Mocks fora de produção (§6)

As gavetas de referência declaram `catalog.dev_only: true` no manifesto. Com
`ASSETFLOW_APP_ENV=production` elas **não são registradas** — não é "escondidas".
Uma gaveta registrada continua resolvível por capacidade, e "invisível mas
usável" deixaria um job de produção cair em um mock sem ninguém ver.

O padrão é `development`, deliberadamente: produção é um ambiente que alguém
configura; desenvolvimento é onde se cai sem configurar, e uma máquina sem GPU
ficaria sem nenhum motor logo depois do `git clone`.

## 10. Comparar métodos (§43)

```bash
python scripts/benchmark_engines.py --targets pixel_agent,model:flux-pixel-v1
python scripts/benchmark_engines.py --list
```

O alvo do benchmark é **método + motor**, e é isso que permite pôr o agente e
o FLUX na mesma tabela sem fingir que são a mesma tecnologia:

```
método / motor            casos   falha   exato   nota  correção   órfãos tempo(ms)
pixel_agent                   3    0.0%  100.0%   78.3      0.0%     2.5%        55
model:mock-image-v1           3    0.0%  100.0%   57.7      0.0%     8.9%       227
```

Um caso atendido por outro motor, ou por outro método, **não** conta como
sucesso do alvo pedido — senão o relatório credita a um caminho o trabalho de
outro.

## 11. O que ainda não existe

**Planejador por LLM verificado contra um modelo real.** O contrato em volta
dele está testado — prompt, parse estrito, crítica na segunda tentativa,
queda para receitas, e o caminho HTTP contra um servidor de mentira. O que
não foi verificado é a **qualidade do desenho** de um modelo de verdade:
isso depende do modelo escolhido e não se testa em CI.

**Referência conceitual (§26, §27, §39).** O campo existe no contrato
(`concept_reference`), é validado e é persistido; o agente ainda não a usa. O
desenho está fechado: um motor gera a referência, e ela **não é o asset** — ele
entra como *supporting engine*, registrado em campo próprio para que "me
ajudou a pensar" nunca se confunda com "gerou isto".

**Outros agentes.** O registro comporta mais de um; hoje só existe o
`assetflow_pixel_agent`.
