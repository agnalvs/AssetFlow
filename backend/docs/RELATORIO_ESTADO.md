# Relatório de estado — branch `desenhista-mcp`

Data: 2026-11-25. Base: `main` em `be3e9aa`. Escrito para quem revisa pelo
GitHub, sem acesso à máquina onde o trabalho foi feito. Onde um número veio de
dado que só existe nessa máquina (assets gerados, pacotes de referência), o
texto diz isso.

Documentos que este relatório resume e que valem ler junto:
[PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md) (o plano),
[PIXEL_KNOWLEDGE.md](PIXEL_KNOWLEDGE.md) (a pesquisa que vira configuração),
[DESENHISTA.md](DESENHISTA.md) (a gaveta e a receita), [MCP.md](MCP.md)
(servidor, laudo, remendo e recorte), [REFERENCIAS.md](REFERENCIAS.md)
(biblioteca de referências) e o [CLAUDE.md](../../CLAUDE.md) da raiz.

---

## 1. Linha do tempo

Todos os commits do branch, em ordem. Cada um passou com `pytest -q` sem
falhas e com o ruff no mesmo baseline de 154 achados.

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
| (este) | Estado | Lista de ativos com os cinco pacotes importados, `PIXEL_STYLES.md`, `REFERENCIAS_FONTES.md` e este relatório. Nenhum código. | 1410 / 1 |

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
│   │                          Regra nova: gaveta sem seed não é dividida em lotes.
│   ├── engines/
│   │   ├── desenhista/ [novo] A gaveta desenhista-v1: receita.py (lê e valida), rasterizador.py
│   │   │                      (formas, px, espelho, balde -> grade), engine.py, manifest.json.
│   │   ├── mock_image/        Gaveta de referência (testes).
│   │   ├── mock_pixel_alt/    Gaveta de referência (testes, desabilitada).
│   │   └── (removidas: diffusers_sdxl, flux_pixel, gpt_image, pixel_forge, sdpixl)
│   ├── pipelines/             pixel.character (PixelCharacterPipeline) e studio (dormente).
│   ├── postprocessing/        Ponte Pixel (PixelExactProcessor) e Studio.
│   ├── prompting/, profiles/
│   └── (removido: benchmark/)
├── pixel/                     Ilha Pixel Exact: processamento, validação, Optimizer, aceite, preview.
│   ├── validation/            PixelValidator, analisadores, QualityScorer (seção 9).
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
├── storage/                   Assets, artefatos e histórico (data/history/generations.jsonl).
└── llm/                       Revisor opcional do Optimizer por modelo (não usado por padrão).
```

### `backend/config/`

```
config/
├── engines.yaml          [alterado]  Allowlist: desenhista-v1 + as duas de referência.
├── engine_policy.yaml    [alterado]  Regra geral pixel_geral prefere a desenhista no "Automático".
├── capabilities.yaml     [alterado]  Sem os motores removidos.
├── profiles.yaml         [alterado]  + pixel_character_48 (corpo de 32 em 48×48).
├── pixel_profiles.yaml   [alterado]  + pixel_character_48_strict (48×48, 12 cores, prévia 10×).
├── optimizer.yaml                    Teto de iterações, revisor, interruptor.
├── asset_taxonomy/*.yaml             Vocabulário por tipo de asset.
└── pixel_knowledge/      [novo]      Base de conhecimento (seção 7):
    ├── paletas.yaml                  Endesga 32 (mestra), Sweetie 16, PICO-8, DawnBringer 16.
    ├── luz.yaml                      Direção padrão e regras de luz e sombra.
    ├── proporcoes.yaml               Medidas por forma e tamanho; quadros maiores; regras.
    ├── referencias.yaml              Pacotes de referência ativos; faixa de porte.
    └── silhuetas/                    Moldes-base: humanoid_32x32.yaml, prop_32x32.yaml.
```

Testes novos: `test_desenhista.py`, `test_mcp.py`, `test_mcp_servidor.py`,
`test_pixel_knowledge.py`, `test_referencias.py`, e seções novas em
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

**`desenhar`** — Desenha um sprite a partir de uma receita e devolve o laudo: aprovação, nota, problemas, id do asset e caminho do PNG. Para corrigir, passe base=<id> e só o que mudou.
- `pedido` (string | null): O mesmo texto de consultar_pedido. Com base, pode omitir.
- `receita` (object | null): A receita completa; com base, só paleta e camadas alteradas.
- `base` (string | null): Id de um asset anterior, para remendo.
- `perfil` (string | null): Igual a consultar_pedido; num remendo, o da base.

**`ver_referencia`** — Mostra UMA imagem de referência dos pacotes livres ativos, do tipo de asset do pedido, ampliada. Serve para ver estilo, não para copiar; use só quando precisar ver.
- `pedido` (string, obrigatório): O mesmo texto de consultar_pedido.
- `perfil` (string | null): Igual a consultar_pedido.

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
branch e os cinco pacotes de referência ativos (cerca de 3.200 caracteres; o
recorte, a partir de `conhecimento:`, tem ~2.300):

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
referências: estilo de 2807 quadros (5 pacotes, peso igual): contorno escuro único em 75% (cor mais comum #222222) · 3 tons por grupo de matiz (mediana); porte de 23–33 px de altura, 518 quadros (4 pacotes, peso igual): 6–20 cores (mediana 11) · largura 0,79× a altura · preenchimento 63% da caixa
```

Atenção: a parte "porte" desta linha está contaminada por um erro de
importação (seção 12, item 1).

---

## 6. Laudo devolvido por `desenhar`

Exemplo real (o mesmo cavaleiro):

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
| `referencias.yaml` | Lista de pacotes ativos e a faixa de porte. | `faixa_altura` = 0.2, `minimo_de_quadros` = 3. |

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
| `pixel-character-base-64` | Retraissance | retraissance.itch.io/pixel-character-base-animations-64x64 | 121 | character/humanoid 121 ⚠ | 16 |
| `dungeontileset-ii` | 0x72 | 0x72.itch.io/dungeontileset-ii | 339 | character/humanoid 90, character 172, prop 35, tile 42 | 10 |
| `kings-and-pigs` | Pixel Frog | pixelfrog-assets.itch.io/kings-and-pigs | 282 | character/humanoid 40, character 111, prop 17, tile 114 | 25 |
| `ninja-adventure` | pixel-boy | pixel-boy.itch.io/ninja-adventure-asset-pack | 5.397 | character/humanoid 2.156, character 458, prop 141, tile 2.642 | 974 |

⚠ Medido com a grade errada (seção 12, item 1).

Lista de ativos em `config/pixel_knowledge/referencias.yaml`:
`customizable-character-pack`, `pixel-character-base-64`, `dungeontileset-ii`,
`kings-and-pigs`, `ninja-adventure`.

### Relatório de calibração, na íntegra

Saída de `python -m assetflow.referencias calibrar` (o arquivo fica em
`data/referencias/calibracao.md`, fora do git):

```markdown
# Calibração pelas referências

Gerado por `python -m assetflow.referencias calibrar`. **Só propõe**: nenhum YAML
foi alterado. Medidas de conteúdo incluem chapéu, penacho e arma.

## Pacotes

- `customizable-character-pack` — Ordinary Bumblebee, CC0-1.0, 400 quadros
- `pixel-character-base-64` — Retraissance, CC0-1.0, 121 quadros
- `dungeontileset-ii` — 0x72, CC0-1.0, 339 quadros
- `kings-and-pigs` — Pixel Frog, CC0-1.0, 282 quadros
- `ninja-adventure` — pixel-boy, CC0-1.0, 5397 quadros

## humanóide 16x16

2807 quadros de estilo; 2168 de porte parecido (12–16 px de altura).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 14 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 6 | — | — | não medida: exige separar a cabeça |
| tronco_px | 4 | — | — | não medida: exige separar o tronco |
| pernas_px | 4 | — | — | não medida: exige separar as pernas |
| cabecas | 2 a 3 | — | — | não medida: exige separar a cabeça |
| olho_px | 1×1 | — | — | não medida: exige achar o olho |
| braco_px | 1 | — | — | não medida: exige separar o braço |
| tons_por_material | 2 | 2–3–4 (n=2807, 5 pac.) | 3 | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 14 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 7–8–10 (n=2168, 3 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## humanóide 32x32

2807 quadros de estilo; 518 de porte parecido (23–33 px de altura).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 28 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 10 | — | — | não medida: exige separar a cabeça |
| tronco_px | 8 | — | — | não medida: exige separar o tronco |
| pernas_px | 10 | — | — | não medida: exige separar as pernas |
| cabecas | 2,8 | — | — | não medida: exige separar a cabeça |
| folga_topo_px | 2 | — | — | não comparável: depende do quadro |
| largura_cabeca_px | 12 | — | — | não medida: exige separar a cabeça |
| largura_tronco_px | 12 | — | — | não medida: exige separar o tronco; o conteúdo do mesmo porte tem largura de ~22 px (com braços, arma e pose) |
| largura_braco_px | 5 | — | — | não medida: exige separar o braço |
| largura_perna_px | 5 | — | — | não medida: exige separar a perna |
| vao_braco_px | 1 | — | — | não medida: exige separar o braço |
| olho_px | 2×2 | — | — | não medida: exige achar o olho |
| tons_por_material | 3 | 2–3–4 (n=2807, 5 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 30 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 6–11–20 (n=518, 4 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## humanóide 48x48 (corpo 32x32)

2807 quadros de estilo; 518 de porte parecido (23–33 px de altura).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| altura_px | 28 | — | (manter) | circular: é ela que escolhe os quadros de porte parecido; quadros de outros pacotes têm outra escala |
| cabeca_px | 10 | — | — | não medida: exige separar a cabeça |
| tronco_px | 8 | — | — | não medida: exige separar o tronco |
| pernas_px | 10 | — | — | não medida: exige separar as pernas |
| cabecas | 2,8 | — | — | não medida: exige separar a cabeça |
| folga_topo_px | 2 | — | — | não comparável: depende do quadro |
| largura_cabeca_px | 12 | — | — | não medida: exige separar a cabeça |
| largura_tronco_px | 12 | — | — | não medida: exige separar o tronco; o conteúdo do mesmo porte tem largura de ~22 px (com braços, arma e pose) |
| largura_braco_px | 5 | — | — | não medida: exige separar o braço |
| largura_perna_px | 5 | — | — | não medida: exige separar a perna |
| vao_braco_px | 1 | — | — | não medida: exige separar o braço |
| olho_px | 2×2 | — | — | não medida: exige achar o olho |
| tons_por_material | 3 | 2–3–4 (n=2807, 5 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 46 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |
| cores por quadro (informativo) | — | 6–11–20 (n=518, 4 pac.) | — | o limite vem do pedido; serve de régua para o 8 ou 12 de costume |

## objeto 16x16

193 quadros de estilo; sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| margem_px | 1 | — | — | não comparável: depende do quadro |
| ocupacao_min | 0,5 | — | — | não comparável: depende do quadro (ocupação é pixels ÷ área do quadro) |
| tons_por_material | 2 | 1,5–2–2,5 (n=193, 3 pac.) | (manter) | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 14 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |

## objeto 32x32

193 quadros de estilo; sem faixa de porte (forma sem altura ou sem `porte.faixa_altura`).

| medida | base | referências (p25–mediana–p75, n) | proposta | nota |
|---|---|---|---|---|
| margem_px | 1 | — | — | não comparável: depende do quadro |
| ocupacao_min | 0,5 | — | — | não comparável: depende do quadro (ocupação é pixels ÷ área do quadro) |
| tons_por_material | 3 | 1,5–2–2,5 (n=193, 3 pac.) | 2 | por grupo de matiz, de qualquer tamanho; material não se separa por matiz |
| chao_y | 30 | — | — | não comparável: depende do quadro, e o quadro das referências é outro |

## O validador atual sobre as referências

Cada quadro validado no próprio tamanho, sem limite de paleta. É o insumo da
calibração da Fase 5: quantas referências levariam os avisos de blocos pequenos
(`PX-WARN-MICROCLUSTER`) e de cor de 1 pixel (`PX-WARN-PALETTE-RARE`).

| pacote | quadros | nota (mediana) | blocos pequenos | cor de 1 px |
|---|---|---|---|---|
| `customizable-character-pack` | 300 | 78 | 94% | 45% |
| `pixel-character-base-64` | 121 | 60 | 100% | 61% |
| `dungeontileset-ii` | 300 | 79 | 90% | 6% |
| `kings-and-pigs` | 282 | 60 | 98% | 31% |
| `ninja-adventure` | 300 | 78 | 89% | 10% |
```

Nenhuma proposta do relatório foi aplicada.

---

## 9. Validador: como a nota é calculada hoje

Código: `assetflow/pixel/validation/scoring.py` (`QualityScorer`) e os
analisadores em `pixel/validation/analyzers/`. Os limiares **estão no código**,
não em config.

- **Separação dura.** `pixel_exact` sai dos checks obrigatórios (dimensão,
  alpha binário, limite de paleta, paleta travada, não vazio). A nota de
  qualidade é outra coisa e nunca compensa uma falha dura.
- **A nota** começa em 100 e desconta; o resultado é `floor(100 − soma)`, entre
  0 e 100. Cada indicador tem franquia, taxa e teto:

| Penalidade | Métrica | Franquia | Taxa | Teto |
|---|---|---|---|---|
| `orphan` | fração de pixels sem vizinho da mesma cor | 1% | 400 por unidade | 20 |
| `microcluster` | fração de blocos de cor (8-conectados) com 1 a 3 px | 20% | 100 por unidade | 20 |
| `occupancy` | ocupação fora da faixa do profile | dentro da faixa | proporcional ao desvio | 15 |
| `redundancy` | pares de cores quase iguais | — | 2 por par | 10 |
| `outline` | fragmentação do contorno | 0,20 | 50 por unidade | 10 |
| `rare_colors` | cores que pintam ≤ max(1, 0,2% do foreground) px | — | 1 por cor | 5 |

- **Avisos** (`PX-WARN-*`) não descontam por si; o de blocos pequenos aparece
  acima de 25% de microclusters, o de cor rara com qualquer cor rara.
- **Aceite:** aprovado quando Pixel Exact e nota ≥ `quality_threshold` do
  profile (70 em todos).

### Notas dos pacotes (validador atual)

Na tabela final do relatório de calibração acima: medianas 60 a 79; o aviso de
blocos pequenos em 89% a 100% dos quadros, o de cor de 1 px em 6% a 61%.

### Notas dos assets do projeto

Lidas dos `000_validation.json` gravados (na máquina local).

| Asset | O que é | Profile | Nota | Penalidades | Microclusters (1/2/3 px de N blocos) | Cores raras |
|---|---|---|---|---|---|---|
| `asset_fdb06fda2c81` | poção vermelha 16×16 | pixel_prop_64 | 81 | microcluster 17,5 · rare_colors 1 | 37,5% (1/1/1 de 8) | `#b98252` |
| `asset_d702cf4d9e6e` | poção verde 16×16 (remendo) | pixel_prop_64 | 81 | microcluster 17,5 · rare_colors 1 | 37,5% (1/1/1 de 8) | `#b98252` |
| `asset_5909a26ccc62` | cavaleiro 32×32, sem base de conhecimento | pixel_character_32 | 79 | orphan 0,42 · microcluster 20 | 44,2% (5/8/6 de 43) | — |
| `asset_ec17965925c0` | cavaleiro 32×32, molde no recorte | pixel_character_32 | 80 | microcluster 20 | 41,3% (3/11/5 de 46) | — |
| `asset_94101aa383a2` | cavaleiro 32×32, só medidas (aprovado pela autora) | pixel_character_32 | 82 | microcluster 17,25 | 37,3% (3/10/6 de 51) | — |
| `asset_15607e958c4f` | cavaleiro, corpo 32 em 48×48 | pixel_character_32 ² | 84 | microcluster 15,19 | 35,2% (3/10/6 de 54) | — |
| `asset_de58819be438` | mago, corpo 32 em 48×48 | pixel_character_48 | 83 | orphan 0,1 · microcluster 16 | 36% (8/5/5 de 50) | — |
| `asset_27efd3c9d65c` | molde humanóide v1 (manequim) | pixel_character_32 | 100 | — | 15,8% | — |
| `asset_c9caff9aed5d` | molde humanóide v2 | pixel_character_32 | 100 | — | 9,5% | — |
| `asset_f7b0cdb92d08` | molde de objeto (caixa) | pixel_prop_64 | 99 | rare_colors 1 | 18,2% | `#c0cbdc` |

² Desenhado com o texto "48x48" e o perfil padrão, porque o servidor MCP em
execução não conhecia `pixel_character_48` (seção 12, item 4).

Leitura: em todos os desenhos com detalhe, a penalidade de microclusters
sozinha tira 15 a 20 pontos. Os moldes, que não têm detalhe, tiram 99 e 100. A
calibração disso está pedida e ainda não foi feita.

---

## 10. Testes e lint

`pytest -q`: **1410 passando, 1 pulado** (1.411 coletados), cerca de 60 s.

O pulado: `tests/contract/test_engine_contract.py:282`, "gaveta declara que não
suporta seed" — o teste de reprodutibilidade por seed não se aplica à
`desenhista-v1` (`supports.seed: false`). `tests/test_mcp_servidor.py` roda
quando o extra `mcp` está instalado; sem ele, é pulado inteiro.

| Arquivo | Testes |
|---|---|
| test_architecture_boundaries.py | 723 (parametrizado por arquivo) |
| pixel/test_engine_agnostic.py | 130 |
| test_desenhista.py | 64 |
| test_pixel_knowledge.py | 56 |
| test_mcp.py | 46 |
| test_asset_taxonomy.py | 28 |
| test_resolved_spec.py | 27 |
| test_referencias.py | 26 |
| contract/test_engine_contract.py | 25 |
| test_engine_selection.py | 23 |
| test_pixel_optimizer.py | 21 |
| pixel/test_pixel_profiles_config.py | 20 |
| test_body_type_and_style.py | 18 |
| test_api.py | 17 |
| pixel/test_stages_geometry.py | 17 |
| pixel/test_stages_color.py | 16 |
| pixel/test_quality.py | 15 |
| test_job_system.py | 13 |
| test_prompt_preview.py | 12 |
| test_registry.py, test_pixel_pipeline.py, test_kernel.py, pixel/test_dev_api.py | 11 cada |
| test_resolver.py, pixel/test_validator.py | 10 cada |
| test_mcp_servidor.py, test_llm_pixel_reviewer.py | 8 cada |
| test_engine_persistence.py, test_capabilities.py, pixel/test_golden.py | 7 cada |
| test_settings.py | 6 |
| test_third_party_engine.py | 4 |
| test_engine_swap.py | 3 |

A suíte usa as gavetas de referência (mocks); testes que precisam da
desenhista a habilitam pelo nome. Os testes de referências usam só imagens
geradas no próprio teste.

`ruff check .` (sem config própria, regras padrão): **154 achados**, o mesmo
baseline do início do branch; o código novo não acrescentou nenhum.

```text
35 UP037 quoted-annotation        31 RUF022 unsorted-dunder-all     21 BLE001 blind-except
17 UP035 deprecated-import        16 I001  unsorted-imports          5 SIM102 collapsible-if
 4 RUF100 unused-noqa              4 TRY004 type-check-without-type-error
 4 UP041 timeout-error-alias       2 B017 assert-raises-exception    2 F401 unused-import
 2 RET501 unnecessary-return-none  2 RUF046 unnecessary-cast-to-int  1 B008, B010, ISC004,
 PYI034, PYI045, RUF023, RUF059, S112, UP017 (1 cada)                Found 154 errors.
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
| Fases 4 a 7 | — | Não começadas. A calibração do validador (parte da Fase 5) foi pedida e está em espera. | — |

---

## 12. Pendências e riscos

Em ordem de gravidade. São as coisas que eu olharia primeiro.

1. **Um pacote de referência foi medido com a grade errada.** A folha da
   Retraissance (`pixel-character-base-64`) tem quadros de **64×128**, e foi
   importada com `--quadro 64x64` (o comando que eu escrevi, a partir do nome
   do pacote). Cada personagem foi cortado na cintura: os 121 "quadros" são
   metades. Isso contamina a parte de estilo e, mais grave, a parte de **porte**
   da linha `referências:` (as metades têm ~32 px e caem na faixa 23–33 do
   humanóide 32) e o relatório de calibração. Correção: reimportar com
   `--quadro 64x128 --substituir` e rodar `calibrar` de novo. Não foi feito.
2. **Retratos entraram como personagem.** O padrão `*/Actor/Monster/**` do
   Ninja Adventure trouxe 20 `Faceset.png` (retratos) e um `SpriteInHand.png`.
   A moldura escura dos retratos foi tratada como fundo sólido. Afeta só as
   somas de "character sem corpo"; o padrão precisa excluir os `Faceset`.
3. **O validador pune detalhe legítimo.** A penalidade de microclusters tira 15
   a 20 pontos de todo desenho com detalhe, e as referências profissionais
   ficam com mediana 60 a 79. O laudo pode empurrar o desenho para a
   simplificação. A calibração (limiares em config, `a_calibrar`, sem mexer nos
   requisitos duros) está pedida e não foi implementada.
4. **O caminho MCP de ponta a ponta não foi exercitado depois da Fase 3.** O
   servidor da sessão nunca foi reconectado: `consultar_pedido` com recorte,
   `molde=true`, `ver_referencia` e `pixel_character_48` foram verificados pelo
   `ServicoDesenhista` direto e pelos testes do SDK (cliente em memória e por
   stdio), mas nunca por um cliente Claude Code real.
5. **Constantes do medidor estão no código, sem `a_calibrar`.** Limiares de
   contorno (0,7 / 0,6 / 0,4), margem de "mais escuro" (0,02), neutro
   (saturação 0,15, brilho 0,12), salto de matiz (30°), fundo sólido (30%) e
   tetos de importação. Contraria a regra "número sem fonte vai para config
   com `a_calibrar`".
6. **Medidas de referência que medem outra coisa.** "Tons por grupo de matiz"
   não é "tons por material"; "altura" é altura do conteúdo (com arma e
   chapéu); tiles opacos têm "contorno" na borda do quadro, o que não
   significa nada. As propostas do relatório herdam essas limitações (por
   exemplo, propor 3 tons para o humanóide 16×16 vem de pacotes de todos os
   tamanhos).
7. **Fatiamento por linhas transparentes** junta sprites que se tocam e separa
   peças soltas (uma espada destacada). Pacotes sem grade informada dependem
   disso.
8. **Decisões de gosto tomadas rápido:** as rampas por material, os dois
   moldes, 2,8 cabeças (abaixo da fonte), larguras do humanóide, a faixa de
   porte de 20%, quais personagens da DungeonTileset contam como humanoides.
   Todas marcadas ou explicadas, mas nenhuma foi validada além dos poucos
   desenhos feitos.
9. **A desenhista conta cor por chave.** Moldes limitados a 8 chaves; um olho
   com brilho seria a 9ª. Um desenho que reusa o mesmo hexadecimal em duas
   chaves "gasta" duas cores.
10. **Textos de orientação no código.** Frases do recorte (rótulos de medidas,
    "para arma, escudo, crista e animação", a instrução do molde) estão em
    `recorte.py`, não em YAML.
11. **Teto do recorte em caracteres**, com estimativa de tokens sem tokenizador
    oficial (~3 caracteres por token). O recorte atual tem ~2.300 caracteres
    de conhecimento e cabe no teto de 4.000.
12. **`.env` não está no `.gitignore`** (só `env/`). Hoje não existe `.env`;
    se alguém criar um, ele pode ser commitado.
13. **Busca de asset por varredura do histórico.** `remendo` e `ver_asset`
    leem o `generations.jsonl` inteiro (`list(limit=1_000_000)`); fica lento
    com histórico grande.
14. **Interface e produção.** A tela continua oferecendo "Gerar" com a
    desenhista, que falha sem receita (mensagem clara). Com
    `ASSETFLOW_APP_ENV=production` os mocks somem e só sobra a desenhista. O
    modo Studio está dormente.
15. **Configuração lida uma vez.** Base de conhecimento e referências carregam
    no boot: mudar YAML ou a lista de ativos exige reiniciar o backend e
    reconectar o MCP (`/mcp`). Nada avisa que o processo está desatualizado.

---

## 13. O que não está no GitHub

Só existe na máquina local:

- **`backend/data/`** inteiro (ignorado): os assets gerados citados aqui, os
  relatórios de validação, o histórico `history/generations.jsonl`, os cinco
  pacotes em `data/referencias/` (~12 MB, arte de terceiros) com seus
  `manifesto.yaml` e `medidas.json`, e o `calibracao.md`.
- **Os downloads originais** dos pacotes (uma pasta `Downloads\refs` do
  usuário, com os zips e um `LICENCAS.md` com a data e o texto de licença de
  cada página).
- **`.mcp.json`** na raiz (ignorado): o registro do servidor MCP com o caminho
  do Python da venv.
- **`backend/.venv`** e o extra `mcp` instalado.
- **A configuração do Claude Code** da sessão (servidor MCP conectado, ainda
  com o código anterior à Fase 3).
- **Arquivos temporários** usados para conferir desenhos e importações
  (receitas de rascunho, prévias, cópia isolada de importação).

As receitas dos desenhos citados ficam gravadas no histórico local (campo
`engine_options`), não no repositório; a do cavaleiro de 48 está transcrita na
seção 5.
