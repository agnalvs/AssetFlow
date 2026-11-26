# Relatório de estado — branch `desenhista-mcp`

Data: 2026-11-25 (atualizado depois da Fase B do plano do app). Base: `main` em `be3e9aa`. Escrito para quem revisa pelo
GitHub, sem acesso à máquina onde o trabalho foi feito. Onde um número veio de
dado que só existe nessa máquina (assets gerados, pacotes de referência), o
texto diz isso.

Documentos que este relatório resume e que valem ler junto:
[PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md) (o plano),
[PIXEL_KNOWLEDGE.md](PIXEL_KNOWLEDGE.md) (a pesquisa que vira configuração),
[DESENHISTA.md](DESENHISTA.md) (a gaveta e a receita), [MCP.md](MCP.md)
(servidor, laudo, remendo e recorte), [REFERENCIAS.md](REFERENCIAS.md)
(biblioteca de referências), [PLANO_APP_DESENHISTA.md](PLANO_APP_DESENHISTA.md)
(o plano do app, que começa pela Fase A) e o [CLAUDE.md](../../CLAUDE.md) da raiz.

---

## 1. Linha do tempo

Todos os commits do branch, em ordem. Cada um passou com `pytest -q` sem
falhas e sem achado novo do ruff: o baseline foi de 154 até a Fase A do plano
do app, que o baixou para 144 (os achados estavam em arquivos apagados).

| Commit | Fase | O que mudou | Testes |
|---|---|---|---|
| `1d99cb8` | Fase 0 — limpeza | Saem cinco gavetas (`diffusers-sdxl-v1`, `flux-pixel-v1`, `sdpixl-v1`, `pixel-forge-v1`, `gpt-image-v1`), o benchmark entre motores, o extra `diffusers` do `pyproject.toml` e os testes dessas peças. Configs e documentação atualizadas. O modo Studio (2D Normal) fica, dormente. | 1254 / 1 pulado ¹ |
| `eef3dce` | Fase 1 — gaveta desenhista | Nova gaveta `desenhista-v1` (família `agentic`): recebe uma receita em camadas e rasteriza na grade lógica 1:1. Rasterizador próprio dentro da gaveta, exemplo de receita, `exemplo_contrato.json` para o teste de contrato. | ¹ |
| `5572c5d` | Fase 2 — servidor MCP | `assetflow/mcp/`: `consultar_pedido`, `desenhar` (com remendo por `base`) e `ver_asset`, sobre o mesmo `GenerationService`, sem HTTP. SDK `mcp` como extra opcional. | 1254 / 1 |
| `d3dc498` | Fase 3 — base de conhecimento mínima | `config/pixel_knowledge/` (paletas do Lospec, luz, proporções, dois moldes) e `assetflow/pixel_knowledge/` (carga, formato, seletor do recorte com teto). Recorte entregue no fim de `consultar_pedido`. Nota da Fase 5 anotada no plano. | 1323 / 1 |
| `742dc23` | Ajuste da Fase 3 | O recorte padrão deixa de trazer o JSON do molde (só com `molde=true`). Humanóide 32×32 refeito: cabeça 10, tronco 8, pernas 10, larguras. Regras novas de sombra e de equipamento. Rampa `tecido_vermelho` sem o roxo. | 1330 / 1 |
| `4223350` | Ajuste da Fase 3 | Corpo separado do quadro: `quadros` em `proporcoes.yaml` (corpo de 32 num quadro 48×48). Linha `quadro:` no recorte. Molde deslocado para o quadro maior. Profile `pixel_character_48`. Entram `.gitignore` (`.mcp.json`) e o registro do MCP por arquivo no `SETUP.md`. | 1342 / 1 |
| `83ad35a` | Ajuste da Fase 3 | A regra "vão entre braço e tronco e entre as pernas" passa a valer só com o membro à mostra. | 1343 / 1 |
| `8520337` | Ajuste da Fase 3 | A linha `quadro:` deixa de afirmar o vão do braço como exigência. | 1343 / 1 |
| `0e67bc8` | Adiantado antes da Fase 4 | Biblioteca de referências: `assetflow/referencias/` (importar, medir, somar, calibrar), `config/pixel_knowledge/referencias.yaml`, linha `referências:` no recorte, ferramenta `ver_referencia`. | 1410 / 1 |
| `d77cb6a` | Estado | Lista de ativos com os cinco pacotes importados, `PIXEL_STYLES.md`, `REFERENCIAS_FONTES.md` e este relatório. Nenhum código. | 1410 / 1 |
| `40e4bae` | Correções da revisão | Pendências 1, 2 e 12: Retraissance reimportada com quadro 64×128; importador ganha `--excluir` (com teste) e o Ninja Adventure é reimportado sem `Faceset.png` e `SpriteInHand.png`; `calibrar` refeito; `.env` e `.env.*` no `.gitignore`, `.env.example` continua versionado. | 1411 / 1 |
| `9795710` | Calibração | Pendências 1 e 4. **Nota:** limiares de blocos pequenos (84%) e cores raras (a partir da 4ª) em `config/quality.yaml`, `a_calibrar`, pela regra "p90 do pacote mais alto"; um validador só, do `bootstrap`, no pipeline, no Optimizer e na rota de dev; `quality.calibration` no relatório; validador 1.2.0. **Referências:** `minimo_por_pacote` (30) e `minimo_de_pacotes` (2) por parte, na linha, no `ver_referencia` (cai para o estilo) e no `calibrar` (que marca a parte insuficiente e propõe os limiares do validador). | 1440 / 1 |
| `fab1337` | Segunda leva de referências | Cinco pacotes CC0 importados e ativos (`pixel-adventure`, `sunny-land`, `hylsy-64-character`, `ninja-animated`, `super-sprite-boy`), com o quadro conferido nos arquivos; Character Prototype (não é pixel art) e Pixel Boy (pintura com centenas de cores) baixados e não importados. Só lista de ativos e documentação: nenhum limiar nem valor da base mudou. | 1440 / 1 |
| `7e02362` | Corpo do personagem | `character.yaml` com uma linha por palavra (masculino, feminino e plurais) e os nomes das formas de corpo; `category_body_types` (`humanoid -> humanoid`) deduz o corpo no resolvedor do spec, com a origem nova `category_inference` ("inferido da categoria"); o recorte diz "corpo não identificado" em vez de sair sem medidas. Teste das flexões em `test_taxonomia_flexoes.py`. | 1461 / 1 |
| `4f9fdc6` | Fase A do plano do app — simplificação | Saem o seletor e o crédito de motor e o modo 2D Normal da tela; o modo "Automático" (`auto_policy.py`, `engine_policy.yaml`, `engine_advisor.py`, `EngineAdvice`, `EngineSuggestion`, a dica `preferred_engine_id`); os pipelines Studio e Raw, o pós-processamento e os prompt builders Studio, os profiles `studio_character`, `studio_background` e `raw_image`. Mocks só no ambiente de testes (`AppEnvironment.TEST`), rotas Pixel só com a desenhista, fallback desligado. "Gerar" desligado com a frase da fila. Leitor do histórico tolerante a campos antigos. `prompting/`, `AssetMode.STUDIO`, o campo `engine` da API e o `SessionHistory` ficam. | 1448 / 1 |
| `9362e26` | Fase B do plano do app — fila de pedidos | "Gerar" cria um pedido; fila num SQLite em `data/pedidos/` (`assetflow/pedidos/`), dividida pela API (`/api/pedidos`: prévia, criar, listar, ler, cancelar, devolver) e pelo MCP (`pedidos_pendentes`, `desenhar(pedido_id)`). Spec resolvido uma vez, na criação, e executado pelo desenho (`submit(resolved=)`). Tentativas (3), reserva por leva (30 min), conclusão condicional. Liberdade criativa (fiel, equilibrado, ousado) e direção de arte, só no recorte; `liberdade` também em `consultar_pedido` e `ver_referencia` avulsos. Projeto fixo `principal`; gerador do app no `engines.yaml`. Tela com fila, prontos e resultado sem recarregar. Textos pendentes da Fase A corrigidos. | 1540 / 1 |
| `9c652c1` | Fase B2 do plano do app — ver, corrigir e aprender | `desenhar` e `ver_asset` devolvem a imagem do olhar (ampliada, silhueta, tamanho real; 294 tokens); olho do app (`referencias/olho.py`) com os desvios contra as referências do mesmo porte e o contraste entre camadas (mapa gravado pela gaveta); lista de verificação de `config/pixel_knowledge/olhar.yaml` no primeiro olhar. Aprovado no validador vai para `em_revisao` e conclui com `concluir_pedido`, até 2 remendos do olhar. Exemplo de construção CC0 convertido para receita (`referencias/exemplo.py`; regra dos sprites de terceiros mudada com autorização), guarda "repete o exemplo". `assetflow/aprendizado/` (lições, opiniões, exemplos mostrados; SQLite em `data/aprendizado/`), `registrar_licao`, `/api/aprendizado`, "gostei"/"não gostei" e lista de lições na tela. Interruptores `ASSETFLOW_EXEMPLO`/`ASSETFLOW_LICOES` e o envio gravado no pedido e no asset. `sqlite_curto.py` dividido pela fila e pelas lições. | 1642 / 1 |
| `c48c920` | Ajuste da Fase B2 | `ASSETFLOW_EXEMPLO` passa a nascer desligado: no teste da maga do gelo, o único exemplo do porte para personagem vestido foi um corpo-base sem roupa, e atrapalhou. Volta com pacotes melhores, com a diferença medida. | 1644 / 1 |
| `7baa4b5` | Lote 1 — banca e conceito | Banca de teste (`assetflow/banca/`, `config/banca.yaml`, `/api/banca`, página "Banca e Comparar"): rodadas ligadas a uma versão da base, comparação cega com nota de 1 a 5, resumo com veredito; custo por pedido registrado pelo MCP. Etapa de conceito: três modos por pedido, `propor_conceitos`, situação `escolhendo`, conceito na medida da grade, pergunta do conceito no olhar. Ajustes de custo em settings (`ASSETFLOW_CONCEITO`, `ASSETFLOW_PEDIDOS_REMENDOS`, `ASSETFLOW_OLHAR_LISTA_CURTA`), documentados em `CUSTO.md`. Entram `PLANO_BASE_CONHECIMENTO.md` e `FUNDAMENTOS_E_FERRAMENTAS.md`, da autora. | 1693 / 1 |
| `ebb0d2d` | Lote F2 — cor e luz | Comandos opcionais da receita: `rampas` (com desvio de matiz), `luz`, `material`, `sombrear` (esfera, cilindro, caixa, plano), `brilho`, `oclusao`, `sombra_projetada`. Interruptor `comandos_cor_e_luz` em `engines.yaml`; o MCP mostra no formato só os grupos ligados. | 1708 / 1 |
| `59fabc1` | Lote F3 — construção | `capsula` (2 ou 3 pontos, espessura, contorno, vão até outra camada), `copiar` (deslocada, espelhada) e `boneco` na raiz (altura, cabeças, forma dominante, linha de ação, pose, cores), que vira camadas `boneco_*`. Interruptor `comandos_construcao`. | 1724 / 1 |
| `9ffea04` | Lote F5 — ficha de verificação | Toda regra da base declara `verificacao` (`construcao`, `medida`, `olhar`, `autora`), e a carga recusa a que não declara; teste confere que o alvo existe. `concluir_pedido` com `respostas` por pergunta; `000_ficha.json` por asset (`mcp/ficha.py`) com uma linha por regra e as divergências entre resposta e medida; `GET /api/pedidos/{id}/ficha` e a ficha dobrada no resultado. Interruptor `ASSETFLOW_FICHA`. | 1735 / 1 |
| `51f14f6` | Lote 5 — editor de pixels | `assetflow/editor/` e o editor na tela (lápis, apagar, conta-gotas, paleta do asset, desfazer, prévia 2×): a troca vira a camada `retoque_N` no fim da receita, desenhada pelo caminho de sempre; aprovado, vira um pedido de ajuste já concluído (`registrar_edicao`). "O que estava errado" vira opinião pendente no original. `GET`/`POST /api/pedidos/{id}/editor`; a gaveta grava a paleta efetiva. Interruptor `ASSETFLOW_EDITOR`. | 1768 / 1 |
| `0ede490` | Lote F1 — linha e contorno | `reta` (degraus iguais), `curva` (Catmull-Rom pelos pontos, sem canto em L), `limpar_linha` (dobras, depois cantos, relata posições) e `contorno` na raiz (inteiro, seletivo, colorido). Interruptor `comandos_linha`. Olho do app: cantos em L, dobras e degraus no contorno escuro, contra limites por tipo calibrados nos pacotes ativos (p90, `scripts/calibrar_linha.py`). Ficha: `limpeza` cruza com as medidas novas; as perguntas `limpeza` reescritas no positivo (corrige o F5). | 1796 / 1 |
| `fc14d13` | Lote F4 — detalhes e acabamento | `rosto`, `extremidade`, `suavizar`, `pontilhar`, `textura`, `luz_de_borda`; interruptor `comandos_acabamento`; recusas em sprite pequeno como aviso. Olho: pontilhado por manchas de xadrez, calibrado nos pacotes. Formato dos opcionais uma vez por conversa (`ASSETFLOW_FORMATO_UMA_VEZ`, `consultar_pedido(formato=true)`). | 1820 / 1 |
| `0aa3827` | Lote 8 — base por temas | §4, 7, 8 e 17 do PIXEL_KNOWLEDGE em `config/pixel_knowledge/temas/` (5 temas, 32 regras com seção, fonte, verificação e etiquetas). Linha dos temas na consulta e uma vez no topo da lista; ferramenta `consultar_base`; regras de tema na ficha, com três medidas novas do validador (fragmentado, redundância, borda). Interruptor `ASSETFLOW_CONSULTAR_BASE`. | 1830 / 1 |
| `6c920bc` | Lote 9 — cópia de segurança | `python -m assetflow.backup criar/listar/restaurar`, botão no rodapé e `/api/backup`: zip datado de `backend/data/` fora do repositório, bancos pela cópia do SQLite (com o `-wal`), restauração com hashes, recusa de banco em uso e guarda do que havia. Interruptor `ASSETFLOW_BACKUP`. | 1852 / 1 |
| (este) | Lote 10 — um clique para abrir | `iniciar.bat` + `backend/scripts/iniciar.py`: reaproveita API e tela já de pé (IPv4 e IPv6), sobe as que faltam em portas livres, confere título e saúde pelo proxy, abre o navegador, encerra o que subiu. Conferido ao vivo com a 5173 ocupada. | 1858 / 1 |

¹ A contagem de cada commit está na mensagem dele; a Fase 0 registra 1254
passando no fim da limpeza.

---

## 2. Mapa do código

Legenda: **[novo]** criado neste branch · **[alterado]** mudou neste branch ·
sem marca = veio do `main` sem mudança relevante.

### `backend/assetflow/`

```
assetflow/
├── main.py                    App FastAPI (uvicorn assetflow.main:app).
├── bootstrap.py   [alterado]  Composition root: monta registry, kernel, pipelines, storage, jobs,
│                              e agora a base de conhecimento e as referências ativas.
├── settings.py    [alterado]  Configuração (env ASSETFLOW_* > YAML > padrão); ganhou
│                              pixel_knowledge_dir, referencias_dir e referencias_config.
├── version.py
├── api/                       Rotas HTTP (/api/generation/...). Não mudou de forma relevante.
├── generation/
│   ├── service.py             GenerationService: submit, resolve_spec, jobs, catálogo.
│   ├── spec/                  Texto -> FinalResolvedSpec (extrator, classificador, resolver, taxonomia).
│   ├── schemas/  [alterado]   Contratos: FinalResolvedSpec, pedidos, motores (família `agentic` usada).
│   ├── kernel/   [alterado]   Descoberta de gavetas, resolver de capacidade, fallback, execução.
│   │                          Fase A do app: sai auto_policy.py (o modo "Automático").
│   │                          Regra nova: gaveta sem seed não é dividida em lotes.
│   ├── engines/
│   │   ├── desenhista/ [novo] A gaveta desenhista-v1: receita.py (lê e valida), rasterizador.py
│   │   │                      (formas, px, espelho, balde -> grade), engine.py, manifest.json.
│   │   ├── mock_image/        Gaveta de referência (registrada só no ambiente de testes).
│   │   ├── mock_pixel_alt/    Gaveta de referência (idem, e desabilitada).
│   │   └── (removidas: diffusers_sdxl, flux_pixel, gpt_image, pixel_forge, sdpixl)
│   ├── pipelines/ [alterado]  Só pixel.character (PixelCharacterPipeline); Studio e Raw saíram.
│   ├── postprocessing/        Ponte Pixel (PixelExactProcessor); o Studio saiu.
│   ├── prompting/ [alterado]  Prompt semântico de todo job Pixel; só os builders Pixel.
│   ├── profiles/
│   └── (removido: benchmark/)
├── pixel/        [alterado]   Ilha Pixel Exact: processamento, validação, Optimizer, aceite, preview.
│   ├── validation/ [alterado] PixelValidator, analisadores, QualityScorer (seção 9);
│   │                          calibration.py [novo]: limiares de blocos pequenos e cores raras.
│   └── optimizer/             AssetFlowPixelOptimizer (revisa e corrige na grade real).
├── pixel_knowledge/ [novo]    Base de conhecimento para o desenhista:
│   ├── base.py                Carga e formato de config/pixel_knowledge (paletas, luz, proporções,
│   │                          quadros, moldes); BaseDeConhecimento.estilo() é o ponto único.
│   └── recorte.py             Seletor: lê 5 campos do spec e monta o recorte com teto; porte().
├── referencias/ [novo]        Biblioteca de referências (seção 8):
│   ├── pacote.py              Manifesto, licença, partes, lista de ativos.
│   ├── importador.py          Zip ou pasta -> data/referencias/<id>/; medir_pacote.
│   ├── medidor.py             Medidas por quadro, sem IA (numpy + Pillow).
│   ├── colecao.py             Soma com peso igual por pacote; linha do recorte; exemplo.
│   ├── calibracao.py          Relatório que propõe ajustes e roda o validador nas referências.
│   └── __main__.py            CLI: importar, listar, medir, calibrar.
├── mcp/ [novo]                Servidor MCP (seção 4):
│   ├── servidor.py            Protocolo (SDK `mcp`, opcional): as 4 ferramentas.
│   ├── servico.py             O trabalho, sem o SDK: consultar, desenhar, ver, ver_referencia.
│   ├── laudo.py               Textos que o Claude lê (consulta e laudo).
│   ├── remendo.py             Receita parcial sobre a receita de um asset anterior.
│   └── __main__.py            python -m assetflow.mcp
├── jobs/                      Fila, store e GenerationWorker (o MCP roda o worker ele mesmo).
├── storage/   [alterado]      Assets, artefatos e histórico (data/history/generations.jsonl);
│                              o leitor ignora campos de topo que saíram do modelo.
├── pedidos/   [novo]          A fila de pedidos da tela (Fase B do app): modelo.py (situações,
│                              etapas), fila.py (SQLite, transições condicionais), servico.py
│                              (montar, prévia, criar; spec resolvido uma vez).
└── llm/                       Revisor opcional do Optimizer por modelo (não usado por padrão).
```

### `backend/config/`

```
config/
├── engines.yaml          [alterado]  Allowlist: desenhista-v1 + as duas de referência.
├── (engine_policy.yaml)  [removido]  O modo "Automático" saiu na Fase A do app.
├── capabilities.yaml     [alterado]  Rotas Pixel só com a desenhista; sem fallback nem motor fora da rota.
├── (engines.yaml)        [alterado]  + `gerador: desenhista-v1`, o gerador dos pedidos da tela.
├── profiles.yaml         [alterado]  + pixel_character_48; − studio_character, studio_background, raw_image.
├── pixel_profiles.yaml   [alterado]  + pixel_character_48_strict (48×48, 12 cores, prévia 10×).
├── optimizer.yaml                    Teto de iterações, revisor, interruptor.
├── quality.yaml          [novo]      Limiares da nota: blocos pequenos e cores raras (seção 9).
├── asset_taxonomy/*.yaml             Vocabulário por tipo de asset.
└── pixel_knowledge/      [novo]      Base de conhecimento (seção 7):
    ├── paletas.yaml                  Endesga 32 (mestra), Sweetie 16, PICO-8, DawnBringer 16.
    ├── luz.yaml                      Direção padrão e regras de luz e sombra.
    ├── proporcoes.yaml               Medidas por forma e tamanho; quadros maiores; regras.
    ├── referencias.yaml              Pacotes ativos; faixa de porte; mínimos por pacote e por parte.
    └── silhuetas/                    Moldes-base: humanoid_32x32.yaml, prop_32x32.yaml.
```

Testes novos: `test_desenhista.py`, `test_mcp.py`, `test_mcp_servidor.py`,
`test_pixel_knowledge.py`, `test_referencias.py`, `pixel/test_quality_calibration.py`,
`test_taxonomia_flexoes.py`, `test_gerador_unico.py`, `test_historico_antigo.py`,
`test_pedidos_fila.py`, `test_pedidos_processos.py` (dois processos de verdade),
`test_pedidos_api.py`, `test_pedidos_mcp.py`, e seções novas em
`test_architecture_boundaries.py`.

---

## 3. Fluxo de um desenho pelo MCP, do pedido ao PNG

1. **Consulta.** O Claude chama `consultar_pedido` → `mcp/servidor.py`
   (`consultar_pedido`) → `mcp/servico.py` `ServicoDesenhista.consultar`:
   - `_pedido` monta um `AssetGenerationRequest` com `engine=manual,
     desenhista-v1, allow_fallback=False`, uma variação;
   - `GenerationService.resolve_spec` → `generation/spec/` resolve o
     `FinalResolvedSpec` (extrator de restrições do texto, classificador da
     taxonomia, precedência);
   - `pixel_knowledge/recorte.py` `montar_recorte(spec, base, molde=…,
     referencias=…)` monta o recorte a partir de 5 campos do spec;
   - `mcp/laudo.py` `formatar_consulta` escreve o texto.
2. **Desenho.** O Claude escreve a receita e chama `desenhar` →
   `ServicoDesenhista.desenhar`:
   - com `base`, `_registro` acha o asset no histórico e `mcp/remendo.py`
     `aplicar_remendo` junta a receita parcial à da base;
   - `_executar` → `GenerationService.submit` (resolve o spec **uma vez** e
     cria o job) → laço de `GenerationWorker.run_once` (`jobs/worker.py`) até
     o job terminar (o teto é `job_timeout_s` + 30 s).
3. **Pipeline.** `pipelines/base.py` `ImageAssetPipeline.run`
   (`PixelCharacterPipeline`) monta o pedido de imagem e chama
   `GenerationKernel.execute` (`kernel/service.py`), que resolve a gaveta pelo
   nome (sem fallback) e chama `DesenhistaEngine.generate`
   (`engines/desenhista/engine.py`):
   - `receita.py` `ler_receita` valida (erro em português dizendo onde);
   - `rasterizador.py` `desenhar` aplica as camadas na grade e `para_png`
     grava o PNG 1:1; a gaveta recusa mais cores (chaves) do que o
     `max_colors` do spec.
4. **Pós-processamento e validação.** `postprocessing/pixel/exact.py`
   `PixelExactProcessor` → `pixel/service.py` `PixelAssetProcessor.run`:
   processamento Pixel Exact, validação V1 (`PixelValidator.validate`),
   `AssetFlowPixelOptimizer` (corrige o que é seguro; descarta se a nota cai),
   validação V2 e `PixelAcceptancePolicy` (aprovado se Pixel Exact e nota ≥ 70).
5. **Storage.** `AssetStorageService` grava `000.png`, prévia, miniatura e os
   relatórios (`000_validation.json`, `000_optimizer.json`,
   `000_engine_output.json`, …) em `data/assets/projects/mcp/jobs/<job>/` e
   uma linha no histórico.
6. **Laudo.** `ServicoDesenhista._laudo` lê os relatórios gravados e
   `formatar_laudo` escreve o veredito, a nota, os problemas (com posição
   quando o validador a expõe), os avisos da receita, o Optimizer e o caminho.
7. **Ver.** `ver_asset` amplia o PNG por vizinho mais próximo até ~256 px.
   `ver_referencia` devolve um quadro dos pacotes ativos (seção 8).

---

## 4. Ferramentas MCP

Texto exato, como o SDK as expõe (gerado de `criar_servidor`).

**`consultar_pedido`** — Resolve um pedido de pixel art em texto livre (ex.: "cavaleiro 32x32, 8 cores, sem fundo") e devolve o que o AssetFlow entendeu, o formato da receita e as medidas, a paleta e a luz da base. Chame antes de desenhar.
- `pedido` (string, obrigatório): O pedido em texto livre.
- `perfil` (string | null, padrão null): Profile de partida; só vale no que o texto não disser. Opções: pixel_character_32, pixel_character_48, pixel_character_64, pixel_prop_64. Padrão: pixel_character_32.
- `molde` (boolean, padrão false): true inclui a receita do molde-base; sem ele, só as medidas.
- `liberdade` (string | null): Fiel (padrão, como hoje), equilibrado ou ousado: muda só a orientação do recorte; grade, cores e fundo não mudam.

**`pedidos_pendentes`** — Lista os pedidos feitos na tela do AssetFlow que esperam desenho, cada um já com o que consultar_pedido devolveria, e os reserva para você. Desenhe cada um com desenhar(pedido_id=...).
- `limite` (integer, padrão 5): Quantos pedidos trazer, dos mais antigos (padrão 5, máximo 10).

**`desenhar`** — Desenha um sprite a partir de uma receita e devolve o laudo: aprovação, nota, problemas, id do asset e caminho do PNG. Para corrigir, passe base=<id> e só o que mudou. Com pedido_id, atende um pedido da fila da tela.
- `pedido` (string | null): O mesmo texto de consultar_pedido. Com base, pode omitir.
- `receita` (object | null): A receita completa; com base, só paleta e camadas alteradas.
- `base` (string | null): Id de um asset anterior, para remendo.
- `perfil` (string | null): Igual a consultar_pedido; num remendo, o da base.
- `pedido_id` (string | null): Id de um pedido de pedidos_pendentes. Texto, perfil e controles vêm dele: omita pedido e perfil. Aprovado, o pedido fica concluído e aparece na tela.

**`ver_referencia`** — Mostra UMA imagem de referência dos pacotes livres ativos, do tipo de asset do pedido, ampliada. Serve para ver estilo, não para copiar; use só quando precisar ver.
- `pedido` (string, obrigatório): O mesmo texto de consultar_pedido.
- `perfil` (string | null): Igual a consultar_pedido.
- `liberdade` (string | null): Fiel (padrão, como hoje), equilibrado ou ousado; em ousado, a imagem é escolhida pelo estilo, sem o filtro de porte.

**`ver_asset`** — Mostra o PNG de um asset, ampliado, para revisão visual. Custa mais contexto que o laudo: use só quando precisar ver.
- `id` (string, obrigatório): Id do asset.

---

## 5. Receita e resposta de `consultar_pedido`

### Formato da receita

Detalhes em [DESENHISTA.md](DESENHISTA.md). Em resumo:

- `grade: [l, a]` (opcional; se vier, tem de bater com o pedido),
  `paleta: {chave de 1 caractere: "#rrggbb"}` e `camadas: [{nome, espelho?, ops}]`;
- operações: `ret` e `elipse` `[x, y, l, a]` (com `contorno` opcional),
  `linha [x0, y0, x1, y1, …]`, `poligono [x0, y0, …]`, `balde [x, y]`
  (proibido em camada com espelho) e `px ["linha", …]` em `em: [x, y]`
  (`.` mantém, `-` apaga);
- camadas pintam por cima em ordem; o espelho (`x`, `y`, `xy`) só preenche o
  que a camada não pintou;
- a desenhista conta cor por **chave**, não por hexadecimal: mais chaves usadas
  que o `max_colors` do spec é erro.

### Exemplo real de receita

O cavaleiro em quadro 48×48 (`asset_15607e958c4f`, aprovado com 84):

```json
{"grade":[48,48],"paleta":{"k":"#181425","s":"#5a6988","m":"#8b9bb4","l":"#c0cbdc","d":"#733e39","R":"#a22633","r":"#e43b44","g":"#feae34"},"camadas":[{"nome":"pernas","ops":[{"em":[17,37],"px":[".klmsk..klmsk.",".klmsk..klmsk.",".klmsk..klmsk.",".klmsk..klmsk.",".klmsk..klmsk.",".klmsk..klmsk.",".klmsk..klmsk.",".kmssk..kmssk.","kmmssk..kmmssk","kkkkkk..kkkkkk"]}]},{"nome":"tronco","ops":[{"em":[18,29],"px":["kklmmmmmsskk","kkrRRRRRddkk","kkrRRRRRddkk","kkrRRRRRddkk","krrRRRRRRddk","krrRRRRRRddk","kssssggssssk","krrRRRRRRddk","kkkkkkkkkkkk"]}]},{"nome":"braco_esq","ops":[{"em":[30,29],"px":["kkkk..","mmmsk.","klmmsk",".klmsk",".klmsk",".klmsk",".klmsk",".kmmsk",".kmmsk","..kkk."]}]},{"nome":"braco_dir","ops":[{"em":[7,32],"px":[".....kkkkkkk","klmmklllllmk","kmmskmmmmmsk","kmsskssssssk",".....kkkkkk."]}]},{"nome":"cabeca","ops":[{"em":[18,19],"px":["...kkkkkk...",".kkllmmmskk.","klllmmmmmssk","kllmmmmmmssk","klkkkkkkkksk","klmmmmmmmssk","kmmmmmmmsssk","kmmmmmmmsssk",".kmmmmmsssk.","..kkkkkkkk.."]}]},{"nome":"crista","ops":[{"em":[21,17],"px":[".kkkk.","krRRdk","kRRddk"]}]},{"nome":"ombreiras","ops":[{"em":[14,28],"px":["..kkk.",".kllmk","klmmmk","kmmssk",".kkkk."]},{"em":[28,28],"px":[".kkk..","kmmsk.","kmmssk","kmsssk",".kkkk."]}]},{"nome":"espada","ops":[{"em":[8,18],"px":[".kk.","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk","klmk"]},{"em":[7,32],"px":["kggggk"]},{"em":[8,36],"px":["kggk",".kk."]}]},{"nome":"escudo","ops":[{"em":[36,31],"px":["kkkkkkkk","krRggRdk","krRggRdk","kggggggk","krRggRdk","krRggRdk","krRggRdk",".kRggdk.",".kRggdk.","..kggk..","...kk..."]}]}]}
```

### Exemplo real de resposta

`consultar_pedido("cavaleiro 32x32, 8 cores, sem fundo")`, com o código deste
branch e os dez pacotes de referência ativos (3.089 caracteres; o recorte, a
partir de `conhecimento:`, tem 2.274):

```text
pedido: cavaleiro 32x32, 8 cores, sem fundo (perfil pixel_character_32)
tipo: character · cavaleiro · categoria humanoid · corpo humanoid (inferido)
grade: 32×32 (do texto) · paleta: até 8 cores (do texto) · fundo: transparente (do texto)
estilo: contorno auto · sombreamento auto · luz não definida
motor: desenhista-v1

receita: {"grade": [l, a], "paleta": {"k": "#rrggbb", ...}, "camadas": [{"nome": ..., "espelho"?: "x"|"y"|"xy", "ops": [...]}]}
ops: ret|elipse [x, y, l, a] e poligono [x0, y0, ...], com cor e contorno? · linha [x0, y0, x1, y1, ...] cor
     balde [x, y] cor (não vale em camada com espelho) · px ["linha", ...] em [x, y] ('.' mantém, '-' apaga)
origem no canto superior esquerdo; chave de cor tem 1 caractere; camada seguinte pinta por cima;
o espelho só preenche o que a camada não pintou.

conhecimento:
humanóide 32×32: cabeça y3–12 (10 px) · tronco y13–20 (8 px) · pernas y21–30 (10 px) · chão y=30 (pixel opaco mais baixo) · folga y1–2 acima da cabeça, para crista, penacho ou cabelo · larguras com contorno: cabeça 12, tronco 12, braço 5, perna 5 · olho 2×2 com brilho de 1 px · 3 tons por material
quadro: corpo centrado entre x=15 e x=16, com braços em x4–27 (colunas contando o braço separado do tronco por 1 px, o que só vale com o membro à mostra); livre x1–3 e x28–30 dos lados, para arma, escudo, crista e animação
luz: de cima e da esquerda (padrão da base; o pedido não definiu) · luz do lado de onde ela vem e sombra no oposto, nunca só acompanhando o contorno · sombra principal com o vizinho imediato da rampa; o tom mais escuro só em pontos pequenos, nunca em faixa
cores: até 8, contorno incluído · paleta-mestra endesga-32, rampas do escuro ao claro; cada material usa tons vizinhos de uma rampa:
  contorno #181425
  metal #262b44 #3a4466 #5a6988 #8b9bb4 #c0cbdc #ffffff · pedra #262b44 #3a4466 #5a6988 #8b9bb4
  pele #733e39 #b86f50 #e4a672 #ead4aa · pele_rosada #733e39 #c28569 #e8b796
  madeira #3e2731 #733e39 #b86f50 #d77643 #e4a672 · ouro #be4a2f #f77622 #feae34 #fee761
  tecido_vermelho #733e39 #a22633 #e43b44 #f77622 · tecido_azul #262b44 #124e89 #0099db #2ce8f5
  tecido_roxo #3e2731 #68386c #b55088 #f6757a · folha #193c3e #265c42 #3e8948 #63c74d
silhueta: arma e escudo fora do corpo, com vão de 1 px, mudando o contorno · o equipamento muda o contorno do corpo (ombreiras, elmo com crista, capa), não só a cor por dentro · uma assimetria intencional: pose, arma, cabelo ou capa · vão entre braço e tronco e entre as pernas quando a roupa deixa o membro à mostra; com manto, capa, vestido ou roupa larga, vale a silhueta da roupa · partes vizinhas com valores diferentes, antes de matizes diferentes
camadas: pernas, tronco, braco_dir, braco_esq, cabeca (direita e esquerda do personagem) · a receita do molde-base vem com molde=true
referências: estilo de 2985 quadros (9 pacotes, peso igual): contorno escuro único em 58% (cor mais comum #222222) · 3 tons por grupo de matiz (mediana); porte de 23–33 px de altura, 515 quadros (3 pacotes, peso igual): 7–24 cores (mediana 11) · largura 0,81× a altura · preenchimento 76% da caixa
```

A linha `referências:` tem as duas partes. O porte do humanóide 32 tem 515
quadros de 3 pacotes: Customizable (400), Pixel Adventure (85) e Super Sprite
Boy (30). Ficam fora dele, por terem menos de 30 quadros na faixa: Kings and
Pigs (26), SunnyLand (12), DungeonTileset (2), Ninja [Animated] (2) e
Retraissance (1). Com os cinco pacotes da primeira leva, o porte tinha ficado
com um pacote só e saía da linha; antes dos mínimos, 1 quadro da Retraissance
pesava como os 400 do Customizable (seção 12, item 1). O `pixel_character_48`
("cavaleiro, 8 cores, sem fundo") dá a mesma linha: o corpo é o mesmo, de 32.

---

## 6. Laudo devolvido por `desenhar`

Exemplo real: o cavaleiro da seção 5, redesenhado com a mesma receita e o perfil
`pixel_character_48`, já com a calibração da nota (seção 9):

```text
APROVADO · asset_7b32cac39b80 · cavaleiro em quadro 48x48, corpo de 32, 8 cores, sem fundo
Pixel Exact ✓ · qualidade 100/100 (mínimo 70)
grade 48×48 · 8 de 8 cores · fundo transparente
Optimizer: nada a corrigir
arquivo: <data>/assets/projects/mcp/jobs/job_d0d5832063c6/000.png
```

O mesmo desenho, antes da calibração (`asset_15607e958c4f`, perfil padrão):

```text
APROVADO · asset_15607e958c4f · cavaleiro em quadro 48x48, corpo de 32, 8 cores, sem fundo
Pixel Exact ✓ · qualidade 84/100 (mínimo 70)
grade 48×48 · 8 de 8 cores · fundo transparente
problemas:
- 19 de 54 blocos de cor têm 3 pixels ou menos (35.19%) — a imagem pode não ter superfícies sólidas
Optimizer: nada a corrigir
arquivo: <data>/assets/projects/mcp/jobs/job_813e9e88e4d6/000.png
```

---

## 7. Base de conhecimento (`config/pixel_knowledge/`)

Carregada no boot por `BaseDeConhecimento.do_diretorio`. Arquivo fora do
formato é ignorado com aviso (e listado em `problemas`; a configuração atual
tem zero). Toda regra e medida declara `classe` (`hard`, `semantic`, `style`)
e seção de origem; número sem fonte externa leva `a_calibrar: true`, e a carga
recusa o que faltar.

| Arquivo | Conteúdo | `a_calibrar` |
|---|---|---|
| `paletas.yaml` | 4 paletas copiadas da API do Lospec (`<id>.json`, 2026-11-25): Endesga 32 (`mestra`, 10 rampas), Sweetie 16 (5 rampas), PICO-8 e DawnBringer 16 (sem rampas). Rampas são curadoria, conferidas do escuro ao claro pela luminância. | Não há números; as rampas são escolha, não medida. |
| `luz.yaml` | `padrao: de cima e da esquerda` e duas regras de estilo (luz e sombra; sombra principal com o vizinho imediato da rampa). | Sem números. |
| `proporcoes.yaml` | Formas `humanoid` e `prop`; medidas por tamanho de corpo (`tamanhos`) e por quadro maior (`quadros`); regras de silhueta. | Ver abaixo. |
| `silhuetas/humanoid_32x32.yaml` | Manequim de frente, 5 camadas com nome (pernas, tronco, braco_dir, braco_esq, cabeca), 8 chaves. Só chega ao Claude com `molde=true`. | Segue `proporcoes.yaml`. |
| `silhuetas/prop_32x32.yaml` | Caixa em 3/4 (topo, frente, detalhe), 7 chaves. | — |
| `referencias.yaml` | Lista de pacotes ativos, a faixa de porte e os mínimos por parte. | `faixa_altura` = 0.2, `minimo_de_quadros` = 3, `minimo_por_pacote` = 30, `minimo_de_pacotes` = 2. |

Valores `a_calibrar` em `proporcoes.yaml`:

- **humanóide 16×16:** altura_px 14, cabeca_px 6, tronco_px 4, pernas_px 4, tons_por_material 2, chao_y 14 (com fonte Pixnote: cabecas 2 a 3, olho 1×1, braco_px 1).
- **humanóide 32×32:** altura_px 28, cabeca_px 10, tronco_px 8, pernas_px 10, cabecas 2.8, folga_topo_px 2, largura_cabeca_px 12, largura_tronco_px 12, largura_braco_px 5, largura_perna_px 5, vao_braco_px 1, tons_por_material 3, chao_y 30 (com fonte Pixnote: olho 2×2).
- **humanóide, quadro 48×48:** corpo 32×32, chao_y 46.
- **objeto 16×16 e 32×32:** margem_px 1, ocupacao_min 0.5, tons_por_material 2 e 3, chao_y 14 e 30.
- **regra marcada:** "arma e escudo fora do corpo, com vão de 1 px, mudando o contorno".

Observação honesta: 2.8 cabeças está **abaixo** da faixa 3 a 4 do Pixnote; foi
escolha do projeto, para sobrar 2 px de folga acima da cabeça.

---

## 8. Referências

### Pacotes importados (todos CC0-1.0, coleção principal)

Importados na máquina local em `backend/data/referencias/` (fora do git). Os
arquivos originais são de terceiros e não estão no repositório.

| Pacote | Autor | Página | Quadros únicos | Por tipo (corpo) | Repetidos |
|---|---|---|---|---|---|
| `customizable-character-pack` | Ordinary Bumblebee | ordinary-bumblebee.itch.io/customizable-character-pack | 400 | character/humanoid 400 | 200 |
| `pixel-character-base-64` | Retraissance | retraissance.itch.io/pixel-character-base-animations-64x64 | 65 | character/humanoid 65 (quadros de 64×128) | 4 |
| `dungeontileset-ii` | 0x72 | 0x72.itch.io/dungeontileset-ii | 339 | character/humanoid 90, character 172, prop 35, tile 42 | 10 |
| `kings-and-pigs` | Pixel Frog | pixelfrog-assets.itch.io/kings-and-pigs | 282 | character/humanoid 40, character 111, prop 17, tile 114 | 25 |
| `ninja-adventure` | pixel-boy | pixel-boy.itch.io/ninja-adventure-asset-pack | 5.311 | character/humanoid 2.156, character 392, prop 121, tile 2.642 | 974 |
| `pixel-adventure` | Pixel Frog | pixelfrog-assets.itch.io/pixel-adventure-1 | 316 | character/humanoid 92, prop 82, tile 142 | 212 |
| `sunny-land` | ansimuz | ansimuz.itch.io/sunny-land-pixel-game-art | 210 | character/humanoid 34, character/quadruped 11, character/avian 4, prop 40, tile 121 | 15 |
| `hylsy-64-character` | Hylsy | hylsy.itch.io/64x64-pixel-art-character1 | 12 | character/humanoid 12 | 0 |
| `ninja-animated` | Morgan McGuire (morgan3d) e DezrasDragons | opengameart.org/content/ninja-animated-0 | 78 | character/humanoid 78 | 1 |
| `super-sprite-boy` | Chris_M_The_Game_Dude. | opengameart.org/content/super-sprite-boy-sprite-sheet-30-frames-32x32-64x64 | 30 | character/humanoid 30 | 0 |

O Ninja Adventure foi importado com `--excluir "**/Faceset.png" --excluir
"**/SpriteInHand.png"`: 86 PNG ficaram de fora (66 retratos de monstros e 20
sprites de arma "na mão"). A Retraissance foi importada com `--quadro 64x128`;
a altura mediana do conteúdo é 60 px.

**Segunda leva (2026-11-25).** Antes de importar, cada zip e cada imagem foi
aberto e o tamanho do quadro saiu dos arquivos, não do nome do pacote (o erro
da Retraissance): escala, níveis de alfa, cores, grade candidata testada contra
desenho cortado e a folha vista ampliada com a grade por cima. A tabela
completa, com o que entrou e o que ficou de fora de cada pacote, está em
[REFERENCIAS_FONTES.md](REFERENCIAS_FONTES.md) §6. Em resumo:

| Pacote | Quadro | Corpo (mediana de altura) | Entrou | Ficou de fora |
|---|---|---|---|---|
| `pixel-adventure` | 32×32 personagens e frutas, 64×64 checkpoints, 16×16 terreno | 25 px | 4 personagens (humanoides), frutas, caixas, checkpoints, terreno | efeitos, fundos, menu, armadilhas, imagens de divulgação |
| `sunny-land` | 33×32 Foxy, 36×28 gambá, 40×41 águia, 35×32 sapo, tileset 16×16 | Foxy 22 px; gambá e sapo 21; águia 28,5 | Foxy (humanoide), gambá e sapo (quadrúpedes), águia (ave), itens, props, tileset | atlas e folhas repetidas, casas e árvores, fundos, efeitos |
| `hylsy-64-character` | 64×64 | 63 px | `Character.png` (12 quadros) | `Hurt1–3` (mesmas poses com sangue), `HurtDead`, `.piskel` |
| `ninja-animated` | 32×32 | 15 px | a folha inteira (78 quadros) | — |
| `super-sprite-boy` | 32×32 | 31 px | `32x32 Improved hair.png` (30 quadros) | as folhas 64×64 (a 32×32 ampliada 2×) e a 32×32 normal (~5 px de diferença por quadro) |

Baixados e **não importados**: Character Prototype Animated (não é pixel art:
boneco vetorial de 150 a 254 px numa tela de 512×512, com alfa suavizado) e
Pixel Boy 32x64 (pintura com textura, 240 a 483 cores por quadro). Yakuza Enemy
e Enemy Biker: indisponíveis na página.

Lista de ativos em `config/pixel_knowledge/referencias.yaml`:
`customizable-character-pack`, `pixel-character-base-64`, `dungeontileset-ii`,
`kings-and-pigs`, `ninja-adventure`, `pixel-adventure`, `sunny-land`,
`hylsy-64-character`, `ninja-animated`, `super-sprite-boy`.

### Relatório de calibração, na íntegra

Saída de `python -m assetflow.referencias calibrar` (o arquivo fica em
`data/referencias/calibracao.md`, fora do git), com os dez pacotes, o mínimo
por pacote (30), o mínimo de pacotes por parte (2) e o validador calibrado:

```markdown
# Calibração pelas referências

Gerado por `python -m assetflow.referencias calibrar`. **Só propõe**: nenhum YAML
foi alterado. Medidas de conteúdo incluem chapéu, penacho e arma.

## Pacotes

- `customizable-character-pack` — Ordinary Bumblebee, CC0-1.0, 400 quadros
- `pixel-character-base-64` — Retraissance, CC0-1.0, 65 quadros
- `dungeontileset-ii` — 0x72, CC0-1.0, 339 quadros
- `kings-and-pigs` — Pixel Frog, CC0-1.0, 282 quadros
- `ninja-adventure` — pixel-boy, CC0-1.0, 5311 quadros
- `pixel-adventure` — Pixel Frog, CC0-1.0, 316 quadros
- `sunny-land` — ansimuz, CC0-1.0, 210 quadros
- `hylsy-64-character` — Hylsy, CC0-1.0, 12 quadros
- `ninja-animated` — Morgan McGuire (morgan3d) e DezrasDragons, CC0-1.0, 78 quadros
- `super-sprite-boy` — Chris_M_The_Game_Dude., CC0-1.0, 30 quadros

## humanóide 16x16

2985 quadros de estilo; 2210 de porte parecido (12–16 px de altura).

- estilo: fora por amostra pequena (menos de 30 quadros na parte): `hylsy-64-character` (12).

- porte: fora por amostra pequena (menos de 30 quadros na parte): `dungeontileset-ii` (9).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 14 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 6 | — | — | não medida: exige separar a cabeça |
| tronco_px | 4 | — | — | não medida: exige separar o tronco |
| pernas_px | 4 | — | — | não medida: exige separar as pernas |
| cabecas | 2 a 3 | — | — | não medida: exige separar a cabeça |
| olho_px | 1×1 | — | — | não medida: exige achar o olho |
| braco_px | 1 | — | — | não medida: exige separar o braço |
| tons_por_material | 2 | 2–3–4 (n=2985, 9 pac.) | 3 | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 14 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 7–10–11 (n=2210, 2 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## humanóide 32x32

2985 quadros de estilo; 515 de porte parecido (23–33 px de altura).

- estilo: fora por amostra pequena (menos de 30 quadros na parte): `hylsy-64-character` (12).

- porte: fora por amostra pequena (menos de 30 quadros na parte): `kings-and-pigs` (26), `sunny-land` (12), `dungeontileset-ii` (2), `ninja-animated` (2), `pixel-character-base-64` (1).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 28 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 10 | — | — | não medida: exige separar a cabeça |
| tronco_px | 8 | — | — | não medida: exige separar o tronco |
| pernas_px | 10 | — | — | não medida: exige separar as pernas |
| cabecas | 2,8 | — | — | não medida: exige separar a cabeça |
| folga_topo_px | 2 | — | — | não comparável: depende do quadro |
| largura_cabeca_px | 12 | — | — | não medida: exige separar a cabeça |
| largura_tronco_px | 12 | — | — | não medida: exige separar o tronco; o conteúdo do mesmo porte tem largura de ~23 px (com braços, arma e pose) |
| largura_braco_px | 5 | — | — | não medida: exige separar o braço |
| largura_perna_px | 5 | — | — | não medida: exige separar a perna |
| vao_braco_px | 1 | — | — | não medida: exige separar o braço |
| olho_px | 2×2 | — | — | não medida: exige achar o olho |
| tons_por_material | 3 | 2–3–4 (n=2985, 9 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 30 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 7–11–24 (n=515, 3 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## humanóide 48x48 (corpo 32x32)

2985 quadros de estilo; 515 de porte parecido (23–33 px de altura).

- estilo: fora por amostra pequena (menos de 30 quadros na parte): `hylsy-64-character` (12).

- porte: fora por amostra pequena (menos de 30 quadros na parte): `kings-and-pigs` (26), `sunny-land` (12), `dungeontileset-ii` (2), `ninja-animated` (2), `pixel-character-base-64` (1).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 28 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 10 | — | — | não medida: exige separar a cabeça |
| tronco_px | 8 | — | — | não medida: exige separar o tronco |
| pernas_px | 10 | — | — | não medida: exige separar as pernas |
| cabecas | 2,8 | — | — | não medida: exige separar a cabeça |
| folga_topo_px | 2 | — | — | não comparável: depende do quadro |
| largura_cabeca_px | 12 | — | — | não medida: exige separar a cabeça |
| largura_tronco_px | 12 | — | — | não medida: exige separar o tronco; o conteúdo do mesmo porte tem largura de ~23 px (com braços, arma e pose) |
| largura_braco_px | 5 | — | — | não medida: exige separar o braço |
| largura_perna_px | 5 | — | — | não medida: exige separar a perna |
| vao_braco_px | 1 | — | — | não medida: exige separar o braço |
| olho_px | 2×2 | — | — | não medida: exige achar o olho |
| tons_por_material | 3 | 2–3–4 (n=2985, 9 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 46 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 7–11–24 (n=515, 3 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## objeto 16x16

278 quadros de estilo; sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`).

- estilo: fora por amostra pequena (menos de 30 quadros na parte): `kings-and-pigs` (17).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| margem_px | 1 | — | — | não comparável: depende do quadro |
| ocupacao_min | 0,5 | — | — | não comparável: depende do quadro (ocupação é pixels ÷ área do quadro) |
| tons_por_material | 2 | 1,5–2–3 (n=278, 4 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 14 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |

## objeto 32x32

278 quadros de estilo; sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`).

- estilo: fora por amostra pequena (menos de 30 quadros na parte): `kings-and-pigs` (17).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| margem_px | 1 | — | — | não comparável: depende do quadro |
| ocupacao_min | 0,5 | — | — | não comparável: depende do quadro (ocupação é pixels ÷ área do quadro) |
| tons_por_material | 3 | 1,5–2–3 (n=278, 4 pac.) | 2 | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 30 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |

## O validador atual sobre as referências

Cada quadro validado no próprio tamanho, sem limite de paleta, com os limiares de
`config/quality.yaml`. Até 300 quadros por pacote, espaçados por igual.
Avisos: blocos pequenos (`PX-WARN-MICROCLUSTER`) e cor rara (`PX-WARN-PALETTE-RARE`);
p90: percentil 90 da fração de blocos pequenos e da contagem de cores raras.

| pacote | quadros | nota (mediana) | aviso de blocos pequenos | aviso de cor rara | blocos pequenos p90 | cores raras p90 |
|---|---|---|---|---|---|---|
| `customizable-character-pack` | 300 | 100 | 0% | 1% | 0,714 | 3 |
| `pixel-character-base-64` | 65 | 81 | 0% | 0% | 0,666 | 1 |
| `dungeontileset-ii` | 300 | 98 | 1% | 0% | 0,688 | 0 |
| `kings-and-pigs` | 282 | 80 | 6% | 2% | 0,831 | 1 |
| `ninja-adventure` | 300 | 100 | 0% | 0% | 0,591 | 1 |
| `pixel-adventure` | 300 | 96 | 1% | 0% | 0,579 | 1 |
| `sunny-land` | 210 | 100 | 0% | 0% | 0,5 | 0 |
| `hylsy-64-character` | 12 | 90 | 0% | 0% | 0,34 | 0 |
| `ninja-animated` | 78 | 92 | 0% | 0% | 0,632 | 2 |
| `super-sprite-boy` | 30 | 87 | 0% | 0% | 0,345 | 0 |

Proposta pela regra de `quality.yaml`: p90 do pacote mais alto, arredondado para cima, para nenhum pacote receber o aviso em mais de 10% dos quadros. Só propõe: o arquivo não foi alterado.

| limiar | configurado (aviso / desconto) | proposta | pacote mais alto (p90) |
|---|---|---|---|
| blocos pequenos (fração) | 0,84 / 0,84 | 0,84 | `kings-and-pigs` (0,831) |
| cores raras (quantas) | 3 / 3 | 3 | `customizable-character-pack` (3) |
```

Das propostas para `proporcoes.yaml`, nenhuma foi aplicada. Os limiares do
validador que a última tabela propõe são os que estão em
`config/quality.yaml`: a regra foi aplicada uma vez, à mão, e o relatório
confere.

O que a calibração mudou no relatório (ainda com os cinco pacotes da primeira
leva):

- **porte do humanóide 16:** sai a `dungeontileset-ii` (9 quadros); sobra o
  Ninja, um pacote só, e a parte fica marcada insuficiente;
- **porte do humanóide 32 e do 48:** saem `kings-and-pigs` (26, todos do King
  Human), `dungeontileset-ii` (2) e `pixel-character-base-64` (1); sobra o
  corpo-base do Customizable (6–7–8 cores, largura de conteúdo ~16 px em vez
  de ~19), insuficiente;
- **objeto:** sai `kings-and-pigs` (17) do estilo; ficam 156 quadros de 2
  pacotes, os tons por grupo de matiz passam de 1,5–2–3 para 1,5–2–2, e as
  propostas de `tons_por_material` não mudam ("(manter)" no 16×16, 2 no 32×32);
- **validador:** medianas 100 / 81 / 98 / 80 / 100, avisos de blocos pequenos
  em 0% a 6% dos quadros (antes 89% a 100%), e a amostra passa a ser espaçada
  pelo pacote (antes, os 300 primeiros quadros: o Ninja dava mediana 78 com
  eles e 86 com todos).

O que a segunda leva mudou (de 5 para 10 pacotes; nenhum valor da base nem
limiar foi alterado):

- **porte do humanóide 16 volta:** 2.210 quadros de 2 pacotes, Ninja
  Adventure (2.156) e Ninja [Animated] (54); a DungeonTileset (9) segue fora.
  Cores por quadro 7–10–11 (antes 6–7–9, de 1 pacote, insuficiente);
- **porte do humanóide 32 e do 48 volta:** 515 quadros de 3 pacotes,
  Customizable (400), Pixel Adventure (85) e Super Sprite Boy (30); ficam fora
  Kings and Pigs (26), SunnyLand (12), DungeonTileset (2), Ninja [Animated] (2)
  e Retraissance (1). Cores por quadro 7–11–24 — o p75 de 24 vem do Super
  Sprite Boy, que tem 23 a 25 cores por quadro —, largura de conteúdo ~23 px
  (antes ~16, só o corpo-base) e, na linha, largura 0,81× a altura;
- **estilo humanoide:** 2.985 quadros de 9 pacotes (o Hylsy, com 12, fica
  fora); o contorno escuro único cai de 75% para 58% dos quadros (peso igual);
  os tons por grupo de matiz seguem 2–3–4 e as propostas não mudam;
- **objeto:** 278 quadros de 4 pacotes (entram Pixel Adventure e SunnyLand;
  Kings and Pigs, com 17, segue fora); tons 1,5–2–3; propostas iguais;
- **validador:** os novos têm mediana 96, 100, 90, 92 e 87 na amostra, aviso
  de blocos pequenos em 0% a 1% e de cor rara em 0%. **A regra do p90 continua
  propondo 0,84 e 3 cores raras** — os pacotes mais altos seguem Kings and
  Pigs (0,831) e Customizable (3); entre os novos, o maior p90 é o do Ninja
  [Animated] (0,632 e 2). Os limiares configurados valem com os 10 pacotes.

## 9. Validador: como a nota é calculada

Código: `assetflow/pixel/validation/scoring.py` (`QualityScorer`), os
analisadores em `pixel/validation/analyzers/` e, para blocos pequenos e cores
raras, a calibração em `pixel/validation/calibration.py`, lida de
`config/quality.yaml` (validador 1.2.0).

- **Separação dura.** `pixel_exact` sai dos checks obrigatórios (dimensão,
  alpha binário, limite de paleta, paleta travada, não vazio). A nota de
  qualidade é outra coisa e nunca compensa uma falha dura. **A calibração não
  toca nenhum hard check**; um teste confere que validador calibrado e do
  plano dão o mesmo `pixel_exact` e os mesmos checks com dimensão, paleta e
  alpha errados.
- **A nota** começa em 100 e desconta; o resultado é `floor(100 − soma)`, entre
  0 e 100. Cada indicador tem franquia, taxa e teto:

| Penalidade | Métrica | Franquia | Taxa | Teto | Aviso | Onde mora |
|---|---|---|---|---|---|---|
| `orphan` | fração de pixels sem vizinho da mesma cor | 1% | 400 por unidade | 20 | > 2% | código |
| `microcluster` | fração de blocos de cor (8-conectados) com 1 a 3 px | **84%** (plano: 20%) | 100 por unidade | 20 | **> 84%** (plano: > 25%) | `quality.yaml` |
| `occupancy` | ocupação fora da faixa do profile | dentro da faixa | proporcional ao desvio | 15 | fora da faixa | código e profile |
| `redundancy` | pares de cores quase iguais | — | 2 por par | 10 | qualquer par | código |
| `outline` | fragmentação do contorno | 0,20 | 50 por unidade | 10 | > 0,15 | código |
| `rare_colors` | cores que pintam ≤ max(1, 0,2% do foreground) px | **3 cores** (plano: nenhuma) | 1 por cor além da franquia | 5 | **> 3 cores** (plano: qualquer) | `quality.yaml` |

- **De onde vieram os números.** Regra escrita no `quality.yaml`: o limiar é o
  p90 do pacote mais alto, arredondado para cima, para nenhum pacote receber o
  aviso em mais de 10% dos quadros. Blocos pequenos: p90 por pacote 0,71
  (Customizable) · 0,67 (Retraissance) · 0,69 (DungeonTileset) · **0,831
  (Kings and Pigs)** · 0,57 (Ninja) → 0,84. Cores raras por quadro: **3** · 1 ·
  0 · 1 · 1 → 3. Aviso e desconto começam no mesmo ponto. Taxa, teto e a
  definição de cor rara continuam os do plano, agora no arquivo. Todo número
  ali tem `a_calibrar: true`; um número sem ele (nem `fonte`) é recusado e
  fica o do plano.
- **Uma régua só.** O `bootstrap` monta um validador com essa calibração e o
  entrega ao pipeline Pixel, ao laço do Optimizer (para "otimizar não pode
  piorar" comparar a mesma nota) e à rota de dev; o `calibrar` monta o seu
  com o mesmo arquivo. O relatório de cada job grava qual calibração valeu em
  `quality.calibration`. Sem `quality.yaml`, valem os números do plano e o boot
  avisa.
- **Aceite:** aprovado quando Pixel Exact e nota ≥ `quality_threshold` do
  profile (70 em todos). Não mudou.

### Notas dos pacotes, antes e depois

Todos os quadros (6.397 da primeira leva e 646 da segunda), cada um no próprio
tamanho, sem limite de paleta, validados pelo código com e sem a calibração (o
`calibrar` usa amostra de até 300 por pacote):

| Pacote | Quadros | Nota mediana | Abaixo de 70 | Aviso de blocos pequenos | Aviso de cor rara | O que ainda desconta (média) |
|---|---|---|---|---|---|---|
| `customizable-character-pack` | 400 | 78 → 100 | 0% → 0% | 93% → 0% | 54% → 1% | órfãos 0,4 · redundância 0,5 |
| `pixel-character-base-64` | 65 | **60 → 81** | 97% → 0% | 100% → 0% | 80% → 0% | **órfãos 17,3** |
| `dungeontileset-ii` | 339 | 79 → 98 | 17% → 0% | 90% → 1% | 6% → 0% | órfãos 4,4 |
| `kings-and-pigs` | 282 | **60 → 80** | 87% → 2% | 98% → 6% | 31% → 2% | **órfãos 16,9** · redundância 0,5 |
| `ninja-adventure` | 5.311 | 86 → 100 | 5% → 0% | 61% → 0% | 11% → 0% | órfãos 1,9 |
| `pixel-adventure` | 316 | 77 → 96 | 12% → 0% | 78% → 1% | 19% → 0% | órfãos 4,4 |
| `sunny-land` | 210 | 90 → 100 | 3% → 0% | 61% → 0% | 7% → 0% | órfãos 1,4 · redundância 0,1 |
| `hylsy-64-character` | 12 | 79,5 → 90 | 8% → 0% | 92% → 0% | 0% → 0% | **redundância 10** · órfãos 0,1 |
| `ninja-animated` | 78 | 71,5 → 92 | 42% → 0% | 100% → 0% | 58% → 0% | órfãos 8,5 · redundância 0,5 |
| `super-sprite-boy` | 30 | 76 → 87 | 10% → 0% | 100% → 0% | 3% → 0% | **redundância 10** · órfãos 2,8 |

Na segunda leva aparece um terceiro desconto que sobra: **redundância** (pares
de cores a menos de 12 de distância RGB) leva o teto de 10 pontos no Hylsy e no
Super Sprite Boy. Também não foi calibrado (seção 12, item 17).

### Notas dos assets do projeto, antes e depois

PNG gravado de cada asset (na máquina local), revalidado com o spec do próprio
job: com o validador do plano, a nota bate com a gravada em todos; com a
calibração, Pixel Exact continua ✓ em todos e nenhum aviso sobra.

| Asset | O que é | Profile | Antes | Depois | O que sobrou | Blocos pequenos | Cores raras |
|---|---|---|---|---|---|---|---|
| `asset_fdb06fda2c81` | poção vermelha 16×16 | pixel_prop_64 | 81 | **100** | — | 37,5% | 1 (`#b98252`) |
| `asset_d702cf4d9e6e` | poção verde 16×16 (remendo) | pixel_prop_64 | 81 | 100 | — | 37,5% | 1 |
| `asset_5909a26ccc62` | cavaleiro 32×32, sem base de conhecimento | pixel_character_32 | 79 | 99 | órfãos 0,42 | 44,2% | 0 |
| `asset_ec17965925c0` | cavaleiro 32×32, molde no recorte | pixel_character_32 | 80 | 100 | — | 41,3% | 0 |
| `asset_94101aa383a2` | cavaleiro 32×32, só medidas | pixel_character_32 | 82 | 100 | — | 37,3% | 0 |
| `asset_15607e958c4f` | cavaleiro, corpo 32 em 48×48 | pixel_character_32 ² | 84 | **100** | — | 35,2% | 0 |
| `asset_de58819be438` | mago, corpo 32 em 48×48 | pixel_character_48 | 83 | **99** | órfãos 0,1 | 36% | 0 |
| `asset_27efd3c9d65c` | molde humanóide v1 (manequim) | pixel_character_32 | 100 | 100 | — | 15,8% | 0 |
| `asset_c9caff9aed5d` | molde humanóide v2 | pixel_character_32 | 100 | 100 | — | 9,5% | 0 |
| `asset_f7b0cdb92d08` | molde de objeto (caixa) | pixel_prop_64 | 99 | 100 | — | 18,2% | 1 (`#c0cbdc`) |

² Desenhado com o texto "48x48" e o perfil padrão, porque o servidor MCP em
execução não conhecia `pixel_character_48` (seção 12, item 5). Redesenhado
com a mesma receita e o perfil `pixel_character_48` depois da calibração:
`asset_7b32cac39b80`, 100/100 (seção 6).

### O que a nota diz agora

**Os desenhos da desenhista passaram a ficar em 99–100, e a nota só detecta
ruído.** Blocos pequenos só avisam acima de 84% (ruído aleatório de 16 cores dá
98%); um gradiente suave reduzido e quantizado, o defeito que a métrica nasceu
para pegar, dá 36% a 51% — abaixo das referências — e passa. A nota deixou de
empurrar o desenho para a simplificação, mas também não distingue um desenho
bom de um mediano. Fica assim até a Fase 5 trazer medidas que distinguem
qualidade (doubles, jaggies, banding, pillow shading, rampa reta, buracos
internos).

O que mais desconta nas referências agora são os **órfãos** (pixel sem vizinho
da mesma cor): 17 pontos na Retraissance e no Kings and Pigs, com fração
mediana de 5,5% e 6,8% contra franquia de 1%. Não foi calibrado aqui; é
pendência da Fase 5 (seção 12).

## 10. Testes e lint

`pytest -q`: **1642 passando, 1 pulado** (1.643 coletados), cerca de 120 s.

O pulado: `tests/contract/test_engine_contract.py:282`, "gaveta declara que não
suporta seed" — o teste de reprodutibilidade por seed não se aplica à
`desenhista-v1` (`supports.seed: false`). `tests/test_mcp_servidor.py` roda
quando o extra `mcp` está instalado; sem ele, é pulado inteiro.

| Arquivo | Testes |
|---|---|
| test_architecture_boundaries.py | 736 (parametrizado por arquivo) |
| pixel/test_engine_agnostic.py | 132 |
| test_desenhista.py | 63 |
| test_pixel_knowledge.py | 57 |
| test_mcp.py | 50 |
| test_referencias.py | 30 |
| test_asset_taxonomy.py | 29 |
| test_body_type_and_style.py | 28 |
| test_resolved_spec.py | 27 |
| contract/test_engine_contract.py | 25 |
| test_pedidos_mcp.py | 24 |
| test_pixel_optimizer.py | 21 |
| pixel/test_quality_calibration.py, pixel/test_pixel_profiles_config.py | 19 cada |
| test_pedidos_fila.py, test_api.py | 18 cada |
| pixel/test_stages_geometry.py | 17 |
| test_gerador_unico.py, pixel/test_stages_color.py | 16 cada |
| test_pedidos_api.py, test_engine_selection.py, pixel/test_quality.py | 15 cada |
| test_job_system.py | 13 |
| test_registry.py, test_prompt_preview.py, test_kernel.py, pixel/test_dev_api.py | 11 cada |
| test_resolver.py, test_mcp_servidor.py, pixel/test_validator.py | 10 cada |
| test_pixel_pipeline.py | 9 |
| test_llm_pixel_reviewer.py | 8 |
| test_engine_persistence.py, test_capabilities.py, pixel/test_golden.py | 7 cada |
| test_settings.py, test_historico_antigo.py | 6 cada |
| test_taxonomia_flexoes.py | 5 |
| test_third_party_engine.py | 4 |
| test_engine_swap.py | 3 |
| test_pedidos_processos.py | 2 (dois processos Python sobre o mesmo SQLite) |

A suíte usa as gavetas de referência (mocks), no ambiente de testes
(`AppEnvironment.TEST`) e com o roteamento dos testes (`ROTEAMENTO_DE_TESTE`,
no `conftest`); testes que precisam da desenhista a habilitam pelo nome. O
`test_gerador_unico.py` monta o app sem essas fixtures, como ele roda. Os testes de referências usam só imagens
geradas no próprio teste. Os testes da ilha Pixel usam o validador do plano
(`PixelValidator()` sem calibração), de propósito: fixam o mecanismo; os de
`test_quality_calibration.py` fixam o efeito de `quality.yaml`.

`ruff check .` (sem config própria, regras padrão): **144 achados**. Até a
Fase A do plano do app eram 154; os 10 que sumiram estavam em arquivos
apagados. Nenhum código novo acrescentou achado (a Fase B também não).

```text
33 UP037 quoted-annotation        30 RUF022 unsorted-dunder-all     20 BLE001 blind-except
16 I001  unsorted-imports         16 UP035 deprecated-import          4 TRY004 type-check-without-type-error
 4 UP041 timeout-error-alias       3 RUF100 unused-noqa               2 B017 assert-raises-exception
 2 F401  unused-import             2 RET501 unnecessary-return-none   2 RUF046 unnecessary-cast-to-int
 1 B008, B010, ISC004, PYI034, PYI045, RUF023, RUF059, S112, SIM102, UP017 (1 cada)
                                                                     Found 144 errors.
```

---

## 11. Desvios do plano

| Onde | O plano dizia | O que foi feito | Por quê |
|---|---|---|---|
| Fase 1 | Reusar o `PixelCanvas` e as ferramentas do Optimizer. | Rasterizador próprio dentro da gaveta. | O teste de fronteiras proíbe gaveta importar `assetflow.pixel`; o próprio plano previa essa saída. |
| Fase 1 | Saída ampliada por múltiplo inteiro até o tamanho de render. | Saída na grade lógica 1:1 (`exact_resolution`). | 512 não é múltiplo de 48; ampliar só para o Pixel Exact reduzir de volta não acrescentava nada. |
| Fase 1 | Paleta "pelo nome ou lista de cores" na receita. | Só lista de cores; os nomes ficam na base de conhecimento e chegam ao Claude no recorte. | Conhecimento mora na estante, não na gaveta. |
| Fase 3 | `luz.yaml` só na Fase 4. | Criado na Fase 3, só com a direção padrão e regras. | Pedido da autora: luz e paleta-mestra lidas da configuração por um ponto único (`estilo()`), para uma futura fase de estilos. |
| Fase 3 | Molde-base no recorte. | Molde só com `molde=true`; o padrão traz medidas, faixas e nomes de camadas. | Entregue sempre, o molde engessava o desenho no corpo do manequim. |
| Fase 3 | Proporções por tamanho de grade. | Separação corpo × quadro (`tamanhos` e `quadros`), profile `pixel_character_48`. | O corpo de 32 não cabia com arma e escudo num quadro de 32; a saída escolhida foi o quadro maior. |
| Fase 3 | — | Regras novas (sombra, equipamento, vão condicionado à roupa). | Lições de desenhos reais; ver a linha do tempo. |
| Trilha | Calibrar com exemplos reais quando chegasse a hora. | Biblioteca de referências adiantada antes da Fase 4. | Pedido da autora, para calibrar com dados antes de estilos e validação. |
| Processo | Desenhar pelo servidor MCP. | Depois da Fase 3, a consulta (e o desenho do mago) rodou por script no mesmo `ServicoDesenhista`. | O servidor MCP da sessão não foi reconectado e seguia com o código anterior. |
| Fase 5 | Calibrar o validador na Fase 5, com limiares em `pixel_knowledge/validacao.yaml`. | Blocos pequenos e cor rara calibrados antes da Fase 5, em `config/quality.yaml`. Órfãos ficam para a Fase 5. | Pedido da autora. O arquivo fica fora de `pixel_knowledge/` porque vale para todo pipeline Pixel, não só para o MCP. |
| Fases 4 a 7 | — | Não começadas. | — |
| App, Fase A | Apagar `generation/prompting/`, depois de conferir. | Mantido; saem só os três builders Studio. | O pipeline Pixel monta o prompt semântico em todo job, inclusive os do MCP; o histórico e a pré-visualização da tela o usam. |
| App, Fase A | Tirar o fallback para mock nas rotas do `capabilities.yaml`. | Três travas: mocks registrados só em `AppEnvironment.TEST`; rotas Pixel só com a desenhista e `allow_unlisted_engines: false`; fallback desligado. | Só as rotas não bastavam: `allow_unlisted_engines: true` e o registro em development punham o mock na cadeia. "Mocks só nos testes" estava em "Muda de papel" e entrou já na A. |
| App, Fase A | Studio: pipeline, pós-processamento e profiles. | Também os prompt builders Studio, o profile e o pipeline `raw_image` e a saída `studio.character` do serviço. `AssetMode.STUDIO` e as capacidades 2D ficam no contrato. | Peças do mesmo modo que o plano não citava; o contrato fica para não mexer em manifestos e testes de mecanismo. |
| App, Fase A | `SessionHistory` sai da tela (seção 3). | Fica até a galeria da Fase C. | Não estava na seção 4. |
| App, Fase B | "A fila de pedidos se apoia em jobs, fila e worker." | Fila em SQLite (`data/pedidos/`); o sistema de jobs só executa o desenho, no MCP. | API e MCP são dois processos, cada um com a fila de jobs em memória. |
| App, Fase B | "Em desenho" e "desenhar com pedido_id conclui". | Reserva por `pedidos_pendentes` (etapa "na vez do Claude"); só aprovado conclui, com 3 tentativas; "devolver à fila". | O desenho leva segundos; o tempo longo é a receita. Não aprovado precisava de destino. |
| App, Fase B | Pedidos de ajuste na fila. | API e MCP aceitam ajuste; o campo da tela fica para a Fase C. | O campo "pedir ajuste" é da Fase C. |
| App, Fase B | — | Liberdade criativa e direção de arte (pedido da autora durante a fase). | Muda o recorte, nunca o spec. |
| App, Fase A | — | Leitor do histórico tolerante a campos antigos (`GenerationRecord.do_historico`). | A conferência pedida antes de apagar campos achou 18 de 91 registros, da era do STRATEGY, sumindo em silêncio para `ver_asset` e `desenhar(base=...)`. |

---

## 12. Pendências e riscos

Em ordem de gravidade. São as coisas que eu olharia primeiro.

1. ~~Peso igual por pacote com amostra desigual~~ — **resolvido**. Pacote
   com menos de 30 quadros numa parte sai dela (`minimo_por_pacote`), e a
   parte com menos de 2 pacotes some da linha e do `ver_referencia`
   (`minimo_de_pacotes`); o `calibrar` a mostra como insuficiente. Ficou
   uma limitação: quadros medem mal o que importa, que é personagens
   distintos — os 26 quadros do Kings and Pigs no porte do humanóide 32 eram
   todos do King Human (item 19).
2. ~~Pacote medido com a grade errada~~ — **resolvido**. A Retraissance tem
   quadros de 64×128 e tinha sido importada com 64×64 (comando meu, a partir
   do nome do pacote): os 121 "quadros" eram metades de personagem e caíam na
   faixa de porte. Reimportada com `--quadro 64x128`: 65 quadros inteiros,
   altura mediana 60 px, e só 1 deles na faixa de 23–33.
3. ~~Retratos entraram como personagem~~ — **resolvido**. A descrição
   anterior estava incompleta: o padrão `*/Actor/Monster/**` trazia 66
   `Faceset.png` (e não 20; 20 eram só os que tiveram a moldura escura tomada
   por fundo), e os 20 `SpriteInHand.png` vinham do padrão de itens. O
   importador ganhou `--excluir PADRAO` (gravado no manifesto e respeitado
   também por `medir`), e o Ninja foi reimportado sem esses 86 arquivos.
4. ~~O validador pune detalhe legítimo~~ — **resolvido para blocos pequenos e
   cor rara** (seção 9): limiares em `config/quality.yaml`, referências com
   mediana 80 a 100, desenhos da desenhista com 99–100. Os requisitos duros
   não mudaram. O que sobra está nos itens 17 e 18.
5. ~~O caminho MCP por um cliente Claude Code real~~ — **resolvido**. A
   arqueira (`asset_c7fab4e5d482`) foi desenhada pelo servidor MCP da sessão
   do Claude Code, e a conferência da Fase A também rodou por ele, depois de
   reconectá-lo pelo `/mcp`.
6. **Constantes do medidor estão no código, sem `a_calibrar`.** Limiares de
   contorno (0,7 / 0,6 / 0,4), margem de "mais escuro" (0,02), neutro
   (saturação 0,15, brilho 0,12), salto de matiz (30°), fundo sólido (30%) e
   tetos de importação. Contraria a regra "número sem fonte vai para config
   com `a_calibrar`".
7. **Medidas de referência que medem outra coisa.** "Tons por grupo de matiz"
   não é "tons por material"; "altura" é altura do conteúdo (com arma e
   chapéu); tiles opacos têm "contorno" na borda do quadro, o que não
   significa nada. As propostas do relatório herdam essas limitações (por
   exemplo, propor 3 tons para o humanóide 16×16 vem de pacotes de todos os
   tamanhos).
8. **Fatiamento por linhas transparentes** junta sprites que se tocam e separa
   peças soltas (uma espada destacada). Pacotes sem grade informada dependem
   disso.
9. **Decisões de gosto tomadas rápido:** as rampas por material, os dois
   moldes, 2,8 cabeças (abaixo da fonte), larguras do humanóide, a faixa de
   porte de 20%, quais personagens da DungeonTileset contam como humanoides, o
   Foxy (raposa bípede) como humanoide e o sapo do SunnyLand como quadrúpede.
   Todas marcadas ou explicadas, mas nenhuma foi validada além dos poucos
   desenhos feitos.
10. **A desenhista conta cor por chave.** Moldes limitados a 8 chaves; um olho
   com brilho seria a 9ª. Um desenho que reusa o mesmo hexadecimal em duas
   chaves "gasta" duas cores.
11. **Textos de orientação no código.** Frases do recorte (rótulos de medidas,
    "para arma, escudo, crista e animação", a instrução do molde) estão em
    `recorte.py`, não em YAML.
12. **Teto do recorte em caracteres**, com estimativa de tokens sem tokenizador
    oficial (~3 caracteres por token). O recorte atual tem 2.260 caracteres
    de conhecimento e cabe no teto de 4.000.
13. ~~`.env` fora do `.gitignore`~~ — **resolvido**: `.env` e `.env.*` estão
    ignorados, e `.env.example` (sem segredo) continua versionado.
14. **Busca de asset por varredura do histórico.** `remendo`, `ver_asset` e a
    criação de ajuste leem o `generations.jsonl` inteiro
    (`list(limit=1_000_000)`); fica lento com histórico grande. A lista de
    pedidos não varre: lê o `asset.json` do job de cada pedido.
15. ~~Interface sem gerar~~ — **resolvido na Fase B**: "Gerar" cria um pedido
    na fila. O campo `engine` continua no `POST /api/generation/jobs`, que a
    tela não usa mais (diagnóstico).
16. **Configuração lida uma vez.** Base de conhecimento, referências e
    `quality.yaml` carregam no boot: mudar YAML ou a lista de ativos exige
    reiniciar o backend e reconectar o MCP (`/mcp`). Nada avisa que o
    processo está desatualizado.
17. **Calibração de órfãos — pendência da Fase 5.** É o maior desconto que
    sobra nas referências: 17 pontos na Retraissance e no Kings and Pigs
    (fração mediana 5,5% e 6,8%; franquia de 1%, teto 20). Contorno,
    ocupação e redundância também continuam com os números do plano, no
    código; a redundância tira o teto de 10 pontos do Hylsy e do Super
    Sprite Boy.
18. **A nota ficou em 99–100 para os desenhos da desenhista e só detecta
    ruído**, até a Fase 5 trazer medidas que distinguem qualidade. Ela não
    pune mais detalhe, mas também não separa um desenho bom de um mediano;
    o laudo continua útil para os requisitos duros e para ruído.
19. **Faltam pacotes de personagens vestidos, de proporção realista, com corpo
    de 32 a 48 px.** A segunda leva devolveu o porte do humanóide 32 e 48 (3
    pacotes) e do 16 (2), mas o de 32 vem do corpo-base sem roupa do
    Customizable e de personagens cabeçudos e fantasiados (Pixel Adventure,
    Super Sprite Boy): a largura na linha subiu de 0,57× para 0,81× a altura,
    e as cores vão de 7 a 24. O Super Sprite Boy entra com 30 quadros,
    exatamente o mínimo: com um a menos, o porte cairia para 2 pacotes. Os
    dois candidatos de 50 px (Enemy Biker e Yakuza Enemy, de Rancic) estão
    indisponíveis, e o Pixel Boy (53 px) não foi importado.

20. ~~A mensagem da desenhista sem receita~~ — **resolvido na Fase B**: diz
    que um pedido da tela vai para a fila e o Claude o desenha pela conversa.
21. ~~Textos que ficaram fora do escopo da Fase A~~ — **resolvido na Fase B**
    (`optimizer.yaml`, `pixel_profiles.yaml`, `GeneratorHero`).
22. **Restos de contrato do modo automático.** `ResolvedEngine.reason` fica
    sempre vazio, e o campo `dev_only` do manifesto mantém o nome com o
    significado novo ("só nos testes").
23. **O leitor do histórico ainda pula em silêncio** a linha que falhar por
    outro motivo (JSON quebrado, tipo errado). Os 91 registros locais são
    lidos hoje; a troca por índice ou SQLite da Fase C é a hora de tornar isso
    visível.
24. **A tela da Fase B não foi vista num navegador nesta sessão.** Typecheck e
    build passam, e a API que ela usa tem testes (inclusive o marco, com API
    e MCP em dois containers); o layout e o andamento ao vivo pedem a
    conferência do passo a passo do marco.
25. **Fila em três arquivos.** Para ser rápida no Windows com conexão curta,
    a fila mantém o `-wal` entre conexões: `pedidos.sqlite3`, `-wal` e `-shm`
    ficam juntos em `data/pedidos/`, e uma cópia de segurança leva os três.
26. **`consultar_pedido` avulso é fiel por padrão**, e os pedidos da tela,
    equilibrados. É de propósito (sem o parâmetro, o comportamento de antes),
    mas a mesma frase pode receber orientações diferentes pelos dois caminhos.

---

## 13. O que não está no GitHub

Só existe na máquina local:

- **`backend/data/`** inteiro (ignorado): os assets gerados citados aqui, os
  relatórios de validação, o histórico `history/generations.jsonl`, os cinco
  pacotes em `data/referencias/` (10 pacotes, ~13 MB, arte de terceiros) com seus
  `manifesto.yaml` e `medidas.json`, e o `calibracao.md` (refeito depois da
  calibração; transcrito na seção 8).
- **Os downloads originais** dos pacotes (uma pasta `Downloads\refs` do
  usuário, com os zips e um `LICENCAS.md` com a data e o texto de licença de
  cada página), inclusive os dois da segunda leva que não foram importados.
- **`.mcp.json`** na raiz (ignorado): o registro do servidor MCP com o caminho
  do Python da venv.
- **`backend/.venv`** e o extra `mcp` instalado.
- **A configuração do Claude Code** da sessão (servidor MCP conectado; ele lê
  código e YAML ao subir, e é reconectado pelo `/mcp` depois de cada mudança).
- **Arquivos temporários** usados para conferir desenhos e importações
  (receitas de rascunho, prévias, cópia isolada de importação).

As receitas dos desenhos citados ficam gravadas no histórico local (campo
`engine_options`), não no repositório; a do cavaleiro de 48 está transcrita na
seção 5.


## Sessão de lotes (2026-11-25): decisões e dúvidas

A autora pediu para seguir sem esperar "sim" entre lotes, registrando aqui o
que foi decidido sem consulta e o que ficou em dúvida. Cada lote tem o seu
documento em `backend/docs/`.

Em 2026-11-26 ela acrescentou ao fim da lista, no mesmo ritmo, os lotes 9
(cópia de segurança), 10 (`iniciar.bat`), 11 (aviso de servidor
desatualizado), 12 (painel de custo) e 13 (estudo dos 30 melhores sprites
CC0). A lista inteira está no CLAUDE.md, "Sessão de lotes".

### Lote 1 — banca e conceito ([BANCA_E_CONCEITO.md](BANCA_E_CONCEITO.md))

Decisões:

1. O conceito escolhido vira a direção de arte como texto, depois da direção
   escrita na criação; também fica estruturado, para a pergunta do olhar.
2. Ajuste (remendo de um asset) é sempre sem conceito.
3. A página da banca cria a rodada com "sem conceito" por padrão (a primeira
   rodada de referência que a autora pediu); a segunda, "o Claude escolhe".
4. Nota por imagem (duas por par), escolha por par.
5. Par com lado sem desenho (falhou, cancelado) conta como derrota desse lado.
6. A fila da tela mostra os projetos `principal` e `banca`; "Prontos", só o
   `principal`.

Dúvidas para a autora:

1. **A rodada da banca é desenhada pela mesma conversa que vê a fila.** O
   plano pede conversa nova; nada no servidor garante.
2. **"Serve para qualquer personagem do mesmo tipo"** não é conferido por
   código — só a diferença entre os três e contra os recusados.
3. **O custo registrado é por caracteres**; o raciocínio do Claude, que na etapa
   de conceito pode ser grande, não aparece.

### Lote F2 — cor e luz ([LOTE_F2_COR_E_LUZ.md](LOTE_F2_COR_E_LUZ.md))

Decisões: chaves de rampa de um caractere; a luz vem da receita (a gaveta não
lê a base); efeitos agem sobre o que a camada já pintou, antes do espelho, e são
recusados em camada espelhada; ligado por padrão.

Dúvidas: os números de intensidade e de contraste por material são `a
calibrar`; o desvio de matiz vai para 240° e 60° fixos.

### Lote F3 — construção ([LOTE_F3_CONSTRUCAO.md](LOTE_F3_CONSTRUCAO.md))

Decisões: o boneco vira camadas antes do parse (os comandos de sempre o
desenham); proporções do boneco são convenção minha, `a calibrar`; só
humanoide; `vao` poupa a raiz do membro.

Dúvidas: medir na banca se o boneco iguala os personagens; quatro poses fixas.

### Lote F5 — ficha de verificação ([LOTE_F5_FICHA.md](LOTE_F5_FICHA.md))

Decisões: `verificacao` numa string `tipo:alvo`; resposta livre lida pelo
começo ("sim"/"não"); a ficha mora no `mcp/` e a rota só lê o arquivo; só as
regras da forma do pedido e as de luz; a ficha aparece no resultado (a tela não
tem página de detalhe do asset); a linha `autora` é relida a cada leitura; a
obrigação do campo não tem interruptor (só a ficha tem).

Dúvidas: nove das dez regras de hoje são `olhar` — as medidas e construções
chegam com as regras dos lotes F1, F4 e 8; a revisão independente na banca não
entrou (a conversa nova não é distinguível); o cruzamento cobre só `valores` e
`limpeza`.

### Lote 5 — editor de pixels ([LOTE_5_EDITOR.md](LOTE_5_EDITOR.md))

Decisões: só pedido pronto abre no editor; a edição é sempre uma camada nova
(`retoque_N`), com um `px` sobre o retângulo do que mudou; o resultado aprovado
vira um ajuste já concluído (um `INSERT`), e o não aprovado não entra na fila;
a paleta vem da gaveta (`engine_metadata.paleta`), com a da receita para assets
antigos; "ficou" com tolerância de 8 por canal; o motivo vai para o asset
original; a requisição de ajuste é montada pelo `ServicoDePedidos`
(`requisicao_de_ajuste`), a mesma do pedido de ajuste da fila.

Dúvidas: o Optimizer pode desfazer um pixel isolado da autora (a tela avisa
quantos ficaram; respeitar a edição mexeria numa regra da arquitetura); editar
pedido que falhou ficou de fora; a ficha do asset editado sai vazia. **O editor
não foi usado no navegador nesta sessão**: os testes cobrem o backend e a rota,
e a tela só passou no `tsc` e no build.

### Lote F1 — linha e contorno ([LOTE_F1_LINHA.md](LOTE_F1_LINHA.md))

Decisões: a reta ajusta o fim, não o degrau; a curva passa pelos pontos; o
ápice de uma curva recomeça a progressão; o contorno é a borda de dentro e
repinta traços finos na borda; limites por tipo (character, prop, tile), p90
dos pacotes; limpeza e medida em dois códigos com a mesma regra, conferidos
por teste. Correção do F5: as perguntas `limpeza` eram negativas e a ficha
as contaria ao contrário.

Dúvidas: os pacotes profissionais têm canto em L (mediana 2,2 por 100 px nos
personagens), então a regra do §4 não é absoluta e o olho só acusa acima do
p90 — a poção de exemplo da gaveta passa a receber o desvio; contorno seletivo
e colorido sem medida contra as referências; o degrau 2, 1, 2, 1 conta como
irregular.

Nota do commit: o `0ede490` levou também `backend/docs/SUGESTOES_DE_MELHORIA.md`,
que a autora pôs na pasta durante a sessão (lista de ideias, sem nada
sensível), porque a pasta foi adicionada inteira. Dali em diante os arquivos
entram pelo nome.

### Lote F4 — detalhes e acabamento ([LOTE_F4_ACABAMENTO.md](LOTE_F4_ACABAMENTO.md))

Decisões: tamanhos do rosto por altura de cabeça (convenção minha a partir do
§9); `reflexo` e `traco` no lugar de `brilho` e `linha`, que já são comandos;
recusa de acabamento vira aviso; suavizar a partir de 32 px e pontilhar a
partir de 48; mão e pé como carimbos fixos; o formato dos opcionais uma vez por
conversa (ia inteiro em toda consulta, ~800 tokens com os quatro grupos).

Dúvidas: os carimbos de mão aberta; rosto de perfil sem nariz nem queixo; o
pontilhado não confere o contraste entre as duas cores. Achado: contar a
janela xadrez solta como pontilhado acusaria 2.392 de 3.469 personagens
profissionais de até 32 px; a medida conta só manchas de 4 janelas (67 acusam).

### Lote 8 — base por temas ([LOTE_8_BASE.md](LOTE_8_BASE.md))

Decisões: um arquivo por tema, com o leitor de regra de sempre; o recorte não
leva a linha dos temas por padrão (por pedido, numa lista de dez, passava o
teto), e ela vai depois do recorte na consulta e uma vez no topo da lista; só
técnica e processo do §17; material gravado sem uso; as regras de tema entram
na ficha.

Dúvidas: sete regras são de gosto (`autora`); não há como saber, sem a banca,
se o Claude vai pedir `consultar_base`; o §7 virou dois temas.

### Lote 9 — cópia de segurança ([LOTE_9_BACKUP.md](LOTE_9_BACKUP.md))

Decisões: o `-wal` e o `-shm` não vão soltos — a cópia do SQLite os incorpora
num arquivo consistente (levá-los soltos exigiria parar quem escreve); pasta
padrão no perfil do usuário; restaurar só pelo comando, com ensaio por padrão;
referências entram por padrão.

Dúvidas: cópia automática agendada não entrou; cópias antigas não são
apagadas (~21 MB cada).

### Lote 10 — um clique para abrir ([LOTE_10_INICIAR.md](LOTE_10_INICIAR.md))

Decisões: o `.bat` é fino e chama um Python testável; reaproveita o que já
está rodando; a porta da tela é escolhida pelo lançador, com `--strictPort`.
Achado: a tela da autora escutava só em `[::1]:5173` — o `localhost` do Windows
é IPv6 —, então o lançador procura nos dois endereços.

Dúvidas: o servidor MCP não sobe pelo lançador (é do Claude Code); atalho com
ícone não entrou.
