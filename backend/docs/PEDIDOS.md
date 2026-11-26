# Fila de pedidos

> Plano do app ([PLANO_APP_DESENHISTA.md](PLANO_APP_DESENHISTA.md)), Fase B.
> Código em `assetflow/pedidos/` (fila e serviço), `api/routers/pedidos.py`
> (rotas) e `mcp/servico.py` (`pedidos_pendentes`, `desenhar(pedido_id)`).
> Testes em `tests/test_pedidos_*.py`.

A tela não cria jobs: ela cria **pedidos**. O Claude, pela conversa, pega os
pedidos com `pedidos_pendentes` e desenha cada um com
`desenhar(pedido_id=...)`. A tela acompanha a fila e mostra o resultado sem
recarregar a página.

Desde o lote 1, um pedido pode ter **etapa de conceito** antes do desenho
(`modo_conceito`: `eu_escolho`, `claude_escolhe`, `sem_conceito`), com a
situação nova `escolhendo`; e a fila guarda pedidos da **banca de teste** no
projeto `banca`. Ver [BANCA_E_CONCEITO.md](BANCA_E_CONCEITO.md).

Desde a Fase B2, **aprovado no validador não é pronto**: o pedido espera o
olhar do Claude (`em_revisao`, etapa `olhando`), pode receber até 2 remendos do
olhar e só conclui com `concluir_pedido`. O olhar, o olho do app, o exemplo e
as lições: [OLHAR.md](OLHAR.md).

## 1. Por que um SQLite

A API (uvicorn) e o servidor MCP (`python -m assetflow.mcp`, que o Claude Code
sobe) são **dois processos**, cada um com a sua fila de jobs em memória. A fila
de pedidos é o que os dois precisam ver, então mora em disco:
`backend/data/pedidos/pedidos.sqlite3` (fora do git, como todo o `data/`;
`ASSETFLOW_PEDIDOS_DB` troca o caminho). O sistema de jobs continua sendo quem
executa o desenho, dentro do processo do MCP.

Regras de acesso, todas por causa dos dois processos (`pedidos/fila.py` e,
desde a Fase B2, `sqlite_curto.py`, que a fila divide com as lições):

- **conexão curta**: cada operação abre, faz e fecha;
- **WAL e `busy_timeout`** (`ASSETFLOW_PEDIDOS_ESPERA_S`, padrão 5 s): leitor não
  espera escritor, e um escritor espera o outro antes de desistir com erro.
  O `-wal` fica entre conexões (`SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE`): sem isso,
  cada fechamento faria checkpoint e apagaria o arquivo — 130 ms por escrita
  no Windows, contra 7 ms. Por isso a fila são três arquivos (`.sqlite3`,
  `-wal`, `-shm`); uma cópia de segurança leva os três. `synchronous=NORMAL`;
- **uma transição, uma instrução**: toda mudança de situação é um `UPDATE`
  condicional (`WHERE situacao = ...`), com o evento anexado e o resultado lido
  pelo `RETURNING` na mesma instrução;
- **o arquivo nunca é apagado nem recriado**: banco ocupado além da espera vira
  `fila_indisponivel`; arquivo danificado vira `fila_corrompida`, com o caminho
  e o que fazer. A API responde 503 com a frase, a tela a mostra crua, e o MCP
  a devolve como erro da ferramenta.

`tests/test_pedidos_processos.py` sobe **dois processos Python de verdade**
sobre o mesmo arquivo: criando 80 pedidos cada um ao mesmo tempo, e
disputando a fila — nenhum pedido sai para os dois, e um pedido disputado é
concluído por um só.

## 2. O registro

| Campo | O que guarda |
|---|---|
| `id` | `ped_` + 12 hexadecimais |
| `tipo` | `desenho` ou `ajuste` |
| `situacao` | `pendente`, `em_desenho`, `em_revisao`, `concluido`, `falhou`, `cancelado` |
| `projeto` | o projeto do app, fixo: `principal` (`ASSETFLOW_PROJETO_PADRAO`) |
| `texto` | a descrição; num ajuste, o que mudar |
| `liberdade` | `fiel`, `equilibrado` (padrão) ou `ousado` (§5) |
| `direcao_de_arte` | texto livre, entregue ao Claude como está |
| `corpo` | o que a tela mandou |
| `leitura` | `resolved` (o spec) e `semantic`, resolvidos **uma vez**, na criação |
| `origem_asset_id` | num ajuste, o asset de origem |
| `asset_id`, `job_id`, `asset_projeto` | o desenho que concluiu o pedido, o que espera o olhar, ou o último não aprovado |
| `candidatos` | os desenhos aprovados no validador, na ordem (Fase B2) |
| `remendos`, `max_remendos`, `remendando` | remendos do olhar, o teto (`ASSETFLOW_PEDIDOS_REMENDOS`, padrão 2) e se um está rodando |
| `olhar` | a linha do olhar que concluiu o pedido |
| `envio` | o que foi entregue ao Claude: interruptores, exemplo, lições |
| `tentativas`, `max_tentativas`, `ultimo_laudo` | desenhos não aprovados, o teto (`ASSETFLOW_PEDIDOS_TENTATIVAS`, padrão 3) e o laudo mais recente |
| `leva`, `reservado_ate` | a reserva: qual `pedidos_pendentes` o pegou, até quando (`ASSETFLOW_PEDIDOS_RESERVA_MIN`, padrão 30) |
| `desenhando_desde` | um `desenhar(pedido_id)` rodando agora |
| `motivo`, `eventos` | por que falhou ou foi cancelado; o andamento |

```
pendente ──reserva──▶ em_desenho ──aprovado no validador──▶ em_revisao
                        ├─ não aprovado (antes do teto) ──▶ em_desenho
                        ├─ não aprovado (no teto) ────────▶ falhou
                        └─ devolvido à fila ──────────────▶ pendente
em_revisao ──concluir_pedido (o olhar)────▶ concluido
em_revisao ──remendo do olhar (até o teto)─▶ em_desenho ─▶ aprovado: em_revisao
                                            └ não aprovado: em_revisao, com o
                                              candidato de antes
em_revisao ──reserva vencida ou devolvido──▶ pendente, com os candidatos
pendente, em_desenho, em_revisao ──cancelar──▶ cancelado
```

Um pendente com candidato, quando reservado, volta direto para `em_revisao`:
falta o olhar, não um desenho novo. As colunas da Fase B2 entram por
`ALTER TABLE` ao abrir um arquivo anterior; os pedidos antigos ficam como
estavam.

A **etapa** é o que a tela mostra, mais fina que a situação: `na_fila`,
`na_vez` (reservado, sem desenho ainda), `desenhando`, `corrigindo` (houve
desenho não aprovado), `olhando` (aprovado no validador, esperando o olhar),
`pronto`, `nao_aprovado`, `cancelado`. Uma reserva vencida aparece como
`na_fila`, e o próximo `pedidos_pendentes` a pega.

## 3. O spec é resolvido uma vez

O pedido de geração de um pedido da tela é montado num lugar só
(`ServicoDePedidos.requisicao`): projeto do app, o **gerador do app** pelo nome
e sem fallback (`gerador:` no `engines.yaml`) e uma variação. A prévia da tela
(`POST /api/pedidos/previa`), a criação e o desenho usam essa montagem.

Na criação, o spec vai para `leitura`. O desenho **não resolve de novo**: o MCP
passa o spec gravado a `GenerationService.submit(..., resolved=spec)`, e o
worker executa exatamente esse objeto. Mudar a taxonomia ou a base de
conhecimento entre criar e desenhar não muda o que foi pedido
(`test_o_desenho_executa_o_spec_gravado_mesmo_com_a_taxonomia_mudada`).
Liberdade e direção de arte **não** entram no spec.

Num **ajuste**, o spec é o do asset de origem, lido do `resolved_spec.json` que
o job dele gravou, e o desenho é um remendo sobre a receita da origem.

## 4. API

| Rota | O que faz |
|---|---|
| `POST /api/pedidos/previa` | a leitura que a criação vai gravar (sem gravar) |
| `POST /api/pedidos` | cria (201). Desenho: `prompt`, `profile`, controles, `liberdade?`, `direcao_de_arte?`. Ajuste: `origem_asset_id`, `texto`. Sem `engine` nem `project_id` (422) |
| `GET /api/pedidos?projeto=&situacao=&limit=` | lista do mais novo, com o asset de cada um |
| `GET /api/pedidos/{id}` | o pedido inteiro: corpo, leitura, eventos, último laudo |
| `POST /api/pedidos/{id}/cancelar` | pendente, em desenho ou em revisão → cancelado; senão 409 |
| `POST /api/pedidos/{id}/devolver` | em desenho ou em revisão → pendente, sem cancelar nem zerar tentativas (os candidatos ficam); senão 409 |

As lições e as opiniões da tela ficam em `/api/aprendizado` ([OLHAR.md](OLHAR.md) §4).

Erros: 400 com a razão (pedido impossível, descrição vazia, mais de uma
variação, ajuste sem asset), 404 `pedido_nao_encontrado`, 409
`pedido_em_outra_situacao` (com `detail.situacao`), 503 `fila_indisponivel` e
`fila_corrompida`. O asset de um pedido sai do `asset.json` do job — sem varrer
o histórico.

## 5. Liberdade criativa

Muda **o recorte** que o Claude recebe, nunca o spec: grade, cores, fundo, o
validador e a recusa da desenhista a mais chaves de cor são os mesmos.

- **fiel** — o recorte de sempre;
- **equilibrado** (padrão) — a mesma base, aberta por uma linha que a põe como
  ponto de partida; o título das proporções e a linha de cores dizem isso;
- **ousado** — a linha `liberdade:` com os limites duros do spec, um convite
  (proporção livre, traço exagerado, pose, quadro inteiro), do quadro só a
  grade e o chão, luz e silhueta como sempre, cores livres com tons vizinhos
  por material e as rampas como sugestão. Sem medidas do corpo, molde nem
  referências.

`consultar_pedido` e `ver_referencia` avulsos aceitam `liberdade` (sem ela,
fiel). Em ousado, `ver_referencia` escolhe a imagem só pelo estilo, sem o
filtro de porte. O texto exato está em `pixel_knowledge/recorte.py` e
`mcp/laudo.py`, e `tests/test_pedidos_mcp.py` o cobra.

## 6. MCP

`pedidos_pendentes(limite=5)` traz até 10 pedidos, dos mais antigos, e os
**reserva**. O formato da receita e as rampas vêm uma vez, no topo; cada pedido
traz a consulta dele sem os dois. Teto de **16.000 caracteres**
(`TETO_PENDENTES`): o pedido que não couber fica na fila, sem reserva.

`desenhar(pedido_id=..., receita=...)` desenha com o spec gravado (sem
`pedido` nem `perfil`), renova a reserva da leva inteira e abre o laudo com o
que aconteceu com o pedido:

| Caso | Primeira linha do laudo |
|---|---|
| aprovado | `pedido X: aprovado no validador com asset_Y; falta o seu olhar (remendos: 0 de 2)` |
| remendo aprovado | `pedido X: remendo aprovado no validador com asset_Y; falta o seu olhar (remendos: 1 de 2)` |
| remendo não aprovado | `pedido X: o remendo asset_Y não foi aprovado; o candidato continua asset_Z (remendos: 1 de 2)` |
| repete o exemplo | `pedido X: não aprovado (tentativa 1 de 3); …` e o motivo "repete o exemplo de construção" |
| não aprovado, antes do teto | `pedido X: não aprovado (tentativa 1 de 3); corrija com desenhar(pedido_id=X, base=asset_Y, receita=<só o que muda>)` |
| não aprovado, no teto | `pedido X: falhou — 3 desenhos sem aprovação; o último fica na tela` |
| cancelado ou devolvido durante o job | `pedido X: foi cancelado na tela durante o desenho; asset_Y ficou avulso, fora do pedido` |
| concluído por outro desenho | `pedido X: já tinha sido concluído com asset_Z; asset_Y ficou avulso` |

Receita inválida não conta tentativa nem remendo: o erro volta ao Claude e o
pedido segue com ele. Pedido cancelado, concluído ou falho é recusado antes de
desenhar, e o que já usou os remendos também ("conclua com concluir_pedido").

`concluir_pedido(pedido_id, olhar, asset_id?)` conclui um pedido em revisão
com o último desenho aprovado, ou com um anterior do mesmo pedido; a linha do
olhar fica no pedido e aparece na tela. O `pedidos_pendentes` traz, antes dos
pedidos, as opiniões novas da autora, e um pedido que voltou à fila com
desenho aprovado vem como "falta o olhar".
