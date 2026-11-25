# Gaveta desenhista — o formato da receita

> Plano desenhista ([PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md)),
> Fase 1. Código em `assetflow/generation/engines/desenhista/`; testes em
> `tests/test_desenhista.py`.

A gaveta `desenhista-v1` não carrega modelo. O desenho vem do Claude, na
conversa, como uma **receita**: uma descrição curta, em camadas, do que pintar
em cada pixel da grade lógica. A gaveta transforma a receita em sprite, e o
resto do AssetFlow — Pixel Exact, Pixel Optimizer, validação, storage — segue
como para qualquer motor.

## 1. Onde a receita chega

Em `engine_options["desenhista-v1"]["receita"]`, um campo que o pedido já
levava da API até a gaveta (`AssetGenerationRequest.engine_options`). Quem
manda é o servidor MCP ([MCP.md](MCP.md)). O botão **Gerar** da tela não manda receita,
e a gaveta recusa com uma mensagem em português dizendo isso.

O **tamanho da grade não vem da receita**. Ele vem do `FinalResolvedSpec`, como
qualquer outro campo, e chega à gaveta em `output.logical_width/height`. O
campo `grade` da receita só confere: se ele não bater com o pedido, é erro.

## 2. O formato

```json
{
  "grade": [16, 16],
  "paleta": {"k": "#2d3436", "v": "#a8d8e8", "r": "#b03a2e", "R": "#e3584a", "m": "#8b5a2b", "b": "#ffffff"},
  "camadas": [
    {"nome": "silhueta", "espelho": "x", "ops": [
      {"elipse": [3, 5, 10, 10], "cor": "k"},
      {"ret": [6, 2, 2, 4], "cor": "k"}
    ]},
    {"nome": "vidro", "espelho": "x", "ops": [
      {"elipse": [4, 6, 8, 8], "cor": "v"},
      {"ret": [7, 3, 1, 4], "cor": "v"}
    ]},
    {"nome": "superficie", "espelho": "x", "ops": [
      {"linha": [4, 9, 7, 9], "cor": "R"}
    ]},
    {"nome": "liquido", "ops": [
      {"balde": [7, 11], "cor": "r"}
    ]},
    {"nome": "rolha", "espelho": "x", "ops": [
      {"ret": [6, 1, 2, 2], "cor": "m"}
    ]},
    {"nome": "brilho", "ops": [
      {"px": ["b.", ".b"], "em": [5, 7]}
    ]}
  ]
}
```

Esta é a poção de `exemplos/pocao_16x16.json`. O resultado, com `.` no
transparente:

```
    0123456789012345
 0  ................
 1  ......mmmm......
 2  ......mmmm......
 3  ......kvvk......
 4  ......kvvk......
 5  ......kvvk......
 6  ....kkvvvvkk....
 7  ....kbvvvvvk....
 8  ...kvvbvvvvvk...
 9  ...kRRRRRRRRk...
10  ...krrrrrrrrk...
11  ...krrrrrrrrk...
12  ....krrrrrrk....
13  ....kkrrrrkk....
14  ......kkkk......
15  ................
```

### Paleta

Um objeto de **chave de um caractere** para cor `"#rrggbb"`. A chave tem um
caractere para caber nas linhas de `px`. `.`, `-` e espaço são reservados.

Paleta pública pelo nome (`"pico-8"`, `"endesga-32"`) **não** entra na gaveta:
quem conhece as cores é a base de conhecimento
(`config/pixel_knowledge/paletas.yaml`), que as mostra no recorte de
`consultar_pedido` ([MCP.md](MCP.md) §4), e a receita chega com os
hexadecimais. Conhecimento mora na estante, não na gaveta.

### Camadas

Grupos de operações **com nome**, aplicados em ordem sobre a mesma grade — a
camada seguinte pinta por cima. O nome é único na receita: é por ele que o
remendo do MCP (`base: <id>`, [MCP.md](MCP.md) §3) troca só a camada `"brilho"` sem reenviar o
resto. Sem `nome`, a camada se chama `"camada N"`.

### Espelho

`"espelho": "x"`, `"y"` ou `"xy"` numa camada: as operações dela são
desenhadas e depois copiadas em torno do centro da grade.

- `x` reflete esquerda e direita: a coluna `c` vai para `largura - 1 - c`.
  Em largura ímpar a coluna do meio é o próprio espelho.
- `y` reflete cima e baixo, do mesmo jeito.
- `xy` faz os dois: os quatro quadrantes.
- **A cópia só preenche posições que a camada não pintou.** Se a camada
  pintou os dois lados, o que ela pintou vale. O espelho completa o desenho,
  nunca apaga uma decisão explícita.
- O espelho vale só para a própria camada.

É o jeito certo de fazer simetria, e não um atalho: uma linha de Bresenham
não é simétrica a si mesma refletida, então desenhar os dois lados à mão dá
degraus diferentes em cada lado.

### Operações

Origem no canto superior esquerdo, x para a direita, y para baixo — como no
`PixelCanvas` do Optimizer. Cada operação tem **exatamente uma** forma:

| Operação | Valor | Extras | O que pinta |
|---|---|---|---|
| `ret` | `[x, y, largura, altura]` | `cor`, `contorno` | o retângulo; com `contorno: true`, só a borda de 1 px |
| `elipse` | `[x, y, largura, altura]` | `cor`, `contorno` | as células cujo **centro** cai na elipse inscrita na caixa |
| `linha` | `[x0, y0, x1, y1, …]` | `cor` | Bresenham de 1 px ligando os pontos; o mesmo traçado nos dois sentidos |
| `poligono` | `[x0, y0, x1, y1, …]` (≥ 3 pontos) | `cor`, `contorno` | arestas + células de centro interno (par-ímpar); com `contorno`, só as arestas |
| `balde` | `[x, y]` | `cor` | a região de células iguais à de `(x, y)`, ligadas pelos 4 lados |
| `px` | `["..kk..", …]` | `em: [x, y]` | uma string por linha a partir de `em`; `.` mantém o que está embaixo, `-` apaga |

O `balde` enxerga tudo o que já foi pintado — pelas camadas anteriores e pelas
operações anteriores da mesma camada. **Ele não pode ficar em camada com
`espelho`**: ali a cópia só acontece no fim, o `balde` enxergaria o desenho
antes dela e vazaria pelo lado ainda vazio. A receita é recusada com erro, e
o caminho é o da poção: a superfície numa camada espelhada, o `balde` do
líquido na camada seguinte, sem espelho.

## 3. O que a gaveta entrega

- **A grade lógica, 1:1** (`catalog.exact_resolution: true`): um pixel do PNG
  por célula, alpha só 0 ou 255, as cores exatas da paleta. Não amplia até o
  tamanho de render: 512 não é múltiplo de 48, e ampliar só para o Pixel Exact
  reduzir de volta não acrescentaria nada.
- **Sem seed** (`supports.seed: false`): a mesma receita dá sempre o mesmo
  sprite.
- **Uma variação** (`limits.max_variations: 1`). Mais de uma seriam cópias. O
  kernel tem uma regra genérica para isso: uma gaveta sem seed não é dividida
  em lotes, e o pedido acima do limite falha com `InvalidGenerationRequest`
  antes de a gaveta rodar.
- No metadado do artefato: os nomes das camadas, o número de cores usadas e o
  `receita_sha256` (identidade da receita, estável à ordem das chaves).

## 4. Erros e avisos

Quem lê a mensagem é o Claude, que corrige e manda de novo. Toda mensagem diz
**onde** — `camadas[1] ('vidro').ops[0] (ret)` — e o que era esperado.

**Erro** (o job falha com `invalid_request`):

- sem receita, ou receita que não é objeto;
- chave desconhecida em qualquer nível (`"camada"` no lugar de `"camadas"`);
- paleta vazia, chave com mais de um caractere ou reservada, cor fora do
  formato `"#rrggbb"`;
- cor que não está na paleta, operação sem forma ou com duas, números errados;
- `px` com caractere fora da paleta, ou que só tem `.`;
- nome de camada repetido, `espelho` desconhecido, `balde` em camada com
  `espelho`;
- operação **inteira** fora da grade, `balde` fora dela, `grade` diferente do
  pedido;
- mais cores usadas do que o `max_colors` do spec;
- mais de uma variação.

**Aviso** (o asset sai, e o aviso vai junto no resultado): operação
**parcialmente** fora da grade. Ela é recortada, e o aviso diz quantos pixels
ficaram de fora.

## 5. Ver uma receita virar PNG

```bash
cd backend
python scripts/preview_engine.py --engine desenhista-v1 \
    --receita assetflow/generation/engines/desenhista/exemplos/pocao_16x16.json \
    --profile pixel_prop_64 --prompt "poção vermelha 16x16"
```

O `16x16` do texto é o que faz o spec resolver a grade em 16×16 (a precedência
do prompt ganha do profile). O PNG, a ampliação e os relatórios do Pixel Exact
e do Optimizer saem em `backend/data/preview/`.

## 6. O contrato de gavetas

`tests/contract/test_engine_contract.py` chama `generate()` com um pedido
genérico, que não traz receita. Para a desenhista não falhar em todo caso de
geração, a pasta dela tem um `exemplo_contrato.json`: o conteúdo vira
`engine_options["desenhista-v1"]` no pedido do contrato. Qualquer gaveta que
precise de uma entrada própria pode fazer o mesmo; as que não têm o arquivo
recebem o pedido de sempre.

O caso de seed do contrato é pulado para a desenhista, pela regra que já
existia: ela declara que não suporta seed.
