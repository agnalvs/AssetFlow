# Ajustes de custo por desenho

> Para o plano menor: o que cada interruptor economiza, em tokens por pedido.
> Estimativa pelos tamanhos medidos (cerca de 3 caracteres por token em texto,
> 2,3 no JSON de pixels; imagens pela regra ⌈l/28⌉ × ⌈a/28⌉). O raciocínio do
> Claude não entra na conta.

Um pedido típico (personagem 48×48, `equilibrado`) custa, com tudo ligado:

| Parte | Tokens |
|---|---|
| Etapa de conceito (modo `eu_escolho` ou `claude_escolhe`) | ~900 |
| Bloco do pedido na fila | ~1.100 a 1.600 |
| Receita (saída) | ~1.000 |
| Resposta do `desenhar` (laudo + imagem de 294 tokens) | ~860 |
| Cada remendo do olhar (saída ~350 + resposta ~650) | ~1.000 |
| Olhar, lições e conclusão | ~120 a 600 |
| **Total**, bom de primeira / com 2 remendos | **~4.900 / ~7.600** |

## Os três ajustes prontos em settings

| Ajuste | Variável | Padrão | Economia por pedido |
|---|---|---|---|
| Pular a etapa de conceito | `ASSETFLOW_CONCEITO=sem_conceito` (ou "Sem conceito" no pedido) | `eu_escolho` | ~900 tokens (e uma volta de conversa a menos no `eu_escolho`) |
| Menos remendos do olhar | `ASSETFLOW_PEDIDOS_REMENDOS=1` (ou `0`) | `2` | ~1.000 por remendo não feito: até ~1.000 com 1, ~2.000 com 0 |
| Lista de verificação curta | `ASSETFLOW_OLHAR_LISTA_CURTA=1` | desligado | ~170 (a lista do primeiro olhar vira uma linha com os nomes) |

Somados no pior caso (2 remendos → 0, sem conceito, lista curta): de ~7.600
para ~4.600 tokens por pedido, cerca de 40% a menos. No melhor caso (bom de
primeira), de ~4.900 para ~3.800, cerca de 22%.

Outros que já existiam: `ASSETFLOW_LICOES=0` tira as lições do recorte (~0 a
300 tokens, conforme quantas houver) e `ASSETFLOW_EXEMPLO` já nasce desligado
(o exemplo custaria ~400 a 600). A ficha de verificação (`ASSETFLOW_FICHA`,
lote F5) soma ~10 a 30 tokens de respostas por pedido; desligá-la quase não
economiza e tira o cruzamento com as medidas.

Os **comandos opcionais da receita** (lotes F1 a F4) custam no formato: cor e
luz ~170 tokens, construção ~150, linha ~100, acabamento ~200. Desde o lote
F4 eles vão **uma vez por conversa** (`ASSETFLOW_FORMATO_UMA_VEZ`, ligado);
nas consultas seguintes, uma linha com os nomes — ~600 tokens a menos por
consulta. Desligar um grupo (`comandos_<grupo>: false`) tira o custo dele
também da primeira.

O **editor de pixels** (`ASSETFLOW_EDITOR`, lote 5, ligado) não custa token
nenhum: a correção pequena feita ali poupa um remendo do olhar (~1.000 tokens)
ou um pedido de ajuste inteiro (~3.000 a 5.000).

**O que não reduzir.** A imagem do olhar (294 tokens) é o que permite julgar o
desenho; o laudo do validador é pequeno. Em vez de tirar a imagem, tire os
remendos: o olhar continua, só não corrige.

Depois de mudar qualquer um, reinicie a API e reconecte o servidor MCP
(`/mcp`): os dois leem o ambiente ao subir.
