# Lote 8 — a base por temas e `consultar_base`

> Oitavo lote da sessão de 2026-11-25 ([PLANO_BASE_CONHECIMENTO.md](PLANO_BASE_CONHECIMENTO.md)
> §3, §4 e §6, etapa K2). Proposta seguida sem consulta; decisões e dúvidas
> também no [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/pixel_knowledge/temas.py`; regras em `config/pixel_knowledge/temas/`.

## 1. O que entrou

**Quatro seções do PIXEL_KNOWLEDGE.md viraram cinco temas**, com 32 regras
curtas:

| Tema | Seção | Regras | Verificação das regras |
|---|---|---|---|
| `contorno` | §4 | 8 | 1 por construção, 4 medidas (degraus, dobras, cantos, contorno fragmentado), 1 olhar, 1 autora, 1 por construção do `contorno` |
| `suavizacao` | §7 (AA manual) | 5 | 4 por construção (`suavizar`), 1 autora |
| `pontilhado` | §7 (dithering) | 5 | 2 medidas (`PONTILHADO`), 2 por construção, 1 autora |
| `manchas` | §8 | 7 | 3 medidas (órfãos, redundância), 2 olhar, 2 autora |
| `erros` | §17 (estilo e processo) | 7 | 2 medidas (borda, cores), 1 por construção (`rampas`), 4 olhar |

Cada regra tem `secao`, fonte quando tem número (Pixel Joint, Pixel Parmesan,
Pixnote — as do documento), `verificacao` (lote F5) e **etiquetas**: `tipos`,
`corpos`, `tamanho` (lado maior, `[mín, máx]`), `liberdade` e `materiais`.
Campo vazio vale para todos. A carga recusa número sem fonte, liberdade
desconhecida e tema cujo nome não é o do arquivo.

**O pedido aciona as etiquetas.** Uma poção de 16 px recebe "personagem e
objeto de até 32×32 não pontilham" e "em sprite pequeno, sem suavização"; um
céu de 64 px recebe "pontilhado até 15% da área" e as regras de suavizar por
dentro da silhueta. Em `ousado`, as regras de gosto (`liberdade: [fiel,
equilibrado]`) saem.

**O que chega ao Claude, e quanto custa:**

| Onde | O que vai | Custo |
|---|---|---|
| `consultar_pedido` | depois do recorte, uma linha: `temas (consultar_base, regras que valem): contorno 8 · erros 7 · manchas 7 · pontilhado 2 · suavizacao 1` | ~30 tokens |
| `pedidos_pendentes` | uma linha só, no topo: os temas, sem contagem | ~25 tokens por resposta, não por pedido |
| `consultar_base(tema, pedido?, perfil?, liberdade?)` | as regras do tema, filtradas pelo pedido, cada uma com como é conferida | ~150 a 300 tokens, só quando pedido |

**Na ficha (F5).** As regras de tema que o pedido aciona entram na ficha do
asset, com o resultado de cada verificação. Para isso o validador ganhou três
medidas na ficha: `FRAGMENTADO` (`PX-WARN-OUTLINE-FRAGMENTED`), `REDUNDANCIA`
(`PX-WARN-COLOR-REDUNDANCY`) e `BORDA` (`PX-WARN-BORDER`). Uma verificação
`olhar:*/limpeza` usa a pergunta de mesmo nome da lista da forma do pedido.

## 2. Interruptor

`ASSETFLOW_CONSULTAR_BASE` (`settings.aprendizado.consultar_base`, ligado).
Desligado, a linha dos temas some da consulta e da lista, `consultar_base`
recusa dizendo isso, e as regras de tema saem da ficha.

## 3. Decisões tomadas sem consulta

1. **Um arquivo por tema** em `temas/`, no formato das regras de `luz.yaml` e
   `proporcoes.yaml`, mais as etiquetas: o leitor de regra é o mesmo.
2. **O recorte não leva a linha por padrão** (`montar_recorte(temas=False)`):
   ela vai depois do recorte na consulta avulsa e uma vez no topo da lista.
   Por pedido, numa lista de dez, ela passava o teto da resposta.
3. **Só técnica e processo do §17**: os hard checks (dimensão, alpha, paleta)
   já reprovam pelo validador e não precisam de regra para o Claude.
4. **Material fica gravado, sem uso**: as quatro seções não têm regra de
   material (essas estão no §6, já em `luz.yaml`), e o spec não tem campo de
   material.
5. **A ficha recebe as regras de tema** — a ficha cresce (29 linhas numa
   poção de 16 px, contra 5), mas não custa token: é do app.

## 4. Dúvidas para a autora

1. **Sete regras são `autora`** (gosto: preto puro, borda de mancha variada,
   contraste do pontilhado…). Elas só passam ou não passam pelo seu "gostei";
   vale ver na ficha se fazem sentido como regra ou se saem.
2. **O Claude vai pedir `consultar_base`?** Só a banca dirá: a linha diz quantas
   regras valem, mas ninguém obriga a consulta. Se ele não pedir, uma saída é
   pôr as 2 ou 3 regras de maior peso no recorte, com teto.
3. **O §7 foi dividido em dois temas** (suavização e pontilhado), porque as
   etiquetas de tamanho dos dois são opostas.
