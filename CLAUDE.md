# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

Código, comentários, docstrings e mensagens de commit estão em **português**.
Mantenha esse padrão — inclusive nas mensagens de erro voltadas ao usuário.

## Comandos

Backend (a partir de `backend/`, com a venv ativa):

```bash
pytest -q                                # suíte completa (1830 passed, 1 skipped)
pytest tests/test_kernel.py -q           # um arquivo
pytest tests/test_kernel.py::test_fallback_when_preferred_engine_fails -q   # um teste
ruff check .                             # lint (sem config própria: defaults do ruff)

# API
.venv\Scripts\python.exe -m uvicorn assetflow.main:app --port 8000 \
    --reload --reload-dir assetflow --reload-dir config

# Servidor MCP (stdio; fica parado esperando o Claude Code — Ctrl+C sai)
.venv\Scripts\python.exe -m assetflow.mcp
```

O servidor MCP precisa do extra `mcp` (`pip install -e ".[mcp]"`); sem ele,
`tests/test_mcp_servidor.py` é pulado e o resto da suíte roda igual. Ele carrega
código e `config/*.yaml` uma vez, quando sobe: depois de mudar qualquer um,
reinicie a sessão do Claude Code (ou reconecte pelo `/mcp`).

`ruff check .` tem **144 achados pré-existentes** (nenhuma config própria, então
valem os defaults, bem mais rígidos que o estilo do projeto). Compare com esse
baseline antes de concluir que uma alteração sua introduziu lint novo — e, se
mexer nele, atualize o número aqui: o baseline só serve enquanto estiver certo.

O `--reload-dir` é obrigatório: sem ele o uvicorn vigia `backend/` inteiro, e
`backend/data/` é onde os PNGs gerados são gravados — cada geração reiniciaria
o servidor no meio do próprio job.

**Alteração em `config/*.yaml` exige reiniciar o backend.** O reload do uvicorn
só casa `*.py`, e `config/` não tem nenhum — então `--reload-dir config` não
cobre o que o nome sugere. `--reload-include "*.yaml"` só funciona com o pacote
`watchfiles`, que o projeto não instala. Um servidor rodando configuração velha
não dá nenhum sinal disso; `GET /api/generation/engines/<id>` mostra o que ele
realmente carregou.

Para **olhar** o que uma gaveta produz (os testes escrevem em tmp):

```bash
python scripts/preview_engine.py --engine mock-image-v1 -n 2
python scripts/preview_engine.py --engine desenhista-v1 \
    --receita assetflow/generation/engines/desenhista/exemplos/pocao_16x16.json \
    --profile pixel_prop_64 --prompt "poção vermelha 16x16"
```

Sempre nomeie a gaveta: o script liga só a gaveta nomeada e gera com ela. A
`desenhista-v1` só gera com `--receita` (um JSON no formato de
[backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md)); com ele, o padrão
passa a ser uma variação. O script monta o sistema no ambiente de testes
(`AppEnvironment.TEST`), o único que registra os mocks — ele é diagnóstico, não
o app.

O benchmark entre motores (`scripts/benchmark_engines.py`) saiu na Fase 0 do
plano desenhista; as métricas de otimização continuam gravadas em todo job.

Referências de estilo (pacotes livres baixados à mão; nada é baixado aqui):

```bash
python -m assetflow.referencias importar <zip|pasta> --pacote <id> --fonte <url> \
    --autor "<nome>" --licenca CC0-1.0 --licenca-url <url> --parte "PADRAO:TIPO[:CORPO][:QUADRO]"
python -m assetflow.referencias listar      # o que está ativo e os avisos
python -m assetflow.referencias calibrar    # propõe ajustes; não altera YAML
```

Pacotes em `backend/data/referencias/` (fora do git); quais valem, em
`config/pixel_knowledge/referencias.yaml`. Ver
[backend/docs/REFERENCIAS.md](backend/docs/REFERENCIAS.md).

Frontend (a partir de `frontend/`):

```bash
npm ci          # não `npm install` — reproduz o package-lock
npm run dev     # :5173, com proxy de /api para :8000
npm run build   # tsc -b && vite build
npm run typecheck
```

Instalação completa: veja [SETUP.md](SETUP.md). Não há modelo para baixar nem
GPU para configurar — `pip install -e ".[dev,mcp]"` basta. O registro do
servidor MCP no Claude Code está no SETUP.md §10.

## Plano em andamento

O projeto está executando o plano
[backend/docs/PLANO_DESENHISTA_MCP.md](backend/docs/PLANO_DESENHISTA_MCP.md),
uma fase por vez, um commit por fase, no branch `desenhista-mcp`. O motor passa
a ser o Claude, por um servidor MCP: a gaveta `desenhista-v1` recebe uma
receita curta e a transforma em sprite na grade lógica. A base de práticas que
vira `config/pixel_knowledge/` está em
[backend/docs/PIXEL_KNOWLEDGE.md](backend/docs/PIXEL_KNOWLEDGE.md). Leia os dois
antes de mexer numa fase.

Feito:

- **Fase 0** (limpeza) — saíram as gavetas de difusão (`diffusers-sdxl-v1`,
  `flux-pixel-v1`), as pontes externas (`sdpixl-v1`, `pixel-forge-v1`), a de
  API paga (`gpt-image-v1`), o benchmark entre motores e o extra `diffusers`
  do `pyproject.toml`. O modo Studio (2D Normal) ficou, dormente, até a Fase A
  do plano do app, que o tirou.
- **Fase 1** (gaveta desenhista) — `engines/desenhista/`, id `desenhista-v1`,
  família `agentic`. Recebe a receita em
  `engine_options["desenhista-v1"]["receita"]` e entrega a grade lógica 1:1.
  Formato, espelho por camada, erros e avisos:
  [backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md). O rasterizador
  mora **dentro** da gaveta: o teste de fronteiras proíbe gaveta importar
  `assetflow.pixel`, então o `PixelCanvas` não é reusado. `balde` em camada
  com `espelho` é erro (o balde enxergaria o desenho antes da cópia).
- **Fase 2** (servidor MCP) — `assetflow/mcp/`, ao lado da API: outra porta de
  entrada para o mesmo `GenerationService`, pelo mesmo `bootstrap`, sem HTTP.
  Ferramentas `consultar_pedido`, `desenhar` e `ver_asset`; laudo em texto;
  remendo com `base: <id>`. Detalhes: [backend/docs/MCP.md](backend/docs/MCP.md).
  Três regras ao mexer ali:
  - **o MCP pede `desenhista-v1` pelo nome, com `allow_fallback=False`** — um
    desenho que falha não vira saída de mock;
  - **o laudo só lê** o spec e os relatórios gravados (`validation.json`,
    `optimizer.json`, `engine_output.json`) e só dá posição de problema que o
    validador expõe — o contorno fragmentado não tem;
  - **`servico.py` não importa o SDK**; só `servidor.py` importa. É o que deixa
    o pacote importável e testável sem o extra `mcp`. E `servidor.py` não usa
    `from __future__ import annotations`: o SDK avalia as anotações das
    ferramentas, e a descrição de `perfil` é variável local.
- **Fase 3** (base de conhecimento mínima) — `config/pixel_knowledge/`
  (`paletas.yaml`, `luz.yaml`, `proporcoes.yaml`, `silhuetas/`), lida no boot
  por `assetflow/pixel_knowledge/` e entregue no fim de `consultar_pedido`
  como um **recorte** de poucas linhas. Formato e regras:
  [backend/docs/MCP.md](backend/docs/MCP.md) §4 e os cabeçalhos dos YAML.
  Quatro regras ao mexer ali:
  - **o seletor só lê o spec** (`recorte.py` lista os cinco campos); um teste
    lhe entrega um objeto com só esses campos;
  - **paleta-mestra e luz padrão vêm da configuração**, por um ponto único,
    `BaseDeConhecimento.estilo()` — a porta para uma fase futura de estilos.
    Nenhuma paleta ou direção de luz fica escrita no código;
  - **cor de paleta pública vem do Lospec** (`<id>.json`), nunca de memória;
    número sem fonte leva `a_calibrar: true`, e a carga recusa o que faltar;
  - **molde com no máximo 8 chaves de paleta**: a desenhista conta cor por
    chave, não por hexadecimal. O recorte tem teto (`TETO_CARACTERES`).
  - **o recorte padrão traz medidas, não o molde**: faixas de y, chão,
    larguras e nomes de camadas. A receita do molde só vem com
    `consultar_pedido(..., molde=true)` — entregue sempre, ela engessava o
    desenho no corpo do manequim.
  - **corpo e quadro são separados**: a grade do spec é o quadro, e
    `proporcoes.yaml` diz qual corpo vive nele — do mesmo tamanho
    (`tamanhos`) ou menor (`quadros`, como corpo de 32 em 48×48, centrado e
    com o chão do quadro). O profile `pixel_character_48` pede esse quadro.

Adiantado antes da Fase 4: a **biblioteca de referências**
(`assetflow/referencias/`), que importa e mede pacotes de pixel art livres e
entrega ao Claude uma linha `referências:` no recorte e a ferramenta
`ver_referencia`. Detalhes: [backend/docs/REFERENCIAS.md](backend/docs/REFERENCIAS.md).
Cinco regras ao mexer ali:
  - **só CC0 entra direto**; outra licença exige `aceitar_atribuicao: true`
    na lista de ativos;
  - **referência mede estilo; só CC0 vira exemplo**: o recorte traz números
    somados, com **peso igual por pacote**, e `ver_referencia` só imagem.
    Desde a Fase B2, um sprite **CC0** pode ser convertido para receita e
    mostrado como **exemplo de construção** — nunca base de um asset nem
    remendo; o desenho que repete a silhueta dele é não aprovado;
  - **peso igual exige amostra**: pacote com menos de `minimo_por_pacote`
    quadros numa parte (estilo ou porte) sai dela, e a parte com menos de
    `minimo_de_pacotes` some da linha e do `ver_referencia` (que cai para o
    estilo). O `calibrar` a mostra marcada como insuficiente;
  - **porte compara pelo corpo, não pelo quadro**: a altura do corpo vem de
    `proporcoes.yaml`; chão, margem e ocupação não se comparam entre pacotes;
  - **o módulo não importa gaveta, kernel, pipeline, job, API, storage nem
    MCP**, e `pixel_knowledge` não o importa (o recorte recebe a linha por
    parâmetro). Testes só com imagens geradas no próprio teste.

### Plano do app

Depois do plano desenhista, o projeto segue
[backend/docs/PLANO_APP_DESENHISTA.md](backend/docs/PLANO_APP_DESENHISTA.md): a
desenhista vira o gerador único do app, e a tela passa a montar pedidos, mostrar
a galeria, pedir ajustes e exportar. Mesmas regras — uma fase por vez, um commit
por fase, no branch `desenhista-mcp`. O estado do branch está em
[backend/docs/RELATORIO_ESTADO.md](backend/docs/RELATORIO_ESTADO.md).

Feito:

- **Fase A** (simplificação) — saíram o seletor e o crédito de motor da tela,
  o modo 2D Normal (tela, pipeline, pós-processamento, profiles e prompt
  builders Studio), o profile e o pipeline `raw_image`, o modo "Automático"
  (`kernel/auto_policy.py`, `config/engine_policy.yaml`,
  `spec/engine_advisor.py`) e o fallback para mock. "Gerar" fica desligado,
  com a frase dizendo que os pedidos vão para uma fila na Fase B. Três regras:
  - **mock só nos testes, em três travas**: as gavetas de referência só são
    registradas em `AppEnvironment.TEST` (o `conftest` o liga por código;
    `ASSETFLOW_APP_ENV=test` é recusado); as rotas Pixel do
    `capabilities.yaml` listam só a desenhista, com
    `allow_unlisted_engines: false`; e o fallback está desligado. O
    `tests/test_gerador_unico.py` monta o app como ele roda e cobra as três;
  - **o `auto` do kernel continua**: é o roteamento por capacidade que o
    pipeline usa, e no app ele só chega à desenhista. O campo `engine` da API,
    `AssetMode.STUDIO` e `generation/prompting/` ficam: o pipeline Pixel monta
    o prompt semântico em todo job, inclusive os do MCP;
  - **o histórico lê registros antigos**: `GenerationRecord.do_historico`
    ignora campos de topo que saíram do modelo (os da era do STRATEGY, que
    faziam 18 linhas sumirem em silêncio). Gravar continua estrito.
- **Fase B** (fila de pedidos) — "Gerar" cria um **pedido**
  (`assetflow/pedidos/`, `/api/pedidos`); o Claude os pega com
  `pedidos_pendentes` e desenha com `desenhar(pedido_id=...)`; a tela consulta
  a lista e mostra o resultado sem recarregar. Pedido tem **liberdade**
  (`fiel`, `equilibrado`, `ousado`) e **direção de arte**, que mudam o recorte
  e nunca o spec. Detalhes: [backend/docs/PEDIDOS.md](backend/docs/PEDIDOS.md).
  Cinco regras:
  - **a fila é um SQLite em `data/pedidos/`**, porque API e MCP são dois
    processos: conexão curta por operação, WAL com o `-wal` mantido entre
    conexões, `busy_timeout`, e **toda transição é um `UPDATE` condicional
    só**, com `RETURNING`. O arquivo nunca é apagado: travado ou danificado
    vira erro em português (503 na API, erro da ferramenta no MCP);
  - **o spec é resolvido uma vez, na criação**, e o desenho o executa
    (`GenerationService.submit(..., resolved=spec)`). Prévia, criação e
    desenho montam o pedido no mesmo lugar (`ServicoDePedidos.requisicao`): o
    projeto do app (`principal`, em settings), o gerador do `engines.yaml`
    (`gerador:`) pelo nome e sem fallback, uma variação;
  - **aprovado conclui; não aprovado conta tentativa** (3, `settings`), e o
    teto leva a `falhou`. Receita inválida não conta. Concluir é condicional:
    cancelado, devolvido ou concluído por outro desenho deixa o asset avulso;
  - **reserva**: `pedidos_pendentes` reserva o que entrega (30 min, renovados
    a cada `desenhar` da leva); a tela pode devolver à fila sem cancelar;
  - **`pedidos/` não importa API, MCP, gaveta nem jobs** (teste de
    fronteiras), e nenhuma gaveta o importa.
- **Fase B2** (ver, corrigir e aprender) — o `desenhar` devolve a **imagem do
  olhar** (ampliada, silhueta, tamanho real; 294 tokens) e o **olho do app**
  (`referencias/olho.py`: desvios contra as referências do mesmo porte e
  contraste entre camadas da receita, cujo mapa a gaveta grava); o laudo pede
  o olhar, com a lista de `config/pixel_knowledge/olhar.yaml` no primeiro olhar
  de cada pedido. O recorte traz **um exemplo de construção** CC0
  (`referencias/exemplo.py`) e **as lições** (`assetflow/aprendizado/`,
  SQLite em `data/aprendizado/`). Ferramentas novas: `concluir_pedido` e
  `registrar_licao`. Na tela: "gostei"/"não gostei" e a lista de lições.
  Detalhes: [backend/docs/OLHAR.md](backend/docs/OLHAR.md). Cinco regras:
  - **aprovado no validador não é pronto**: o pedido vai para `em_revisao`
    (etapa `olhando`) e só `concluir_pedido` o conclui; até
    `settings.pedidos.remendos` (2) remendos do olhar, que não são tentativas
    do validador. Revisão devolvida ou vencida volta como "falta o olhar";
  - **o olho do app só informa**: nenhum desvio reprova nem muda a nota. A
    única exceção é a guarda "repete o exemplo" (IoU da silhueta com o
    exemplo mostrado ≥ `olho.iou_copia`). Limiares em `referencias.yaml`,
    seção `olho:`, todos `a_calibrar`;
  - **nenhuma pergunta da lista é inventada**: cada uma cita a seção do
    PIXEL_KNOWLEDGE.md e a regra de origem; `tests/test_olhar_lista.py`
    confere. O que a base não tem fica de fora, dito no cabeçalho do YAML;
  - **exemplo e lições têm interruptor e ficam gravados**: `ASSETFLOW_EXEMPLO`
    (**desligado por padrão**: o único exemplo do porte para personagem vestido
    era um corpo-base sem roupa; volta com pacotes melhores, medido) e
    `ASSETFLOW_LICOES` (ligado); o que foi entregue vai para o pedido (`envio`) e para
    o asset (`000_olhar.json`). O exemplo: porte (estilo em ousado), rotação
    entre pacotes, quadro parado primeiro, teto 1.500; as lições: ligadas, do
    tipo e corpo, contador × peso (autora 3), 5 e 900 caracteres, só técnica
    em ousado;
  - **`aprendizado/` não importa API, MCP, gaveta, jobs, pedidos nem
    referências**, e nenhuma gaveta o importa. A opinião "não gostei" com
    motivo fica pendente até o Claude convertê-la (`da_autora=true`), com o
    texto original ao lado; sem motivo, é só nota.

### Sessão de lotes (2026-11-25)

A autora pediu, só nesta sessão, para seguir sem esperar "sim" entre lotes: a
proposta de cada lote vai para um arquivo em `backend/docs/`, as decisões e
dúvidas para o [RELATORIO_ESTADO.md](backend/docs/RELATORIO_ESTADO.md), um
commit por lote. A ordem está em
[FUNDAMENTOS_E_FERRAMENTAS.md](backend/docs/FUNDAMENTOS_E_FERRAMENTAS.md) §8 e
no [PLANO_BASE_CONHECIMENTO.md](backend/docs/PLANO_BASE_CONHECIMENTO.md). Toda
ferramenta nova é opcional e nasce com interruptor; os ajustes que baixam o
custo por desenho estão em [CUSTO.md](backend/docs/CUSTO.md).

A ordem: banca e conceito, F2 (cor e luz), F3 (construção), F5 (ficha),
editor de pixels, F1 (linha e contorno), F4 (detalhes e acabamento), a base
por etiquetas (§4, 7, 8 e 17 do PIXEL_KNOWLEDGE.md, com `consultar_base`), e,
pedidos depois, no mesmo ritmo: 9. cópia de segurança de `backend/data/`
(botão e `python -m assetflow.backup`, com restaurar); 10. `iniciar.bat` (API
e tela, espera as duas, abre o navegador na porta certa); 11. aviso de
servidor desatualizado (API e MCP gravam o commit em que subiram); 12. painel
de custo (por pedido e por dia, limite diário com aviso); 13. estudo dos 30
melhores sprites CC0 (análises em `backend/data/`, técnicas gerais em
`backend/docs/ESTUDO_SPRITES.md`, "bons exemplos" na biblioteca, regras novas
propostas sem ativar).

- **Lote 1** (banca e conceito) — `assetflow/banca/` (rodadas ligadas a uma
  versão da base, comparação cega, votos), `config/banca.yaml`, `/api/banca`,
  página "Banca e Comparar"; etapa de conceito com três modos por pedido
  (`eu_escolho`, `claude_escolhe`, `sem_conceito`), ferramenta
  `propor_conceitos`, situação `escolhendo`, pergunta do conceito no olhar.
  Detalhes: [backend/docs/BANCA_E_CONCEITO.md](backend/docs/BANCA_E_CONCEITO.md).
  Três regras:
  - **pedido que precisa de conceito não desenha**: `iniciar` recusa enquanto
    `modo_conceito != sem_conceito` e não há conceito escolhido. Os testes de
    mecanismo criam pedidos `sem_conceito` explicitamente;
  - **o lado de cada rodada nunca aparece no par**: só o resumo, com todos os
    pares avaliados, revela os lados (hash estável de `a|b|item`);
  - **`banca/` não importa API, MCP, gaveta nem jobs** (teste de fronteiras).
- **Lote F2** (cor e luz) — comandos opcionais da receita em
  `engines/desenhista/cor_e_luz.py`: `rampas`, `luz`, `material`, `sombrear`,
  `brilho`, `oclusao`, `sombra_projetada`. Interruptor
  `comandos_cor_e_luz` nas opções da gaveta; o MCP só cita os grupos ligados
  (`formato_da_receita`). Efeito em camada com espelho é recusado. Detalhes:
  [backend/docs/LOTE_F2_COR_E_LUZ.md](backend/docs/LOTE_F2_COR_E_LUZ.md).
- **Lote F3** (construção) — `engines/desenhista/construcao.py`: `capsula`
  (membro com cotovelo, contorno e vão), `copiar` (com espelho) e o `boneco`
  na raiz (cabeças, forma dominante, linha de ação, pose), que vira camadas
  `boneco_*` antes das da receita. Interruptor `comandos_construcao`.
  Detalhes: [backend/docs/LOTE_F3_CONSTRUCAO.md](backend/docs/LOTE_F3_CONSTRUCAO.md).
- **Lote F5** (ficha de verificação) — toda regra de `config/pixel_knowledge/`
  declara `verificacao: "tipo:alvo"` (`construcao`, `medida`, `olhar`,
  `autora`); a carga recusa regra sem ela, e `tests/test_ficha.py` confere que
  o alvo existe. `concluir_pedido` aceita `respostas` (uma por pergunta do
  olhar), e o servidor grava `000_ficha.json` (`mcp/ficha.py`) com uma linha
  por regra e as **divergências** — "sim" do Claude contra a medida do app.
  Interruptor `ASSETFLOW_FICHA`; a obrigação do campo não tem. Detalhes:
  [backend/docs/LOTE_F5_FICHA.md](backend/docs/LOTE_F5_FICHA.md).
- **Lote 5** (editor de pixels) — `assetflow/editor/` e `EditorDePixels.tsx`:
  a autora troca pixels de um pedido pronto com as cores da receita, e a troca
  vira a camada `retoque_N` no fim da receita da base, desenhada pelo caminho
  de sempre (Optimizer e validador incluídos), sem o Claude. Aprovado, vira um
  pedido de ajuste já concluído (`FilaDePedidos.registrar_edicao`); "o que
  estava errado" vira um "não gostei" pendente no asset original. A gaveta
  grava a paleta efetiva em `engine_metadata.paleta`. Interruptor
  `ASSETFLOW_EDITOR`; `editor/` não importa API, MCP, gaveta nem jobs. Detalhes:
  [backend/docs/LOTE_5_EDITOR.md](backend/docs/LOTE_5_EDITOR.md).
- **Lote F1** (linha e contorno) — `engines/desenhista/linha.py`: `reta`
  (degraus iguais; o fim ajusta), `curva` (passa pelos pontos, sem canto em
  L), `limpar_linha` (dobras, depois cantos, e relata) e `contorno` na raiz
  (inteiro, seletivo, colorido; camada `contorno_auto`, por último).
  Interruptor `comandos_linha`. O olho do app mede cantos em L, dobras e
  degraus no contorno escuro (`referencias/linha.py`), contra limites por
  tipo calibrados nos pacotes (`scripts/calibrar_linha.py`, p90). As
  perguntas do `olhar.yaml` são feitas de modo que "sim" é o desenho certo:
  a ficha lê "sim" como passou. Detalhes:
  [backend/docs/LOTE_F1_LINHA.md](backend/docs/LOTE_F1_LINHA.md).
- **Lote F4** (detalhes e acabamento) — `engines/desenhista/acabamento.py`:
  `rosto` (tamanho pela cabeça, expressões do §9, olhar, perfil), `extremidade`
  (mão aberta ou fechada, pé, por tamanho e lado), `suavizar` (AA interno nos
  degraus longos), `pontilhar`, `textura` e `luz_de_borda`. Interruptor
  `comandos_acabamento`. Recusa de `suavizar`/`pontilhar` em sprite pequeno é
  aviso, não erro. O olho mede pontilhado por **manchas** de xadrez (a janela
  solta é olho; contada, acusaria 2/3 dos pacotes). O formato dos comandos
  opcionais vai **uma vez por conversa** (`ASSETFLOW_FORMATO_UMA_VEZ`;
  `consultar_pedido(..., formato=true)` repete). Detalhes:
  [backend/docs/LOTE_F4_ACABAMENTO.md](backend/docs/LOTE_F4_ACABAMENTO.md).
- **Lote 8** (base por temas) — os §4, 7, 8 e 17 do PIXEL_KNOWLEDGE.md viraram
  `config/pixel_knowledge/temas/*.yaml` (contorno, suavizacao, pontilhado,
  manchas, erros; 32 regras), cada regra com seção, fonte, `verificacao` e
  **etiquetas** (tipos, corpos, tamanho, liberdade, materiais). O pedido
  aciona as etiquetas (`pixel_knowledge/temas.py`). A consulta leva uma linha
  com os temas e quantas regras valem; a lista de pendentes, uma linha só no
  topo; a ferramenta nova `consultar_base(tema, pedido?)` traz o texto. As
  regras de tema que valem entram na ficha. Interruptor
  `ASSETFLOW_CONSULTAR_BASE`. Detalhes:
  [backend/docs/LOTE_8_BASE.md](backend/docs/LOTE_8_BASE.md).

## Arquitetura

O README.md (986 linhas) é a **especificação do produto**, e o código inteiro
referencia suas seções como `plano §N` em docstrings. Ao mexer em algo marcado
assim, leia a seção citada antes.

### A regra que organiza tudo

O AssetFlow é uma plataforma de geração de assets que **não pode estar acoplada
a nenhuma tecnologia de IA específica**. Toda a estrutura existe para isso:

```
Engine   (gaveta)  sabe -> gerar imagem     conhece SDXL, torch, diffusers
Pipeline           sabe -> gerar asset      conhece Pixel Art, personagem, paleta
```

Quatro conceitos que **nunca** se misturam:

```
ENGINE         qual tecnologia/modelo gera uma imagem
POSTPROCESSOR  normaliza/corrige propriedades técnicas do arquivo
OPTIMIZER      revisa o sprite na grade final e corrige pixel a pixel
VALIDATOR      mede e aprova/reprova
```

Os quatro acontecem **sempre**, nesta ordem, e só o primeiro é escolhível. Já
existiu aqui um quinto — `STRATEGY`, "como o asset será criado" —, e ele
descrevia uma bifurcação que não existe: o motor produz a imagem e o Optimizer
corrige a imagem produzida. Ver
[backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md) §1.

Um pipeline **nunca** importa uma gaveta. Ele pede uma **capacidade**
(`text_to_image.pixel`) ao Kernel, que resolve qual motor atende.

### Fluxo de um pedido

```
API (/api/generation/jobs)
  -> GenerationService.submit       resolve o FinalResolvedSpec  <- uma única vez
  -> JobManager + JobQueue          jobs/
  -> GenerationWorker               jobs/worker.py     <- teto job_timeout_s
  -> Pipeline (pixel.character)     generation/pipelines/
       lê o FinalResolvedSpec       generation/spec/  (nunca o reinterpreta)
  -> GenerationKernel               generation/kernel/service.py
       EngineResolver               capability -> cadeia (no app: só a desenhista)
       fallback                     desligado no app; os testes de mecanismo o ligam
  -> Engine.generate()              generation/engines/<id>/
  -> Postprocessing                 generation/postprocessing/
       PixelPostProcessor           grade lógica, paleta, alpha binário
       PixelValidator      V1       mede
       AssetFlowPixelOptimizer      revisa e corrige pixel a pixel  <- SEMPRE
       PixelValidator      V2       mede de novo
       PixelAcceptancePolicy        decide, sobre a V2
  -> AssetStorageService            storage/
```

Peças-chave:

- **`bootstrap.py`** — composition root, o único módulo que conhece todas as
  peças ao mesmo tempo. Não importa gaveta concreta: elas entram por descoberta
  de `manifest.json`.
- **`generation/kernel/discovery.py`** — acha gavetas pelo manifesto, não por
  `import` escrito à mão. É o que permite somar/remover motores sem tocar em
  código.
- **`generation/kernel/resolver.py`** — capability → `[preferido, fallback, …]`.
- **`generation/kernel/catalog.py`** — a vitrine: manifesto + estado viram a
  lista de `GET /api/generation/engines/catalog`, hoje só para diagnóstico.
- **`settings.py`** — precedência **env (`ASSETFLOW_*`) > YAML > padrão**.
  Nada de motor/modelo/device/precisão fica hardcoded.

### Do texto ao contrato (`backend/assetflow/generation/spec/`)

Entre a frase que a pessoa escreve e o motor existe **um** objeto, resolvido
uma vez e imutável durante o job: o `FinalResolvedSpec`.

```
Texto do usuário
  -> ExplicitConstraintExtractor   "32x32", "8 cores", "sem fundo"
  -> AssetTypeClassifier           config/asset_taxonomy/*.yaml
  -> ConstraintResolver            precedência oficial
  -> FinalResolvedSpec             contrato do job
```

A precedência é a regra inteira, e ela está escrita uma vez, em
`SPEC_PRECEDENCE` (`schemas/resolved_spec.py`), da menor para a maior:

```
padrão global < profile < inferência < interface < prompt < correção manual
```

**Ninguém recalcula um campo que já existe no spec.** Pipeline,
pós-processamento, validação e interface leem; nenhum deles reinterpreta o
prompt nem volta a consultar o profile por resolução lógica, paleta, fundo ou
tipo de asset. Foi a ausência dessa regra que produzia os dois defeitos que o
módulo existe para fechar: `tree` virando `character` (o tipo vinha do profile,
não do sujeito) e 32×32 virando 64×64 (cada camada perguntava ao profile em um
momento diferente).

Três consequências práticas ao mexer aqui:

- **O spec é resolvido no `GenerationService.submit`** e viaja dentro do `Job`.
  O worker não resolve nada: ele repassa `job.resolved_spec`. Resolver de novo
  no worker reabriria a porta que o plano fechou.
- **Nada é corrigido em silêncio.** Pedido impossível vira
  `InvalidGenerationRequest` com a razão em português — e essa mensagem é a
  única do backend que a interface exibe crua, porque é escrita para ser lida.
- **A taxonomia é configuração.** Acrescentar "candelabro" ao vocabulário de
  props é editar `config/asset_taxonomy/prop.yaml`, nunca um `.py`. Nos arquivos,
  `markers` (termos que nomeiam o tipo — "tileset", "fundo") ganham de
  `keywords` (termos que nomeiam o sujeito — "grass", "espada"): é o que faz
  "grass tileset" ser um tileset.

Três eixos que **nunca** se colapsam, e o terceiro é novo (pesquisa PixelLab):

```
asset.type            que papel cumpre no jogo   ->  character
asset.category        que tipo de coisa é        ->  creature
character.body_type   que forma o corpo tem      ->  quadruped
```

Um goblin é `creature` de corpo humanoide; um lobo, `creature` quadrúpede. Sem
o terceiro, o motor desenha o lobo em pé — o mesmo erro que fazia uma árvore
virar `character`, um nível abaixo. O vocabulário está em
`config/asset_taxonomy/character.yaml`, seção `body_types`.

Duas regras ao mexer nesse vocabulário:

- **o classificador não flexiona**: forma que não está escrita não casa. O
  arquivo traz uma linha por palavra, com masculino, feminino e plurais, e
  `tests/test_taxonomia_flexoes.py` falha se faltar uma delas ou se entrar
  masculino em -o/-ão sem decisão de feminino. "anã" fica de fora de
  propósito: sem acento vira "ana", o nome;
- **o corpo que a categoria implica** (`category_body_types`, hoje só
  `humanoid -> humanoid`) é deduzido no resolvedor do spec, quando nenhuma
  camada disse a forma, com origem `category_inference` ("inferido da
  categoria"), logo abaixo de `inference`. Categoria mista, como `creature`,
  não entra na tabela. Corpo que continua `unknown` aparece no recorte do MCP
  como `corpo não identificado: …`, e não como silêncio.

E cada campo declara **o que o AssetFlow promete sobre ele** (`SPEC_CONSTRAINTS`,
ao lado de `SPEC_PRECEDENCE`): `hard` é garantido e reprova; `semantic` é medido;
`style` é orientação que o Optimizer melhora; `engine_hint` não tem promessa
visual. A precedência diz de onde veio o valor; a classe diz o que acontece se o
resultado não bater com ele. Sem as duas, a tela mostra "32×32" e "contorno
seletivo" com o mesmo peso.

Os testes permanentes dos dois bugs estão em `tests/test_resolved_spec.py`.
Detalhes em [backend/docs/RESOLVED_SPEC.md](backend/docs/RESOLVED_SPEC.md) — é
o documento que as docstrings citam como `plano T→J §N`.

### Seleção de motor

Desde a Fase A do plano do app, o app tem **um** gerador, a `desenhista-v1`, e
a tela não pergunta nada de tecnologia. A seleção de motor continua existindo
como mecanismo do kernel — é por ela que o MCP pede a desenhista pelo nome —, e
três regras de governança seguem valendo:

1. **motor escolhido é motor usado.** Não podendo atender, o job falha dizendo
   por quê; nunca vira outro em silêncio;
2. **fallback só em `auto`**, ou quando alguém pediu explicitamente — em
   seleção manual, `allow_fallback` nasce `False`. No app o fallback está
   desligado na configuração, então a regra só age nos testes;
3. a decisão vira o campo **`engine` do `FinalResolvedSpec`**, resolvido por
   precedência como qualquer outro campo — e nenhuma camada posterior a
   reabre. Em `auto`, `engine_id` fica vazio e o roteamento por capacidade
   decide; a política que preenchia esse campo saiu.

**Estado atual:** as gavetas são `desenhista-v1` e as de referência,
`mock-image-v1` e `mock-pixel-alt-v1`, que só existem nos testes (três travas;
ver "Plano do app"). A desenhista só atende quem manda **receita**, e a tela não
manda: um pedido sem receita falha com a mensagem dela, e não há outra gaveta
para tentar. Por isso "Gerar" está desligado até a fila da Fase B.

**Gaveta sem seed não vira lotes.** O kernel divide um pedido em lotes pelo
`max_variations` da gaveta, variando a seed. Para uma gaveta com
`supports.seed: false`, isso só copiaria a imagem: o kernel recusa o pedido
acima do limite com `InvalidGenerationRequest`, antes de carregar a gaveta
(`kernel/service.py`, `_run_candidate`). A regra lê o manifesto; nenhum id é
citado.

As rotas de motor da API (`/api/generation/engines…`) ficam para diagnóstico.
Detalhes, incluindo como acrescentar a próxima gaveta:
[backend/docs/ENGINES.md](backend/docs/ENGINES.md).

### Pixel Optimizer (`backend/assetflow/pixel/optimizer/`)

Depois que o motor gera e o pós-processamento reduz para a grade, **toda**
geração Pixel Art passa pelo `AssetFlowPixelOptimizer`: ele revisa o sprite na
resolução lógica real e corrige o que tiver correção segura — pixel órfão,
contorno esfarelado, cor fora do orçamento.

Ele **não é escolhível**, e a ausência é a arquitetura. O AssetFlow já teve um
seletor de "método de criação" com "Modelo de imagem" e "Agente Pixel" lado a
lado, e os dois não são alternativas: o motor produz a imagem, o Optimizer
corrige a imagem produzida. Não há campo no pedido para desligá-lo, não há
controle na tela e não existe um `if engine ==` em lugar nenhum — o estágio
mora dentro da ilha Pixel Exact, e nenhuma gaveta decide o que acontece depois
de devolver a imagem.

Três regras que valem ao mexer aqui:

- **sempre na grade real.** Reparar em 1024px e reduzir depois devolveria o
  problema pela porta por onde ele entrou;
- **preservar é uma decisão registrada.** Um pixel isolado pode ser um olho: se
  a cor dele aparece em quantidade no sprite, ele é vocabulário do desenho e
  fica — com o motivo escrito em `RepairPlan.declined`;
- **otimizar não pode piorar.** Se a nota cai, a correção é descartada e o
  sprite original volta.

Configuração em `config/optimizer.yaml` (teto de iterações, revisor,
interruptor de instalação). Detalhes em
[backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md).

### Pixel Exact (`backend/assetflow/pixel/`)

No modo Pixel Art, "parecer Pixel Art" não basta: o asset só é entregue como
Pixel Exact com resolução lógica real, alpha binário, paleta dentro do limite e
validação técnica aprovada. Essa tecnologia mora em `assetflow/pixel/` — na
estante, **fora das gavetas**: ela recebe `(imagem, PixelOutputSpec)` e não
conhece motor, job nem storage. O encaixe com a cadeia de pós-processamento é
o `PixelExactProcessor` (`generation/postprocessing/pixel/exact.py`), a única
peça que conhece as duas pontas. Detalhes em
[backend/docs/PIXEL_EXACT.md](backend/docs/PIXEL_EXACT.md).

### Configuração (`backend/config/`)

- `engines.yaml` — quais gavetas existem (allowlist) e como cada uma é
  configurada: `desenhista-v1` e as duas de referência.
- `profiles.yaml` — Generation Profiles: descrevem **o que** produzir
  (resolução lógica, paleta, variações), nunca **com qual motor**.
- `pixel_profiles.yaml` — contratos Pixel Exact (`PixelOutputSpec`): fonte dos
  valores concretos dos profiles oficiais. Um `pixel_profile` do
  `profiles.yaml` aponta para um bloco daqui. Defaults conservadores ainda
  existem nos modelos para compatibilidade com profiles antigos sem essa
  referência.
- `capabilities.yaml` — as rotas por capacidade. No app, as três rotas Pixel
  listam só a desenhista, sem fallback e com `allow_unlisted_engines: false`.
  Os testes trocam essa política pela deles (`ROTEAMENTO_DE_TESTE`, no
  `tests/conftest.py`). O `engine_policy.yaml` do modo "Automático" saiu na
  Fase A do plano do app.
- `optimizer.yaml` — o estágio que **toda** geração Pixel atravessa (plano
  Optimizer §33 e §42): teto de iterações, revisor e o interruptor de
  instalação. Não há aqui uma chave por pedido: a otimização não é opção de
  quem pede. `enabled: false` é para diagnóstico, e o job registra `disabled`.
- `quality.yaml` — os limiares da nota de **estilo** para blocos pequenos e
  cores raras, calibrados pelas referências (p90 do pacote mais alto), todos
  `a_calibrar`. Nada ali toca um hard check. O `bootstrap` monta **um**
  validador com eles e o entrega ao pipeline, ao laço do Optimizer e à rota
  de dev; o relatório grava qual calibração valeu (`quality.calibration`).
  Ausente, valem os números do plano §60, em `validation/calibration.py`, e o
  boot avisa. Os outros indicadores (órfãos, contorno, ocupação, redundância)
  continuam no código: órfãos é a próxima calibração, na Fase 5.
- `asset_taxonomy/*.yaml` — vocabulário semântico por tipo de asset, em
  português e inglês. Um arquivo por tipo; o nome do arquivo não importa, o
  campo `type:` sim. Diretório ausente não quebra o boot: o classificador
  emudece e o tipo do profile volta a prevalecer.
- `pixel_knowledge/` — a base de conhecimento do desenhista (plano
  desenhista, Fase 3): paletas e rampas, direção de luz, proporções por forma
  e tamanho, moldes-base em `silhuetas/`, e a lista de verificação do olhar
  (`olhar.yaml`, Fase B2). Só YAML; só a porta MCP a lê.
  Diretório ausente não quebra o boot: o recorte sai vazio.
  `referencias.yaml` diz quais pacotes de `data/referencias/` estão ativos.

### Fronteiras verificadas por teste

`tests/test_architecture_boundaries.py` falha o build se alguém acoplar o
sistema a uma tecnologia de IA. Ele proíbe, via AST:

1. Importar `torch`/`diffusers`/`transformers`/`openai`/… fora de
   `generation/engines/<gaveta>/`.
2. Importar uma gaveta concreta de fora de `engines/`.
3. Uma gaveta importar outra gaveta.
4. `engines/__init__.py` importar qualquer gaveta (a estante não depende das gavetas).
5. Kernel e schemas dependerem de camadas superiores (jobs, api, storage).
6. Símbolos de fornecedor (`StableDiffusionXLPipeline`, …) fora das gavetas.

`tests/contract/test_engine_contract.py` gera casos automaticamente a partir
dos manifestos descobertos: **toda gaveta nova é testada sem escrever teste
novo**. Gavetas cujas dependências não estão instaladas são puladas, não
falhadas. Uma gaveta que precise de entrada própria para gerar (a desenhista
precisa de receita) põe um `exemplo_contrato.json` ao lado do manifesto: o
conteúdo vira `engine_options[<id>]` no pedido do contrato.

### Frontend

React 18 + Vite + TS. A interface conhece **Pixel Art** e mais nada — o rótulo
vira uma capacidade em `src/types.ts`. Desde a Fase A do plano do app ela não
pergunta nada de tecnologia: saíram o seletor e o crédito de motor e o modo 2D
Normal. Desde a Fase B, **"Gerar" cria um pedido** na fila (`usePedidos`,
`PedidosList`, `LiberdadeControls`), e o desenho acontece pela conversa com o
Claude, pelo MCP; o resultado aparece sem recarregar a página. Desde a Fase
B2, o pedido aprovado aparece como "olhando" até o Claude concluí-lo; o
resultado pronto mostra a linha do olhar e "gostei"/"não gostei"
(`OpiniaoControls`), e `LicoesPanel` lista as lições. A prévia do painel é a dos pedidos (`/api/pedidos/previa`),
para o spec mostrado ser o gravado. Nenhum id de motor está escrito no frontend.

A tela mostra o `FinalResolvedSpec` que o backend devolve: o painel "O que o AssetFlow
entendeu" tem a aba **Interpretação** (o contrato em português, com a origem de
cada valor) e a aba **JSON final** (o mesmo objeto, editável). Editar ali vira
`spec_overrides` — correção manual, o nível mais alto da precedência. Os
controles de tipo/resolução/paleta/fundo viram `output`, o nível da interface;
um controle em "Automático" **não envia campo nenhum**, e é assim que o
classificador e o profile continuam podendo responder. Nenhum componente
sabe o que é um motor, e o bloco `engine` do JSON não vira correção. Todo acesso à API passa por
`src/services/generationApi.ts` (`BASE_URL = "/api/generation"`, mesma origem,
sem CORS).

O front **não abre por `file://` nem por Live Server**: `main.tsx` é TS+JSX e
os imports são bare specifiers que só o Vite resolve.

## Armadilhas conhecidas

- **`job_timeout_s` (padrão 900s) engole tudo.** O worker envolve o pipeline
  inteiro em `asyncio.wait_for`, e o *carregamento do modelo* acontece dentro
  dessa janela. Os `timeouts` do `engines.yaml` são deadlines internos — se o
  teto do worker for menor, ele mata antes e os valores do YAML nunca são
  atingidos. Ao alargar um, alargue o outro (`ASSETFLOW_JOB_TIMEOUT_S`).
- **`backend/data/` é volátil e ignorado pelo git** — assets gerados, histórico
  e, em instalações anteriores à Fase 0, o cache de modelos (vários GB) moram
  lá. Nunca faça `rmtree` na pasta toda.
- **Diferenças de hardware vão em env var, não no YAML.** `engines.yaml` é
  versionado e compartilhado; editar direto gera conflito de merge a cada pull.
  Além de `ASSETFLOW_ENGINES_ENABLED`/`_DISABLED`, as **opções** de cada gaveta
  entram por `ASSETFLOW_ENGINE_<ID>_OPTIONS` como JSON (id em maiúsculas, `-`
  vira `_`), com merge por chave sobre o YAML. É assim que entra tudo o que
  muda de máquina para máquina (caminhos, limites):

  ```bash
  ASSETFLOW_ENGINE_MOCK_IMAGE_V1_OPTIONS='{"simulated_latency_ms": 0}'
  ```
- **Credencial nunca vai no YAML.** Uma gaveta que precise de chave lê do
  ambiente, e o `engines.yaml` guarda no máximo o **nome** da variável. O
  caminho do desenhista não usa chave nenhuma.
- **As gavetas de referência só existem nos testes.** Os mocks declaram
  `catalog.dev_only` (o nome ficou; o significado hoje é "só em
  `AppEnvironment.TEST`") e não são **registrados** em `development` nem em
  `production` — não são apenas escondidos. `ASSETFLOW_APP_ENV` deixou de mudar
  o que o app gera, e `test` não é aceito pela variável: só o `conftest` e o
  `scripts/preview_engine.py` ligam esse ambiente, por código. O app tem só a
  `desenhista-v1`, que exige receita.
- **A suíte roda com as gavetas de referência, não com as entregues.** A
  fixture `settings` monta o ambiente `TEST`, e o `container` de teste troca a
  política de rotas pela `ROTEAMENTO_DE_TESTE` e desabilita tudo fora de
  `REFERENCE_ENGINES` (`tests/conftest.py`). Para conferir o app como ele roda,
  monte o container sem essas fixtures (`tests/test_gerador_unico.py`). A maior parte dos testes exercita *mecanismo* —
  roteamento, troca de motor, fallback — e mecanismo se testa com motores
  previsíveis; amarrá-los ao conjunto que o projeto por acaso entrega
  habilitado os quebraria a cada gaveta nova. Um teste que precise de uma
  gaveta de produto a habilita pelo nome (`container.registry.enable(...)`).
- **O que o `FinalResolvedSpec` já resolveu não se resolve de novo.** Ler
  `profile.output.logical_width` dentro do pipeline, do pós-processamento ou da
  validação é reintroduzir o bug do 32×32: o profile é só uma das seis camadas,
  e a mais fraca depois do padrão global. O caminho é `context.resolved`.
- **Com `pixel_profile` declarado, o profile Pixel é a fonte única da verdade
  técnica** — *de partida*. O `FinalResolvedSpec` do job entra por cima dele
  (resolução lógica, paleta e fundo) em `postprocessing/pixel/spec.py`, que é o
  único ponto onde isso acontece. Mexer em `output.logical_*` ou `palette.size` só no `profiles.yaml`
  não muda um pixel do arquivo gerado — muda apenas a vitrine da API
  (`GET /api/generation/profiles`). O que vale é o bloco correspondente em
  `pixel_profiles.yaml`; mude os dois juntos (existe teste para essa
  coerência).
- **`PixelValidator()` sem argumento é o validador do plano, não o da
  instalação.** Os limiares de blocos pequenos e cores raras vêm de
  `config/quality.yaml` só quando alguém passa a calibração: o `bootstrap`
  (`container.pixel_validator`) e o `calibrar` passam. Um validador montado à
  mão em código de produto devolve outra nota para o mesmo sprite. Nos testes
  isso é de propósito: eles fixam o mecanismo com os números do plano.
