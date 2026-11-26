# Lote F4 — detalhes e acabamento

> Sétimo lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §4 e §5; [PIXEL_KNOWLEDGE.md](PIXEL_KNOWLEDGE.md) §6, §7 e §9). Proposta
> seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/generation/engines/desenhista/acabamento.py`.

## 1. O que entrou

**Comandos da receita** (grupo `acabamento`, todos `op` de camada):

| Comando | O que faz |
|---|---|
| `{"rosto": [x, y], "cabeca": px, "cor": "k", "expressao"?, "olhar"?, "vista"?, "boca"?, "reflexo"?}` | olhos, sobrancelhas e boca no formato da cabeça (`[x, y]` é o meio da linha dos olhos). Olho 1×1 até 7 px de cabeça (sem boca até 5), 1×2 até 11, 2×2 até 15, 2×3 acima. Expressões do §9: neutro; feliz (olhos fechados em linha, cantos da boca para cima); triste (ponta de dentro da sobrancelha erguida, boca para baixo); bravo (sobrancelhas em V, olhos menores); surpreso (olhos maiores, boca redonda). `olhar` desloca os olhos 1 px; `vista: perfil` desenha um olho só; `reflexo` põe 1 px claro no olho a partir de 2×2 |
| `{"extremidade": [x, y], "tipo": mao\|pe, "forma"?: fechada\|aberta, "lado"?, "tamanho"?: 1–4, "cor": "p", "contorno"?: "k"}` | mão (no meio da palma) ou pé (no calcanhar), num carimbo do tamanho do membro, virado para `lado`; o contorno só vale no tamanho 4 (até 3, todo pixel é borda) |
| `{"suavizar": "m", "traco": "k"}` | o tom `m` no cotovelo de dentro de cada degrau longo da linha `k`: AA interno, cor da paleta (§7). Uma diagonal de 45° não ganha tom; reta não tem degrau |
| `{"pontilhar": [x, y, w, h], "cores": "ab", "padrao"?: xadrez\|25}` | as duas cores em padrão ancorado à grade, só onde já há pintura; avisa acima de 15% do sprite (§7: "é melhor uma cor a mais") |
| `{"textura": veio\|rachadura\|tufos\|escamas, "cor": "a", "sobre"?: "bc", "densidade"?: 1–3}` | o padrão no miolo da camada (a borda fica limpa); o veio é de traços curtos e quebrados (§6, madeira) |
| `{"luz_de_borda": "c", "sobre": "ab"}` | `c` nos pixels de `sobre` cuja beira fica do lado oposto à luz da receita — por dentro do contorno, que não está em `sobre` |

**Recusas que não derrubam o desenho.** `suavizar` abaixo de 32 px de lado,
`pontilhar` abaixo de 48 px ou com menos de 16 pixels pintados na região, e
`textura` sem miolo não fazem nada; o aviso diz por quê, e o resto da receita
vale. `rosto` e `luz_de_borda` em camada com `espelho` são erro (a cópia
duplicaria o rosto ou levaria a luz para o lado errado).

**Medida do olho do app: pontilhado** (`referencias/linha.py`, código
`PONTILHADO`). Conta as manchas de janelas 2×2 em xadrez (`a b / b a`)
vizinhas, de 4 janelas ou mais (uma área 3×3); uma janela solta é olho ou
detalhe. Acusa pontilhado em personagem ou objeto de até 32 px de lado (§7:
"dithering nenhum até 32×32") e, acima disso, área pontilhada acima de 15%.
Calibração (2026-11-26, pacotes ativos): com a janela solta contando, 2.392 de
3.469 personagens profissionais de até 32 px acusariam; com a mancha de 4,
67 (1,9%) e 6 de 257 props (2,3%). O p99 da área nos personagens é 5,8%.

**Ajuste de custo que veio junto: o formato uma vez por conversa.** Com os
quatro grupos opcionais ligados, o formato da receita tem ~2.400 caracteres
(~800 tokens), e ia inteiro em cada `consultar_pedido` e `pedidos_pendentes`.
Agora o formato dos opcionais vai na primeira resposta de cada conversa (o
servidor MCP é um processo por sessão), e nas seguintes só uma linha com os
nomes dos grupos; `consultar_pedido(..., formato=true)` o repete.
Interruptor `ASSETFLOW_FORMATO_UMA_VEZ` (ligado). Economia: ~600 tokens por
consulta depois da primeira.

## 2. Interruptores

`comandos_acabamento` nas opções da gaveta (padrão `true`); desligado, a
receita com algum dos seis comandos é recusada dizendo isso, e o formato não o
cita (~620 caracteres, ~200 tokens). A medida de pontilhado sai do olho com
`pontilhado_ate` e `pontilhado_teto` removidos de `referencias.yaml`.

## 3. Decisões tomadas sem consulta

1. **Tamanhos do rosto por altura de cabeça** (1×1 até 7, 1×2 até 11, 2×2 até
   15, 2×3 acima): convenção minha a partir do §9 ("neutro: olhos 2×2, boca de 1
   a 2 pixels"), `a calibrar`.
2. **`reflexo`, e não `brilho`, no rosto; `traco`, e não `linha`, no
   suavizar**: `brilho` e `linha` já são comandos, e uma op tem uma forma só.
3. **Recusa vira aviso, não erro**, em `suavizar`, `pontilhar` e `textura`: o
   §5 diz "recusa", e derrubar o desenho inteiro por um acabamento seria pior
   que pular o acabamento.
4. **Mínimos**: suavizar a partir de 32 px de lado e pontilhar a partir de
   48 (§7: "até 32×32, nenhum"; pontilhado em personagem animado cintila),
   `a calibrar`.
5. **Pontilhado só sobre o que já está pintado**: o comando não cria
   silhueta, só a textura de uma área.
6. **A mão e o pé são carimbos fixos** por tamanho, e não geometria: em 1 a
   4 px a forma é quase pixel a pixel.
7. **O rosto fica fora do alcance do acabamento automático** só pela ordem: o
   `contorno` da raiz mexe na borda da silhueta, e o rosto fica no miolo (§9:
   "o rosto é a última coisa que o acabamento automático deve tocar").

## 4. Dúvidas para a autora

1. **Os carimbos de mão aberta** (dedos de 1 px separados) são o ponto mais
   fraco: vale olhar na banca se ficam melhores que um bloco simples.
2. **Rosto de perfil** desenha um olho e desloca a boca, sem nariz nem queixo:
   a silhueta do perfil continua sendo da receita.
3. **Contorno seletivo e colorido no pontilhado**: o padrão usa as cores
   dadas e não olha a rampa; misturar duas cores distantes fica áspero (§7:
   "quanto menor o contraste entre as duas cores, menos áspero").
