# Fase B2 — ver, corrigir e aprender

> Fase do [PLANO_APP_DESENHISTA.md](PLANO_APP_DESENHISTA.md), entre a B (fila
> de pedidos) e a C (galeria). Motivo: o desenho era feito às cegas — o Claude
> escrevia a receita e recebia só um laudo em texto, que dava 96 a 100 para
> qualquer coisa, e ninguém no processo julgava a aparência.

Quatro partes: **ver e corrigir** (a imagem volta com o laudo e o pedido só
conclui depois do olhar), **o olho do app** (desvios medidos, sem IA),
**exemplos reais** (um sprite CC0 convertido para receita no recorte) e
**aprendizado acumulado** (lições e opiniões da autora).

## 1. Ver e corrigir

### A imagem do olhar

O `desenhar` devolve, junto do laudo, um PNG com três painéis
(`assetflow/mcp/imagem.py`):

```
[ ampliado até 384 px ]  [ silhueta em preto, metade ]
                         [ tamanho real 2× ] [ 1× ]
```

- ampliação: 8× numa grade de 48, 12× em 32, 24× em 16 (vizinho mais
  próximo, sobre cinza claro);
- a silhueta em preto é o "preview da silhueta" do PIXEL_KNOWLEDGE §3;
- o tamanho real serve à pergunta "o rosto se lê?".

Custo, pela regra da Anthropic (⌈largura ÷ 28⌉ × ⌈altura ÷ 28⌉ tokens): a
imagem tem **588 × 384** em qualquer grade quadrada até 48 e custa **294
tokens**. O `ver_asset` devolve a mesma imagem (antes, 240 × 240, 81 tokens).

### O laudo pede o olhar

Depois do laudo de sempre vêm o **olho do app** (§2), a **lista de
verificação** e o que fazer:

- **primeiro olhar de cada pedido** (o primeiro desenho; num avulso, um desenho
  sem `base`): a lista inteira, de 4 a 6 perguntas de
  `config/pixel_knowledge/olhar.yaml`, escolhidas pela forma (o corpo num
  personagem, o tipo nos demais). Cada pergunta cita a seção do
  PIXEL_KNOWLEDGE.md e, quando há, a regra de outro YAML de onde sai
  (`tests/test_olhar_lista.py` confere as duas citações). Personagem
  humanoide: 676 caracteres; objeto: 487;
- **remendos**: uma linha só, lembrando os nomes da lista;
- a instrução: *diga em uma linha o que está feio ou estranho; se houver algo,
  corrija com UM remendo e registre a lição; se estiver bom, diga que está e
  conclua com `concluir_pedido`* (num avulso: *e pare*).

O que a base ainda não tem para perguntar fica de fora, dito no cabeçalho do
`olhar.yaml`: cuidados por categoria de objeto (a tabela "Por categoria" do
§10, sem `props.yaml`), tile (emenda 3×3, §11) e efeito (§15). Forma sem lista
recebe "a base não tem lista de verificação para <forma>".

### Aprovado no validador não é pronto

Num pedido da fila, o desenho aprovado vira **candidato** e o pedido vai para
`em_revisao` (etapa `olhando`, "aprovado no validador — o Claude está olhando o
desenho"). Só `concluir_pedido(pedido_id, olhar, asset_id?)` o conclui:

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
                                             (volta como "falta o olhar")
```

- **remendos do olhar**: no máximo `settings.pedidos.remendos` por pedido
  (`ASSETFLOW_PEDIDOS_REMENDOS`, padrão 2). "Um por olhar" é da própria forma
  do fluxo: cada remendo devolve uma imagem nova, que é um olhar novo. Remendo
  não é tentativa do validador (as 3 tentativas continuam à parte); remendo
  interrompido (receita inválida) não gasta remendo;
- `concluir_pedido` aceita qualquer desenho aprovado **do próprio pedido**
  (`asset_id`): um remendo que piorou não obriga a ficar com ele;
- a linha do olhar fica no pedido (`olhar`) e aparece na tela, no resultado;
- o servidor não tem como provar que houve olhar nem obrigar a lição: ele
  grava a linha e avisa, no laudo seguinte e no `concluir_pedido`, quando um
  remendo saiu sem lição registrada.

A fila ganhou as colunas `remendos`, `max_remendos`, `remendando`,
`candidatos`, `olhar` e `envio`, acrescentadas por `ALTER TABLE` ao abrir um
arquivo anterior ([PEDIDOS.md](PEDIDOS.md)). A disciplina de conexão curta foi
para `assetflow/sqlite_curto.py`, dividida com as lições.

## 2. O olho do app

`assetflow/referencias/olho.py`. O mesmo medidor que mede os pacotes mede o
desenho novo, e o laudo diz **só os desvios**, com posição quando há:

| Medida | Comparada com | Posição |
| --- | --- | --- |
| preenchimento da caixa | porte (p10–p90) | caixa |
| largura ÷ altura | porte | caixa |
| altura do conteúdo | faixa do porte | caixa |
| número de cores | porte | — |
| tons por grupo de matiz | estilo | grupo de 1 tom |
| contorno (tipo, fração escura) | estilo | pixels de borda mais claros |
| rampas prováveis | estilo | grupo sem rampa |
| contraste entre partes vizinhas | limiar fixo (ΔL* < 8) | camadas e contato |

**O olho só informa.** Nenhum desvio reprova um desenho nem muda a nota — quem
decide é o validador (o técnico) e o olhar do Claude (o feio). A única exceção
é a guarda **"repete o exemplo"** (§3). `tests/test_olhar_mcp.py` cobre as
duas coisas.

O contraste entre partes vizinhas não se compara com as referências: elas não
têm camadas. Por grupo de matiz ele não serve (pele, couro e madeira caem no
mesmo grupo laranja; até nas referências o p10 dá 2,3). Por camada da receita,
sim: a gaveta desenhista grava **de qual camada é cada pixel** em
`engine_output.json` (`engine_metadata.mapa_de_camadas`). Duas camadas que se
tocam — lado a lado, ou através de um contorno de 1 px — com L* mediano a menos
de `contraste_minimo` uma da outra "têm o mesmo valor".

Fica de fora (Fase 5): jaggies, banding, pillow shading, doubles, dither.
"Tons por material" é "tons por grupo de matiz", com a fusão de materiais
acima. Legibilidade do rosto e reconhecimento pela silhueta são do olhar.

Os limiares estão em `config/pixel_knowledge/referencias.yaml`, seção `olho:`
(`p_baixo`, `p_alto`, `contraste_minimo`, `iou_copia`), todos `a_calibrar`.
Sem um deles, a verificação correspondente não roda.

O relatório do olho é gravado em `000_olhar.json`, ao lado do PNG, com o
**envio** (§5) e a guarda: o laudo continua só lendo o que foi gravado.

## 3. Exemplos reais

A regra "nenhum sprite de terceiro vira receita" mudou, com autorização da
autora, para: **sprites CC0 da biblioteca podem ser convertidos para o formato
de receita e mostrados como exemplo de construção. O exemplo nunca é a base de
um asset e não entra em remendo.**

`assetflow/referencias/exemplo.py`:

- **desligado por padrão** (§5); ligado, **um** exemplo por pedido, no fim do recorte, com o cabeçalho de origem
  (pacote, autor, arquivo, licença CC0) e o JSON `{"paleta", "px"}`; chaves de
  cor pela luminância (`a` é a mais escura);
- do **porte** do pedido (tipo, corpo, altura do corpo); sem porte que baste,
  ou em **ousado**, do **estilo** (qualquer altura);
- uma **fonte** por vez, em rotação: cada pacote é uma fonte, e os assets que
  a autora marcou com "gostei" (mesmo tipo, corpo e grade) são mais uma. A
  ordem vem do que foi mostrado (`data/aprendizado/`): a nunca mostrada
  primeiro, depois a mais antiga; na mesma resposta do `pedidos_pendentes`,
  pedidos seguidos recebem fontes diferentes;
- dentro da fonte, **quadro parado** primeiro (`idle` no caminho); pulo,
  ataque, dano, queda por último, só sem alternativa; entre iguais, o mais
  perto das medianas;
- **teto de 1.500 caracteres** (`TETO_EXEMPLO`) e de 62 cores (as chaves de um
  caractere): o quadro que passa é pulado. No porte do humanoide de 28 px, os
  três pacotes dão 870 a 1.371 caracteres;
- só CC0: pacote aceito com atribuição serve de estilo, mas não vira exemplo.

**A guarda.** O exemplo mostrado fica gravado no pedido (`envio`). Um desenho
cuja silhueta coincida com a dele — IoU ≥ `iou_copia` (0,85) no melhor
alinhamento — é **não aprovado** ("repete o exemplo de construção"); num
desenho avulso, o laudo diz que ele não vale. E `base` só aceita um asset do
histórico — um exemplo nunca é um.

Onde a regra está escrita: CLAUDE.md, [REFERENCIAS.md](REFERENCIAS.md),
[MCP.md](MCP.md) §4, as docstrings de `assetflow/referencias/` e o comentário
de `tests/test_architecture_boundaries.py`.

## 4. Aprendizado acumulado

`assetflow/aprendizado/` — um SQLite em `data/aprendizado/aprendizado.sqlite3`
(da instalação, fora do git), dividido pela API e pelo MCP com as regras de
`sqlite_curto`. O pacote não importa API, MCP, gaveta, jobs, pedidos nem
referências (teste de fronteiras).

### A lição

| Campo | Teto | No recorte |
| --- | --- | --- |
| `errou` | 120 | não |
| `porque` | 120 | não |
| `regra` | 140 | sim |
| tipo, corpo, porte | do asset (ou `qualquer` com `geral=true`) | filtro |
| tema | silhueta, proporção, pose, rosto, equipamento (**forma**); valor, luz, cor, contorno, limpeza (**técnica**) | filtro em ousado |
| origem | `claude` (peso 1) ou `autora` (peso 3) | marca "(autora)" |
| contador, ligada | | ordem |

`registrar_licao(asset_id, tema, errou, porque, regra, geral?, mesma_que?,
da_autora?)`. **Lição repetida não duplica**: soma no contador quando
`mesma_que` diz qual, ou quando outra lição da mesma origem, tipo e tema tem a
regra com ao menos 70% das mesmas palavras (Jaccard, sem acento nem palavras
vazias). A resposta diz qual ganhou +1.

### A escolha para um pedido

Ligadas, do tipo e do corpo do pedido (ou `qualquer`); em **ousado**, só as de
técnica. Ordem: contador × peso, depois as do mesmo porte, depois as mais
recentes. No máximo `settings.aprendizado.max_licoes` (5) e 900 caracteres
(`TETO_LICOES`):

```
lições (de desenhos anteriores; as mais repetidas primeiro):
- L3 ×4 (autora): cajado com nós e ponta curva, não um cilindro
- L1 ×2: partes vizinhas em valores diferentes: alterne claro e escuro
```

### A opinião da autora

Na tela, cada asset pronto ganha **"gostei"** e **"não gostei"**, com um campo
de motivo (`PUT /api/aprendizado/opinioes/{asset}`):

- "gostei": nota do asset, e o asset entra na rotação do exemplo;
- "não gostei" **sem** motivo: só nota do asset;
- "não gostei" **com** motivo: **opinião pendente**. O próximo
  `pedidos_pendentes` traz as opiniões novas (com o asset e o texto), e o
  Claude as converte com `registrar_licao(..., da_autora=true)`: origem
  `autora`, peso 3, e o texto original guardado ao lado (`texto_da_autora`).

Na tela, a lista de lições mostra cada uma com o contador, o tema, as
etiquetas e — nas da autora — o texto dela; dá para editar a regra, trocar o
tema, desligar e apagar (`/api/aprendizado/licoes`).

## 5. Interruptores e o que foi enviado

Para medir se o exemplo ajuda ou atrapalha (os três pacotes do porte de 28 px
são mascotes de plataforma):

| Settings | Env | Padrão |
| --- | --- | --- |
| `aprendizado.exemplo` | `ASSETFLOW_EXEMPLO` (`1` liga) | **desligado** (ver abaixo) |
| `aprendizado.licoes` | `ASSETFLOW_LICOES` | ligado |
| `aprendizado.peso_autora` | `ASSETFLOW_LICOES_PESO_AUTORA` | 3 |
| `pedidos.remendos` | `ASSETFLOW_PEDIDOS_REMENDOS` | 2 |

**O exemplo nasce desligado** desde 2026-11-25. No teste da Fase B2 (a maga do
gelo 48×48), o único exemplo do porte de 28 px para um personagem vestido foi o
corpo-base sem roupa do `customizable-character-pack`, e atrapalhou. Ele volta
quando houver pacotes melhores, com a diferença medida (`ASSETFLOW_EXEMPLO=1`
para comparar). A guarda "repete o exemplo" só age quando há exemplo entregue.

O que foi entregue com cada pedido — os interruptores, o exemplo (fonte,
pacote, arquivo, tamanho e pixels) e as lições (id, contador, origem) — fica
gravado no pedido (`envio`) e no asset (`000_olhar.json`). Num desenho avulso,
vale o último `consultar_pedido` do mesmo texto e perfil na mesma sessão do
servidor.

## 6. Custo em tokens

Por pedido (maga 48×48, `equilibrado`), estimado a ~3 caracteres por token em
texto e ~2,3 no JSON de pixels; a imagem é exata:

| | antes | bom de primeira | 1 remendo | 2 remendos |
| --- | --- | --- | --- | --- |
| bloco do pedido | ~1.000 | ~1.800 | ~1.800 | ~1.800 |
| receita (saída) | ~1.000 | ~1.000 | ~1.000 | ~1.000 |
| resposta do `desenhar` | ~130 | ~860 | ~1.500 | ~2.150 |
| remendos (saída) | — | — | ~350 | ~700 |
| olhar, lição e conclusão | — | ~120 | ~370 | ~620 |

A lista de verificação vai só no primeiro olhar (cerca de 225 tokens a menos
por remendo). As duas ferramentas novas somam cerca de 250 tokens às
descrições que toda conversa carrega.
