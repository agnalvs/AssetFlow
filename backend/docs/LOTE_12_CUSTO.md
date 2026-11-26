# Lote 12 — painel de custo

> Décimo segundo lote da sessão (pedido da autora em 2026-11-26;
> SUGESTOES_DE_MELHORIA §12). Proposta seguida sem consulta; decisões e
> dúvidas também no [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/pedidos/custo.py`, `assetflow/api/routers/custo.py`,
> `frontend/src/components/PainelDeCusto.tsx`.

## 1. O que entrou

**Cada soma de custo vira um evento datado.** O servidor MCP já somava, por
pedido, o que passava pela conversa (lote 1). Agora cada soma também entra na
tabela `custos` da fila, com a hora — e as consultas **sem pedido** entram
também (`consultar_pedido` avulso, `desenhar` avulso, `ver_asset`,
`ver_referencia`, `consultar_base`), com `pedido_id` vazio.

**O painel**, na página de pedidos, abaixo das lições:

- **hoje**: os tokens estimados e o medidor contra o limite diário;
- **os últimos 7 dias**, em barras (o valor de hoje escrito; os outros ao
  passar o mouse), com **"Ver em tabela"**;
- **os pedidos que mais gastaram** no período, com a situação;
- as consultas sem pedido e como a conta é feita.

**O limite diário** (`ASSETFLOW_LIMITE_DIARIO_TOKENS`, padrão 100.000) **só
avisa**, nada é bloqueado: na tela, uma faixa no topo; no MCP, uma linha no
começo de `pedidos_pendentes` e de `consultar_pedido`, pedindo remendos curtos
e que o Claude pergunte antes de começar pedidos novos. `0` desliga o aviso.

**A estimativa** é a do lote 1, agora num lugar só (`pedidos/custo.py`, que a
banca importa): ~3 caracteres por token em texto, ~2,3 na receita, 294 por
imagem do olhar. O raciocínio do Claude não passa pelo servidor e não entra. O
dia é o **dia local**.

Rota: `GET /api/custo?dias=7`.

## 2. Interruptores

`ASSETFLOW_PAINEL_CUSTO` (ligado): desligado, o painel some e a rota recusa;
os eventos continuam sendo gravados. `ASSETFLOW_LIMITE_DIARIO_TOKENS=0`
desliga só o aviso.

## 3. Decisões tomadas sem consulta

1. **Eventos datados, numa tabela da fila**, em vez de datar o total do
   pedido: um pedido desenhado em dois dias conta nos dois.
2. **Limite padrão de 100.000 tokens por dia** (~20 pedidos com remendos, pela
   conta do [CUSTO.md](CUSTO.md)); é um número meu, para você ajustar.
3. **O aviso não bloqueia**: parar um desenho no meio desperdiçaria o que já
   foi gasto nele.
4. **O aviso no MCP só nas respostas que começam trabalho** (pendentes e
   consulta), não no laudo do `desenhar`.

## 4. Dúvidas para a autora

1. **O custo de antes deste lote não tem data**: os totais por pedido continuam
   no pedido, mas o painel começa vazio — e só se enche quando o servidor MCP
   for reconectado (`/mcp`) e passar a gravar os eventos.
2. **Tokens, não dinheiro**: o preço depende do plano; dá para somar uma
   conversão quando você disser qual vale.
