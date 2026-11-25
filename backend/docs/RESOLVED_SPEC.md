# Final Resolved Spec — do texto ao contrato de geração

Documento de referência do módulo `assetflow/generation/spec/` e dos contratos
em `assetflow/generation/schemas/resolved_spec.py`. Complemento de
[ARCHITECTURE.md](ARCHITECTURE.md), que descreve *trocar o motor sem tocar no
produto*, e de [PIXEL_EXACT.md](PIXEL_EXACT.md), que descreve *garantir que o
arquivo entregue seja mesmo Pixel Art*. Aqui o assunto é anterior aos dois:

> O que o AssetFlow executa é o que a pessoa pediu?

As docstrings do código citam este documento como `plano T→J §N`, seguindo a
mesma convenção que `plano §N` (README.md) e `plano Pixel §N`
(PIXEL_EXACT.md). Os números de seção abaixo são os do plano original.

---

## 1. Os dois defeitos

Dois sintomas motivaram o módulo. Pareciam independentes; eram a mesma causa.

**A árvore que era um personagem.** O pedido `tree` produzia:

```json
{ "asset_type": "character" }
```

Não porque alguém tivesse decidido que árvore é personagem, mas porque
**ninguém decidia nada**. O tipo vinha de `profile.asset.type`, e o profile vem
do modo escolhido na interface — que só conhece "Pixel Art" e "2D Normal". Como
o modo Pixel Art manda `pixel_character_64`, tudo que fosse pedido em Pixel Art
era um personagem. O sujeito da frase nunca era lido.

Não era só um rótulo errado no JSON: o `PromptBuilder` é escolhido pelo tipo, e
uma árvore classificada como personagem era **descrita ao motor** como
personagem — com pose "idle", corpo inteiro, e a lista de `avoid` de
personagem, que não barra "characters" nem "hands".

**O 32×32 que saía 64×64.** A pessoa editava a resolução lógica no painel, e o
asset saía no tamanho do profile assim mesmo — e ainda recebia o selo
`PIXEL EXACT ✓`, porque o validador também conferia contra o profile.

A causa não era um valor errado em lugar nenhum. Era **não existir uma ordem**:
cada camada consultava a fonte que tinha à mão, e o profile respondia por
último simplesmente porque estava mais perto na hora de perguntar.

```text
pipeline               profile.output.render_*      ─┐
pós-processamento      profile / pixel_profile       ├─ três leituras
validação              o mesmo spec do profile      ─┘   independentes
```

O que a pessoa pediu não estava representado em lugar nenhum do caminho.

---

## 2. A regra nova: o JSON é um contrato, não uma sugestão

```text
Texto do usuário
   -> 1. ExplicitConstraintExtractor    restrições exatas
   -> 2. AssetTypeClassifier            classificação semântica
   -> 3. ConstraintResolver             precedência
   -> 4. FinalResolvedSpec              contrato imutável
   -> 5. Generation Job
   -> 6. Engine
```

O motor só recebe o que passou pelo `FinalResolvedSpec`. E vale a regra que
organiza o módulo inteiro (§37):

> **Nenhum componente recalcula ou reinfere um campo que já exista no
> `FinalResolvedSpec`.**

Pipeline, pós-processamento, validação e interface **leem**. Nenhum deles
reinterpreta o prompt, e nenhum deles volta a perguntar ao profile por
resolução lógica, paleta, fundo ou tipo de asset.

---

## 3. A ordem de precedência (§9)

Escrita uma vez, em `SPEC_PRECEDENCE` (`schemas/resolved_spec.py`), da menor
para a maior prioridade:

```text
GLOBAL_DEFAULT      padrão do próprio contrato
PROFILE_DEFAULT     Generation Profile (config/profiles.yaml)
CATEGORY_INFERENCE  deduzido de outro campo resolvido (o corpo pela categoria)
INFERENCE           classificador semântico e prompt builder
UI_SELECTION        controles da tela (campo `output` do pedido)
EXPLICIT_PROMPT     restrição escrita na descrição ("32x32", "8 cores")
MANUAL_OVERRIDE     edição do JSON final (campo `spec_overrides`)
```

O resolver aplica as camadas de baixo para cima; cada campo é um `_Slot` que
guarda **valor e origem**. Quem chega depois ganha, e a origem fica registrada.

Inverter dois itens desta lista é reintroduzir o bug do 32×32.

### Por que a origem importa (§16 e §23)

Guardar a origem não é observabilidade de luxo: é o que separa

```text
"a pessoa pediu 64×64"          EXPLICIT_PROMPT
"ninguém disse nada e o          PROFILE_DEFAULT
 profile respondeu 64×64"
```

Sem essa distinção o sistema não tem como saber o que pode sobrescrever — e
passa a tratar o próprio padrão como se fosse pedido explícito. É também o que
permite à interface dizer "padrão do estilo" em vez de deixar a pessoa supor
que aquele número foi escolha dela.

O `FinalResolvedSpec.sources` carrega isso por campo, e `notes` registra os
conflitos resolvidos: *"resolução do profile (64×64) substituída por 32×32 —
origem: manual_override"* (§31).

---

## 4. Extrair antes de classificar (§26)

A ordem das duas primeiras etapas não é arbitrária.

```text
"tree 32x32, 8 colors, transparent background"
        │
        ├─ extrai:  32×32, 8 cores, fundo transparente
        │
        └─ sobra:   "tree"        ← é isto que o classificador vê
```

Duas consequências, e as duas importam:

1. o número vira contrato imediatamente, com origem `explicit_prompt`, e
   nenhuma camada posterior o sobrescreve;
2. o texto que segue para o classificador está **limpo**.

A segunda é a que evita um erro sutil: `transparent background` contém a
palavra *background*, que é um marker do tipo `background`. Classificar antes
de extrair transformaria toda árvore com fundo transparente em um cenário. Por
isso o padrão de fundo transparente é consumido primeiro, e por isso
`background` **sozinho** nunca casa como restrição de fundo — em
`forest background` ela nomeia o tipo do asset.

O sujeito que sobra vai inteiro para o motor. Se os números não fossem
removidos, o modelo tentaria desenhar o texto.

---

## 5. A taxonomia é configuração (§5)

`config/asset_taxonomy/*.yaml`, um arquivo por tipo, termos em português e
inglês. Acrescentar "candelabro" ao vocabulário de props não pode exigir
editar um `.py` — é a mesma regra que já vale para profiles, engines e
contratos Pixel.

```yaml
type: prop
priority: 40
markers:    { en: [prop, object],  pt: [objeto, item] }
keywords:   { en: [tree, rock],    pt: [árvore, pedra] }
categories: { vegetation: [tree, árvore] }
```

A distinção entre as duas listas é o que resolve os casos que uma lista única
erra:

```text
markers    nomeiam o TIPO de asset     "tileset", "fundo", "ícone"
keywords   nomeiam o SUJEITO           "grass", "floresta", "espada"
```

Em `grass tileset` as duas casam. O marker ganha, e o resultado é um tileset —
que é o que a pessoa pediu. A ordem de força completa está em `_strength()`
(`spec/classifier.py`):

```text
1. marker antes de keyword       "grass tileset" é um tileset
2. frase longa antes de curta    "sala do trono" ganha de "sala"
3. prioridade do tipo            "guerreiro na floresta" é um personagem
```

O que ninguém sabe, ninguém inventa (§23): quando nada casa, a classificação
devolve silêncio, e o profile continua respondendo — com a origem
`profile_default` registrada, para que o padrão não se disfarce de pedido.

A camada B (`ClassifierFallback`) é um ponto de extensão declarado. Hoje o
AssetFlow não tem intérprete de linguagem natural; quando tiver, ele entra
por ali e continua **abaixo** de qualquer restrição explícita.

---

## 6. Dois nomes para dois tamanhos (§12 e §13)

Existiam dois conceitos disputando as palavras `width`/`height`, e é dessa
ambiguidade que nasce a classe de bugs em que 32 vira 64. Agora eles têm nomes
que não se confundem:

```text
LogicalResolution     o tamanho do ASSET      32×32     o arquivo entregue
RenderResolution      o tamanho do MOTOR      512×512   a imagem bruta
```

O `PixelExactProcessor` recebe a resolução lógica pronta (§14). Ele não infere,
não escolhe entre 32 e 64 — executa.

---

## 7. Nunca corrigir em silêncio (§30)

Um pedido que não pode ser atendido vira `InvalidGenerationRequest` com o
motivo escrito em português. Nunca um valor trocado por outro sem aviso.

```text
resolução 4×4                 → recusa: o limite é de 8 a 1024 por lado
32×32 em pedido modo Studio   → recusa: resolução lógica só existe em Pixel Art
só a largura informada        → recusa: o outro lado viria do profile
paleta em pedido modo Studio  → recusa: limite de cores não se aplica
```

Os profiles Studio saíram na Fase A do plano do app; o modo continua no
contrato (`AssetMode.STUDIO`), e o pedido chega a ele pelo campo `mode`.

O caso da metade da resolução merece nota: aceitar `logical_width=32` sozinho
produziria 32×64, uma proporção nova que ninguém pediu. Aceitar e ignorar é a
mesma doença que corrigir em silêncio — o número precisa ter efeito, ou o
pedido precisa ser recusado.

Esta é a única família de erro cuja mensagem do backend a interface exibe
crua: ela é escrita para ser lida por quem pediu. `detail.errors` traz o campo
no mesmo formato que o handler de 422 já usava.

---

## 8. Identidade e rastro (§34 e §35)

`spec_id` e `spec_hash` são **determinísticos**: derivam do conteúdo, e não de
um UUID. Dois pedidos equivalentes produzem o mesmo id — é o que permite
reconhecê-los como equivalentes.

O hash cobre os valores, e não `sources`/`notes`: duas gerações que resultam em
64×64 com 16 cores produzem o mesmo asset, tenham vindo do profile ou da mão de
alguém.

O contrato é persistido em três lugares, cada um por um motivo:

```text
Job.resolved_spec                    o que o worker executa
asset.metadata.spec_id/spec_hash     prova de qual configuração gerou o asset
resolved_spec.json (artefato)        o contrato ao lado do arquivo, para depurar
GenerationRecord.metadata            histórico completo, para comparar gerações
```

---

## 9. Onde o spec é resolvido — e onde não é

**Resolvido uma vez, em `GenerationService.submit`.** O resultado viaja dentro
do `Job` e o worker apenas o repassa ao `PipelineContext`.

```python
# jobs/worker.py
resolved=self._resolved_spec(job, profile)   # job.resolved_spec, e nada mais
```

Resolver de novo no worker reabriria exatamente a porta que o módulo fecha: uma
segunda chance de o pedido ser trocado por um padrão. O fallback existe só para
job montado à mão (teste, fila legada) e usa o **mesmo** resolver, de modo que
continua não havendo uma segunda regra.

`GenerationService.preview_prompt` chama a mesma função. É isso que sustenta a
promessa do §33 — *o JSON mostrado é o JSON executado* — e o que impede a tela
de descrever uma geração parecida em vez da que vai acontecer.

---

## 10. O selo, agora, mede o pedido (§43 e §44)

A ponte `postprocessing/pixel/spec.py` é o único lugar onde o
`FinalResolvedSpec` encosta no `PixelOutputSpec`:

```text
profile Pixel (config/pixel_profiles.yaml)     ← ponto de partida
    < Final Resolved Spec                      ← resolução lógica, paleta, fundo
```

O spec resolvido vem por último porque ele **já** é o resultado da precedência
inteira. Quando ninguém pediu nada, ele carrega os próprios valores do profile
e a sobreposição não muda um pixel; quando alguém pediu 32×32, é ali que 32×32
chega ao arquivo.

E, porque o mesmo `PixelOutputSpec` alimenta o validador logo depois, o
`PX-DIM-001` passa a cobrar o que a pessoa pediu. Antes, um asset de 64×64
passava no check mesmo quando 32×32 tinha sido pedido, e o selo aparecia sobre
o arquivo errado.

---

## 11. A interface (§17, §18, §32 e §45)

O painel "O que o AssetFlow entendeu" tem três abas:

```text
Interpretação   o contrato em português, com a origem de cada valor
JSON final      o mesmo objeto, cru e editável
Prompt          a semântica enviada ao motor
```

A primeira existe porque a versão anterior mostrava JSON e mais nada — quem
pedia uma árvore e recebia um personagem tinha a resposta na tela,
`"asset_type": "character"`, e nenhuma chance de notar.

Os dois níveis de correção da interface não se confundem:

```text
controles (tipo, resolução, paleta, fundo, vista)  →  output          nível 3
edição do JSON final                               →  spec_overrides  nível 1
```

Um controle em **Automático** não envia campo nenhum. Ele não manda o padrão do
estilo — ele se cala, e a resolução acontece nas camadas de baixo. É a mesma
distinção do §23, do lado do cliente.

A edição do JSON envia apenas o **diff** contra o spec resolvido. Mandar o
objeto inteiro de volta congelaria também os campos não tocados, e mudar a
descrição depois deixaria de ter efeito.

---

## 12. Testes que não devem ser afrouxados

`tests/test_resolved_spec.py` (§39 a §43) e `tests/test_asset_taxonomy.py`.

Os do §40, §41 e §42 são declarados permanentes pelo plano — são a prova de que
os dois sintomas originais não voltaram:

```python
assert resolved.asset.type == "prop"        # §40  a árvore
assert resolved.logical_width == 32         # §41  a resolução
assert logical_png.size == (32, 32)         # §42  o arquivo
```

O §42 mede o **arquivo**, e não o relatório. O spec dizer 32 e o PNG ter 64 era
exatamente o defeito.

---

## Os três eixos do sujeito

Um erro que este módulo já corrigiu uma vez, e que reaparece um nível abaixo se
ninguém o vigiar: **colapsar eixos diferentes no mesmo campo**.

```
asset.type            que papel o asset cumpre no jogo   ->  character
asset.category        que tipo de coisa é                ->  creature
character.body_type   que forma o corpo tem              ->  quadruped
```

Um goblin é `creature` de corpo **humanoide**. Um lobo é `creature`
**quadrúpede**. Sem o terceiro eixo os dois chegam ao motor como "character", e
ele desenha o lobo em pé — exatamente como uma árvore virava `character` antes
de o segundo eixo existir.

A topologia é **inferida do sujeito**, não pedida em um dropdown: quem escreve
"um lobo" já disse quadrúpede. Inferência é o nível 3 da precedência, então uma
escolha explícita na tela ganha — é o que permite pedir um lobo antropomórfico
sem reescrever a frase.

O vocabulário é configuração: `config/asset_taxonomy/character.yaml`, seção
`body_types`. Um termo que aparece **só** ali também é registrado como sujeito
do tipo — acrescentar uma ave é uma edição, não duas.

`unknown` é silêncio honesto e **não entra no prompt**. Chutar `humanoid` para
uma árvore mandaria "humanoid character" junto da palavra "árvore", e o modelo
tentaria conciliar as duas coisas.

O classificador casa a palavra inteira e não flexiona: "arqueiras" não casa
"arqueira", que não casa "arqueiro". Por isso o `character.yaml` traz uma linha
por palavra, com masculino, feminino e plurais, e
`tests/test_taxonomia_flexoes.py` confere que nenhuma forma ficou de fora numa
lista em que as outras estão. Foi assim que o recorte do MCP saiu sem medidas
para uma arqueira: "arqueiro" estava em `body_types`, e ela não.

### O corpo que a categoria implica

Quando nenhuma camada disse a forma, o resolvedor pergunta à categoria
resolvida — **uma vez, no resolvedor**, e nunca no recorte ou no prompt, que só
leem o spec. A tabela é configuração, na seção `category_body_types` do
`character.yaml`, e só lista categoria em que **todo** membro tem o mesmo
corpo:

```
humanoid    -> humanoid        (cavaleiro, fada, astronauta, pessoa…)
creature    -> (nada)          goblin humanoide, lobo quadrúpede, slime amorfo
mechanical  -> (nada)          robô é humanoide; um drone não seria
```

O corpo deduzido leva a origem `category_inference` ("inferido da categoria"),
logo abaixo de `inference` na precedência: um termo do texto que nomeie o
corpo, a tela e a correção manual ganham dela. Uma linha da tabela que cite
categoria ou corpo inexistente sai com aviso na carga, sem levar o resto do
vocabulário junto.

### A regra de sobrevivência

A categoria inferida morre quando outra camada troca o **tipo**. A topologia
morre quando outra camada troca o **sujeito** — porque é dele que ela deriva.
Não é a mesma regra:

```
"sprite sheet de um lobo"        -> tipo virou spritesheet, corpo continua quadruped
subject corrigido para "espada"  -> corpo volta a unknown
```

A dedução pela categoria segue a mesma regra: com o sujeito trocado à mão, a
categoria lida no texto antigo descreve o sujeito que saiu e não deduz corpo
nenhum.

---

## O que o AssetFlow promete sobre cada campo

A precedência responde *de onde veio o valor*. Falta a outra metade: *o que
acontece se o resultado não bater com ele?*

Sem essa distinção a interface trata `32×32` e "contorno seletivo" como a mesma
promessa. Não são — e chamar o segundo de erro é mentir sobre o que o sistema
controla.

| classe | promessa | exemplos |
|---|---|---|
| `hard` | o AssetFlow **garante**; não bater reprova | `logical_resolution`, `palette`, `background` |
| `semantic` | o motor tenta, o validador **mede** | `asset.type`, `character.body_type`, `composition.view` |
| `style` | orientação; o Optimizer melhora o que der | `style.detail`, `style.outline`, `style.shading` |
| `engine_hint` | execução, sem promessa visual | `engine`, `generation.seed`, `render_resolution` |

Mora em `SPEC_CONSTRAINTS`, ao lado de `SPEC_PRECEDENCE`, e é servida à
interface em `PromptPreview.constraints` — não copiada no React, pelo mesmo
motivo do catálogo de motores: uma cópia envelheceria em silêncio.

Campo sem classe declarada cai em `semantic`, a resposta conservadora.
Prometer `hard` por omissão daria a um campo novo uma garantia que ninguém
escreveu.

### Estilo: `auto` não é "sem estilo"

`auto` significa **ninguém opinou**, e o compilador de prompt de cada motor
decide o que fazer com isso. A diferença é concreta: em `auto` o compilador do
GPT Image **não diz nada** sobre contorno, em vez de mandar um padrão. Um
prompt que sempre pede "contorno seletivo" tira do modelo uma decisão que
ninguém pediu para tirar.

E `detail` é separado de `shading` de propósito: um sprite pode ser muito
detalhado com sombreamento chapado, ou simples com sombreamento dramático.
Tratá-los como um controle só perderia metade das combinações.
