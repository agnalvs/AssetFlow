# Lote 1 — banca de teste e etapa de conceito

> Primeiro lote da sessão de 2026-11-25 (ordem em
> [FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md) §8 e
> [PLANO_BASE_CONHECIMENTO.md](PLANO_BASE_CONHECIMENTO.md) §7 e §8). Proposta
> aprovada pela autora antes da mudança de ritmo; as decisões tomadas sem
> consulta estão no fim e no [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md).

## 1. O que chega ao recorte nos seis pedidos

Medido com o código do commit `c48c920`, liberdade `equilibrado`, em caracteres
(é a versão enxuta do inventário da K1):

| Pedido | Leitura | Cab. | Lib. | Medidas | Luz | Cores | Silhueta | Molde | Refs | Exemplo | Lições | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Maga do gelo 48, 12 cores | humanoide | 330 | 242 | 584 | 257 | 628 | 454 | 134 | 298 | — | 348 | 3.289 |
| Guerreiro anão 32, 8 cores | humanoide | 332 | 242 | 541 | 257 | 627 | 454 | 134 | 298 | — | 348 | 3.247 |
| Lobo cinzento 32, 8 cores | quadrúpede | 331 | 242 | — | 257 | 627 | — | — | — | — | — | 1.471 |
| Slime verde 16, 4 cores | amorfo | 327 | 242 | — | 257 | 627 | — | — | — | — | — | 1.467 |
| Machado de batalha 32, 8 cores | objeto, arma | 311 | 242 | 147 | 257 | 627 | 160 | 76 | 152 | — | — | 1.986 |
| Baú aberto 32, 10 cores | objeto | 322 | 242 | 147 | 257 | 628 | 160 | 76 | 152 | — | — | 1.998 |

Lobo e slime chegam sem medidas, sem regra de silhueta e sem referências; o anão
recebe as medidas do humanoide padrão; as lições L1–L3 chegam à maga e ao anão;
o exemplo está desligado (`c48c920`).

## 2. A banca

- **Os seis pedidos** ficam em `config/banca.yaml` (versionado), com `id`,
  texto, perfil e o que cada um testa.
- **Uma rodada** (`POST /api/banca/rodadas`, ou "Nova rodada" na tela) cria os
  seis pedidos na fila, no projeto `banca` (`settings.banca.projeto`), com o
  modo de conceito escolhido para a rodada. Ela guarda a **versão da base**:
  a impressão (sha256, 12 hex) de `config/pixel_knowledge/` e dos
  interruptores, o commit (lido do `.git`) e as lições ligadas naquele momento.
- **A fila entrega** os pedidos da banca como os outros, com a etiqueta
  `banca R2 · maga (1 de 6): desenhe do zero, sem olhar desenhos de outras rodadas`.
  A fila da tela mostra os dois projetos; "Prontos" só o seu.
- **Comparar** (`GET /api/banca/comparar?a=&b=`, página "Banca e Comparar"):
  cada par lado a lado; o lado de cada rodada é sorteado por par (hash de
  `a|b|item`, estável) e nunca é dito. A autora escolhe o melhor (ou empate) e
  dá uma nota de 1 a 5 a cada imagem (`PUT /api/banca/votos`). Par com um lado
  sem desenho (falhou ou cancelado) conta como derrota desse lado, nota 1.
- **O resumo** só vem com todos os pares avaliados e revela os lados: vitórias,
  nota média, maior queda, remendos e desvios do olho por desenho, tokens
  estimados por rodada e o veredito pela regra do plano (§7: mantém se a nova
  vence a maioria e nenhum par cai 2 ou mais).
- **Custo por pedido**: o MCP soma em `custo` os caracteres que entram e saem
  em cada ferramenta e as imagens; a banca estima os tokens (÷3 em texto, ÷2,3
  na receita, 294 por imagem). O raciocínio do Claude não entra.

Rodadas e votos num SQLite em `data/banca/` (`assetflow/banca/`), com as regras
de `sqlite_curto`. O pacote não importa API, MCP, gaveta nem jobs.

## 3. A etapa de conceito

Três modos por pedido (`modo_conceito`; padrão da instalação em
`ASSETFLOW_CONCEITO`, `eu_escolho`):

| Modo | O que acontece |
|---|---|
| `eu_escolho` | O Claude propõe três; o pedido fica em "escolha um conceito"; a autora escolhe, edita ou pede outros três; o escolhido vira a direção de arte e o pedido volta à fila |
| `claude_escolhe` | O Claude propõe três, escolhe o mais forte, grava os três e o motivo, e a resposta já traz o recorte para desenhar na mesma rodada; a tela mostra os três e o escolhido |
| `sem_conceito` | O fluxo de antes, para itens simples |

`propor_conceitos(pedido_id, conceitos, escolhido?, motivo?)`. Cada conceito
tem **traço marcante, silhueta, objeto, pose e o que simplificar** (até 120
caracteres; o último, 80). O servidor recusa: número diferente de 3, campo
vazio ou longo, dois conceitos com 50% ou mais das mesmas palavras (traço,
silhueta e objeto), um conceito que repita um recusado, e escolha no modo
errado. "Se serve para qualquer personagem do mesmo tipo, refaça" é instrução,
não conferência: a guarda é a escolha da autora, o "outros três" e a pergunta
do olhar.

**Conceito na medida da grade** (FUNDAMENTOS §2): o bloco da fase de conceito
diz o que cabe — em 16 px, um traço marcante só, de forma grande; em 32, um
traço e um objeto simples; em 48 e 64, o conceito completo.

**Transições** (`em_desenho` com conceito pendente mostra a etapa
`conceituando`; `escolhendo` é situação nova, sem reserva):

```
pendente, precisa de conceito ──reserva──▶ em_desenho  ("o Claude está propondo conceitos")
em_desenho ──propor_conceitos──▶ escolhendo             ("escolha um conceito")      [eu_escolho]
em_desenho ──propor_conceitos(escolhido)──▶ em_desenho, com conceito                  [claude_escolhe]
escolhendo ──a autora escolhe (e edita)──▶ pendente, com conceito
escolhendo ──"outros três"──▶ pendente (os três vão para os recusados)
escolhendo ──cancelar──▶ cancelado
```

`desenhar(pedido_id)` é recusado enquanto o pedido precisa de conceito. **No
olhar**, uma pergunta nova entra quando há conceito, no fim da lista: "o
desenho entrega o traço marcante do conceito escolhido ('…')?"
(`olhar.yaml`, chave `conceito`, §3).

**Custo** (estimado): ~900 tokens por pedido com conceito; cada "outros três",
~600 a mais.

## 4. Decisões tomadas sem consulta

1. **O conceito vira a direção de arte** como texto ("conceito — traço: … ·
   silhueta: …"), com a direção escrita na criação antes dele; o conceito
   também fica estruturado (`conceito`), para a pergunta do olhar usar o traço.
2. **A direção do bloco de desenho diz quem escolheu** ("conceito escolhido
   pela autora" ou "pelo Claude").
3. **Ajuste é sempre sem conceito** (é remendo de um asset que já existe).
4. **Rodada da banca nasce com o modo escolhido na tela**; o padrão da página é
   "sem conceito", para a primeira rodada de referência, como a autora pediu.
5. **Nota por imagem**, não por par: o resumo dá a média de cada rodada.
6. **Os testes de mecanismo do desenho** criam pedidos `sem_conceito`
   explicitamente; os do conceito ficam em `tests/test_conceito.py`.
