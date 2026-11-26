# Lote F5 — ficha de verificação

> Quarto lote da sessão de 2026-11-25 ([FUNDAMENTOS_E_FERRAMENTAS.md](FUNDAMENTOS_E_FERRAMENTAS.md)
> §7 e §8). Proposta seguida sem consulta; decisões e dúvidas também no
> [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/mcp/ficha.py`, `assetflow/pixel_knowledge/base.py`.

## 1. O que entrou

**A regra de entrada.** Toda regra de `config/pixel_knowledge/` (`luz.yaml`,
`proporcoes.yaml`) declara `verificacao`, no formato `tipo:alvo`:

| Tipo | Alvo | Quem confere | Exemplo |
|---|---|---|---|
| `construcao` | um comando da receita | a receita | `construcao:sombrear` |
| `medida` | um código do olho do app ou do validador | o app | `medida:VALOR` |
| `olhar` | `<forma>/<pergunta>` de `olhar.yaml` | o Claude | `olhar:humanoid/silhueta` |
| `autora` | — | a autora | `autora` |

O carregamento recusa a regra sem o campo ou com tipo desconhecido
(`ConhecimentoInvalido`, em português). `tests/test_ficha.py` confere que o alvo
existe: a medida em `MEDIDAS_CONHECIDAS` (e no `olho.py`), a pergunta na lista
do `olhar.yaml`, o comando entre os da receita.

As dez regras de hoje:

| Regra | Verificação |
|---|---|
| luz do lado de onde ela vem e sombra no oposto | `olhar:humanoid/luz` |
| sombra principal com o vizinho imediato da rampa | `olhar:humanoid/luz` |
| arma e escudo fora do corpo, com vão de 1 px | `olhar:humanoid/silhueta` |
| o equipamento muda o contorno do corpo | `olhar:humanoid/silhueta` |
| uma assimetria intencional | `olhar:humanoid/assimetria` |
| vão entre braço e tronco e entre as pernas | `olhar:humanoid/silhueta` |
| partes vizinhas com valores diferentes | `medida:VALOR` |
| um objeto, uma ideia | `olhar:prop/uma ideia` |
| arma longa na diagonal de 45° | `olhar:prop/limpeza` |
| um valor por face | `olhar:prop/faces` |

**A resposta por pergunta.** `concluir_pedido` ganha `respostas`, opcional:

```
concluir_pedido(pedido_id="…", olhar="…",
                respostas={"silhueta": "sim", "valores": "não: braço some no manto, x 4–6"})
```

"sim" ou "não: <onde>". A linha livre (`olhar`) continua obrigatória e igual.

**A ficha.** Ao concluir, o servidor grava `000_ficha.json` ao lado do PNG: uma
linha por regra da forma do pedido e da luz, com tipo, resultado (`passou`,
`nao_passou`, `sem_resposta`, `nao_se_aplica`), detalhe e quem conferiu; as
respostas; as perguntas sem resposta; e as **divergências**.

**O cruzamento.** Uma pergunta respondida "sim" quando a medida que confere a
mesma coisa acusou o problema vira divergência (`CONFERE` em `ficha.py`):

| Pergunta | Medida |
|---|---|
| `valores` | `VALOR` (contraste entre camadas vizinhas, do olho do app) |
| `limpeza` | `ORFAOS` (aviso de pixel solto do validador) e, desde o lote F1, `CANTOS`, `DOBRAS` e `DEGRAUS` do olho |

> Corrigido no lote F1: as perguntas `limpeza` eram feitas no negativo, e a
> ficha lia o "sim" de um desenho sujo como limpo. Agora toda pergunta é
> feita de modo que "sim" é o desenho certo ([LOTE_F1_LINHA.md](LOTE_F1_LINHA.md) §3).

A resposta do `concluir_pedido` acrescenta uma linha por divergência e uma com
as perguntas sem resposta.

**Na tela.** O resultado pronto mostra a ficha dobrada ("Ficha de verificação —
N de M regras passaram"), com a lista aberta ao clicar; as divergências
aparecem fora da dobra, destacadas. Rota: `GET /api/pedidos/{id}/ficha`, que
relê o "gostei" da autora a cada leitura (a ficha nasce antes dele).

## 2. Interruptor

`ASSETFLOW_FICHA` (`settings.aprendizado.ficha`, padrão ligado). Desligado, o
`concluir_pedido` não monta nem grava a ficha, e a resposta não ganha linhas;
`respostas` continua aceito e só entra na conta do custo. A obrigação do campo
`verificacao` nas regras **não** tem interruptor: é regra de entrada da base, e
desligá-la deixaria entrar regra que ninguém confere.

Custo: as respostas somam ~10 a 30 tokens de saída por pedido; a resposta do
`concluir_pedido` cresce uma linha quando falta resposta ou há divergência.

## 3. Decisões tomadas sem consulta

1. **Formato `tipo:alvo` numa string só**, em vez de um bloco com dois campos:
   cabe na linha de cada regra dos YAML, que já são de uma linha.
2. **Resposta livre, lida pelo começo**: "sim", "ok" e "s" passam; "não", "nao"
   e "n" não passam; o resto conta como sem resposta. Não há esquema rígido
   porque o Claude já escreve em português corrido.
3. **A ficha mora no `mcp/`**, ao lado do laudo, e só lê dicionários (olho,
   validação, receita). A rota da API lê o arquivo gravado e não importa o
   módulo.
4. **Só as regras da forma do pedido e as de luz** entram na ficha; um prop
   não recebe as regras de humanoide.
5. **A ficha aparece no resultado**, não numa "tela de detalhe do asset" (o
   §7 fala de uma, e a tela não tem): é ali que o pedido pronto aparece.
6. **"autora" é relida a cada leitura**, porque o "gostei" chega depois da
   conclusão.

## 4. Dúvidas para a autora

1. **Quase tudo é olhar hoje.** Das dez regras, nove são `olhar` e uma é
   `medida`. O §7 conta 24 medidas e 8 construções nos fundamentos — elas
   entram com as regras novas dos lotes F1, F4 e 8; a ficha já as recebe.
2. **A revisão independente na banca** (§7, "como evitar", item 3) não entrou:
   precisa de uma conversa que não desenhou, e o servidor não a distingue (a
   mesma dúvida do lote 1).
3. **O cruzamento cobre duas perguntas.** As outras (silhueta, assimetria,
   luz, faces, uma ideia) não têm medida que confira a mesma coisa; o lote F1
   (cantos, degraus) pode somar a `limpeza`.
