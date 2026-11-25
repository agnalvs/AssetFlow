# Plano de melhoria do AssetFlow — desenhista via MCP

Nov 25, 2026 · @Luiza

## 1. Objetivo

O AssetFlow deixa de depender de modelos de difusão e passa a receber o desenho do Claude por um servidor MCP, usando a assinatura que você já tem. O app faz o acabamento, a limpeza e a validação, para gastar o mínimo de tokens.

**O que muda**

- O "motor" passa a ser uma gaveta desenhista, que transforma uma receita curta (formas, linhas de pixels, paleta pelo nome) em sprite na grade lógica.
- A geração começa na conversa com o Claude, não no botão da tela.
- Entra uma base de conhecimento em `config/pixel_knowledge/`, a partir do documento de práticas já escrito.
- Saem os motores de difusão, o motor pago da OpenAI e tudo que só existia para compará-los.

**O que não muda**

- A regra central: nenhum pipeline conhece tecnologia de IA. A gaveta desenhista entra pelo `manifest.json`, como qualquer outra.
- O `FinalResolvedSpec`, resolvido uma vez e nunca recalculado.
- Pixel Exact, Pixel Optimizer, validador e storage.
- Código, comentários e commits em português.

**Por que este caminho.** O `engines.yaml` registra uma GTX 1050 Ti de 4GB, em que o SDXL normal levou cerca de 86 s por passo. A saída do SDXL-Turbo não é pixel art, e reduzi-la para 32×32 destrói o desenho. A estrutura de pastas nunca foi o problema.

## 2. O que fica

Quase todo o backend continua, porque foi escrito para não depender de motor. Caminhos relativos a `backend/`.

| Parte | Caminho | Papel no novo app |
| --- | --- | --- |
| Contrato e kernel de motores | `assetflow/generation/kernel/` | Descobre e chama a gaveta desenhista |
| Spec do pedido | `assetflow/generation/spec/`, `schemas/` | Diz ao Claude tamanho, paleta, fundo e tipo |
| Taxonomia | `config/asset_taxonomy/` | Classifica o pedido |
| Pipeline Pixel | `assetflow/generation/pipelines/pixel/` | Orquestra motor, pós-processamento e validação |
| Pixel Exact | `assetflow/pixel/` | Garante grade, paleta e alpha |
| Pixel Optimizer | `assetflow/pixel/optimizer/` | Limpeza; o `canvas.py` e as `tools/` viram a base do desenhista |
| Validador e política de aceite | `assetflow/pixel/validation/`, `acceptance/` | Laudo devolvido ao Claude |
| Jobs e storage | `assetflow/jobs/`, `assetflow/storage/` | Fila, histórico e arquivos |
| API e frontend | `assetflow/api/`, `frontend/` | Galeria, spec e resultado |
| Gavetas de referência | `engines/mock_image/`, `engines/mock_pixel_alt/` | A suíte de testes inteira roda sobre elas |
| Revisor por modelo | `assetflow/llm/` | Opcional; pequeno e já testado |
| Testes de fronteira e de contrato | `tests/test_architecture_boundaries.py`, `tests/contract/` | Testam a gaveta nova sem escrever teste novo |

**Atenção às gavetas de referência.** `tests/conftest.py` fixa `REFERENCE_ENGINES = {"mock-image-v1", "mock-pixel-alt-v1"}`, e mais de dez arquivos de teste dependem delas. Não apagar.

## 3. O que apagar

A limpeza remove cinco gavetas, o benchmark entre motores e os arquivos de apoio deles. A lista foi conferida no commit `be3e9aa` do repositório. Caminhos relativos a `backend/`.

### Apagar por inteiro

| Caminho | Motivo |
| --- | --- |
| `assetflow/generation/engines/diffusers_sdxl/` | Difusão; não roda bem na sua placa |
| `assetflow/generation/engines/flux_pixel/` | Difusão; exige GPU maior |
| `assetflow/generation/engines/sdpixl/` | Depende de projeto externo; horas por imagem |
| `assetflow/generation/engines/pixel_forge/` | Depende de binário externo; só o `sdpixl` usa o `bridge.py` dele |
| `assetflow/generation/engines/gpt_image/` | API paga por imagem |
| `assetflow/generation/benchmark/` | Comparava motores; sobra um só |
| `scripts/benchmark_engines.py` | Idem |
| `config/benchmark_suite.yaml` | Idem |
| `scripts/use-local-cache.ps1` | Cache de modelos do HuggingFace |
| `tests/test_diffusers_engine.py` | Testa gaveta removida |
| `tests/test_gpt_image_engine.py` | Testa gaveta removida |
| `tests/test_process_bridges.py` | Testa as pontes do Pixel Forge e do SD-πXL |
| `tests/test_benchmark.py` | Testa o benchmark removido |

### Editar, não apagar

| Arquivo | O que tirar |
| --- | --- |
| `config/engines.yaml` | Os cinco ids da `allowlist` e os blocos de configuração deles |
| `config/engine_policy.yaml` | As regras que preferem motores removidos; deixar uma regra geral apontando para a gaveta desenhista |
| `config/capabilities.yaml` | Referências aos motores removidos |
| `pyproject.toml` | O extra `diffusers` (torch, diffusers, transformers, accelerate, safetensors, peft) |
| `.env.example` | Variáveis dos motores removidos |
| `tests/test_api.py`, `test_engine_selection.py`, `test_registry.py`, `test_settings.py` | Casos que citam ids removidos |
| `assetflow/settings.py`, `kernel/resolver.py`, `kernel/auto_policy.py`, `kernel/catalog.py` | Menções a ids removidos (em geral em comentários e exemplos) |
| `SETUP.md` | As seções de torch, CUDA e download de modelo |
| `CLAUDE.md`, `docs/ENGINES.md`, `docs/ARCHITECTURE.md`, `README.md` do backend | Lista de motores, comandos de benchmark, contagem de testes e de achados do ruff |

### Decisão sua: o modo 2D Normal (Studio)

O novo app é só de pixel art, então o modo Studio não ajuda. Ele envolve `pipelines/studio/`, `postprocessing/studio/`, profiles, o seletor de modo do frontend e testes.

- **Manter por agora** (recomendado): a limpeza fica pequena e segura. Nenhum motor real atende o Studio depois da remoção, então ele fica dormente.
- **Apagar também**: o app fica mais enxuto, mas a mudança toca frontend, schemas e muitos testes de uma vez.

O plano segue com "manter por agora". Apagar o Studio pode virar uma fase própria depois que o desenhista funcionar.

### Fora do repositório, na sua máquina

- **Cache de modelos em `backend/data/`**: vários GB do SDXL. Dá para liberar, mas só a subpasta do cache. `backend/data/` também guarda assets gerados e histórico, e o `CLAUDE.md` proíbe apagar a pasta inteira.
- **Pacotes na venv**: desinstalar torch, diffusers e afins libera mais alguns GB.

### Cuidados

- A limpeza vai num branch e num commit só dela, antes de qualquer código novo. Assim dá para desfazer com um comando, além da sua cópia em zip.
- `pytest -q` antes e depois. O número de testes cai; nenhum pode falhar.
- `tests/test_third_party_engine.py` fica: ele testa a descoberta de gavetas externas, que o desenhista usa.
- O teste de fronteiras continua proibindo `torch`, `openai` e afins fora das gavetas. Não afrouxar.

## 4. O que construir

São sete fases, e as três primeiras já entregam um sprite 32×32 de ponta a ponta. Cada fase termina com os testes passando e um commit próprio.

### Fase 0: limpeza

Executar a seção 3, num branch `desenhista-mcp`.

### Fase 1: gaveta desenhista

Nova gaveta em `assetflow/generation/engines/desenhista/`, id `desenhista-v1`, família `agentic` (já prevista em `schemas/engine.py`).

- **Entrada**: a receita do desenho chega nas opções do motor dentro do pedido. O `ImageGenerationRequest` já tem `options_for(engine_id)` para isso.
- **Receita em camadas**: paleta (pelo nome ou lista de cores), formas (retângulo, elipse, linha, polígono, preenchimento) e trechos de pixels compactados por linha para os detalhes.
- **Saída**: imagem na grade lógica, ampliada por múltiplo inteiro e vizinho mais próximo até o tamanho pedido. Assim a redução por blocos do Pixel Exact não perde nada.
- **Reuso**: desenhar com o `PixelCanvas` e as ferramentas de `pixel/optimizer/tools/`. Se o teste de fronteiras impedir a gaveta de importar da ilha Pixel, o rasterizador fica dentro da própria gaveta.
- **Sem receita no pedido**: falhar com mensagem em português dizendo que este motor só atende pelo MCP.
- **Testes**: o contrato de gavetas cobre o básico sozinho. Acrescentar testes do rasterizador com receitas pequenas e resultado conhecido.

### Fase 2: servidor MCP

Módulo `assetflow/mcp/`, com o SDK Python oficial do MCP como dependência opcional, rodando por stdio.

| Ferramenta | Recebe | Devolve |
| --- | --- | --- |
| `consultar_pedido` | O texto do pedido | O `FinalResolvedSpec` resumido e o recorte de conhecimento |
| `desenhar` | O texto do pedido e a receita | Laudo em texto, id do asset, caminho do arquivo |
| `ver_asset` | Id do asset | A imagem ampliada, só quando o Claude pedir |

- `desenhar` faz tudo numa chamada: resolve o spec, cria o job com `engine: desenhista-v1`, espera o pipeline e monta o laudo.
- Correção como remendo: `desenhar` aceita `base: <id>` com as camadas alteradas, sem reenviar a receita inteira.
- Descrições das ferramentas curtas, porque ocupam contexto em toda conversa.
- O servidor chama o `GenerationService` direto, sem passar por HTTP, e usa o mesmo `bootstrap`.
- O comando para registrar o servidor no Claude Code deve ser conferido na documentação atual e gravado no `SETUP.md`.

### Fase 3: base de conhecimento mínima

Pasta `config/pixel_knowledge/`, lida no boot como a taxonomia. Para começar:

- `paletas.yaml` com três ou quatro paletas nomeadas e rampas por material.
- `proporcoes.yaml` para humanóide e prop em 16×16 e 32×32.
- Um molde-base de humanóide 32×32 e um de prop 32×32.
- Um seletor que monta o recorte a partir de `context.resolved`, sem recalcular nenhum campo do spec.

Diretório ausente não quebra o boot: o recorte volta vazio.

**Marco**: pedir "cavaleiro 32x32, 8 cores, sem fundo" na conversa e receber um PNG aprovado pelo Pixel Exact.

### Fase 4: acabamento automático

Estágios novos na ilha Pixel, antes do Optimizer, ligados por campos do spec:

- Espelhamento para simetria.
- Contorno automático (`preto`, `colorido`, `seletivo`, `nenhum`).
- Sombreamento por volume a partir de `luz.direcao`.
- Variantes sem Claude: troca de rampa por material, espelho, troca de paleta.

### Fase 5: validações de estilo

Novos analisadores em `pixel/validation/`, com limiares em `pixel_knowledge/validacao.yaml`: doubles, jaggies, banding, pillow shading, rampa reta, cores quase iguais, buracos internos. Classe `style`: geram aviso e nota, não reprovação.

### Fase 6: animação

- Modelo de animação: lista de frames com `duracao_ms` e `modo_loop`.
- A receita descreve o frame-base e, para os demais, só as diferenças.
- `animacoes.yaml` com espera e caminhada.
- Exportador de spritesheet PNG com JSON, e GIF de prévia.
- Validações entre frames: canvas, paleta, linha de chão, volume.

### Fase 7: tiles e efeitos

- Tiles com teste de emenda 3×3 e conjunto de transição por grade dupla (16 peças).
- Efeitos procedurais simples: faísca, poeira, anel de impacto.

As fases 4 a 7 seguem o documento "Base de conhecimento de pixel art e animação", seções 4 a 17.

### Trilha paralela: melhoria da base de conhecimento

A base de conhecimento não termina na fase 3. Ela cresce a cada fase e é o que mais pesa na qualidade do desenho, sem custo de tokens. A fonte é o documento [Base de conhecimento de pixel art e animação](https://claude.ai/artifact/2zDPN2QmGZmCW5UF5sN4G5), que deve ser copiado para `backend/docs/PIXEL_KNOWLEDGE.md` para o Claude Code poder lê-lo.

**Arquivos, na ordem em que entram**

| Fase | Arquivo em `config/pixel_knowledge/` | Seção do documento |
| --- | --- | --- |
| 3 | `paletas.yaml`, `proporcoes.yaml`, `silhuetas/` | 2, 3, 5, 9 |
| 4 | `contorno.yaml`, `luz.yaml`, `props.yaml` | 4, 6, 10 |
| 5 | `validacao.yaml` | 17 |
| 6 | `animacoes.yaml` | 13, 14, 16 |
| 7 | `tiles.yaml`, `projecoes.yaml`, `efeitos.yaml` | 11, 12, 15 |

**Como ela melhora com o uso**

1. **Calibrar com exemplos reais.** Rodar o validador sobre 20 a 30 sprites de pacotes livres de boa qualidade e ajustar os limiares de `validacao.yaml` até eles passarem.
2. **Registrar o que você aprova e reprova.** Cada asset guarda a receita e a sua decisão. Receitas aprovadas viram candidatas a molde-base.
3. **Promover moldes.** Um sprite aprovado pode ser salvo como silhueta-base de um novo tipo (por exemplo, quadrúpede 32×32) com um comando, sem editar YAML à mão.
4. **Anotar correções repetidas.** Se o Claude erra a mesma coisa várias vezes (braço grosso, olho alto demais), a correção entra como regra em `proporcoes.yaml`, e não como pedido repetido na conversa.
5. **Preencher as lacunas apontadas.** A seção 19 do documento lista o que ficou fraco: quadrúpedes, voadores, isométrico, efeitos, valores exatos de paletas e exportação. Cada lacuna vira uma pesquisa curta antes da fase que a usa.

**Regras da trilha**

- Conhecimento é configuração: acrescentar uma paleta ou um molde é editar YAML, nunca um `.py`.
- Todo arquivo tem teste de carga e de formato, como a taxonomia.
- Cada regra declara a classe (`hard`, `semantic`, `style`) e, quando o número não tem fonte, o marcador `a_calibrar: true`.
- O recorte entregue ao Claude tem teto de tamanho, para a base poder crescer sem aumentar o gasto por pedido.

## 5. Critérios de pronto e cuidados

Uma fase só está pronta quando os quatro itens abaixo valem.

1. `pytest -q` sem falhas.
2. `ruff check .` sem achados novos em relação ao baseline, com o número atualizado no `CLAUDE.md` se ele mudar.
3. `tests/test_architecture_boundaries.py` passando sem ter sido afrouxado.
4. Documentação da fase atualizada (`CLAUDE.md`, `docs/`).

### Regras que o plano não pode quebrar

- **Nenhum `if engine ==`** fora do kernel. O pipeline pede uma capacidade; o desenhista é só mais uma gaveta.
- **O spec não é recalculado.** A base de conhecimento lê `context.resolved` e só acrescenta orientação.
- **Motor escolhido é motor usado.** O MCP pede `desenhista-v1` de forma explícita, sem fallback para os mocks.
- **Nada é corrigido em silêncio.** Receita inválida vira erro em português, que o Claude lê e corrige.
- **Otimizar não pode piorar.** O acabamento novo entra antes do Optimizer e passa pela mesma comparação de nota.
- **Credencial nunca no YAML.** O novo caminho não usa chave nenhuma.

### Riscos conhecidos

| Risco | Como aparece | O que fazer |
| --- | --- | --- |
| Desenho esquemático | Sprite correto na técnica, sem graça | Moldes-base melhores; ciclo de revisão com `ver_asset` |
| Gasto de cota da assinatura | Muitas rodadas de correção | Laudo em texto, remendos, variantes sem Claude |
| Limpeza quebra teste distante | Falha em arquivo que citava um id removido | Rodar a suíte logo após a fase 0, antes de código novo |
| `ASSETFLOW_APP_ENV=production` | Mocks somem e só resta o desenhista | Comportamento esperado; documentar |
| Botão "Gerar" da tela | Com o desenhista selecionado, falha por falta de receita | Mensagem clara na tela; decidir depois se o botão some |

### Fora deste plano

Contas de usuário, projetos, editor e exportação para motores de jogo, que estão no `README.md` do produto. Como o uso é só seu, nada disso é necessário agora.

## 6. Instrução pronta para o Claude Code

Copie este plano para `backend/docs/PLANO_DESENHISTA_MCP.md` e o documento de práticas para `backend/docs/PIXEL_KNOWLEDGE.md`. Depois cole o texto abaixo no Claude Code, dentro da pasta do projeto.

```text
Leia CLAUDE.md, backend/docs/PLANO_DESENHISTA_MCP.md e
backend/docs/PIXEL_KNOWLEDGE.md antes de qualquer alteração.

Execute SOMENTE a Fase 0 (limpeza) do plano, assim:

1. Crie o branch desenhista-mcp a partir do main.
2. Rode pytest -q em backend/ e anote o resultado.
3. Mostre a lista exata de pastas e arquivos que vai apagar e dos que vai
   editar, conforme a seção 3 do plano, e ESPERE minha confirmação.
4. Depois do meu "sim", apague e edite. Não apague nada fora da lista.
   Não toque em backend/data/, nas gavetas mock_image e mock_pixel_alt,
   nem no modo Studio.
5. Rode pytest -q e ruff check . de novo. Corrija o que quebrou por causa
   da limpeza, sem afrouxar tests/test_architecture_boundaries.py.
6. Atualize CLAUDE.md, SETUP.md e backend/docs/ com a nova lista de
   motores, a contagem de testes e o baseline do ruff.
7. Faça um único commit em português e me mostre o resumo: o que saiu,
   quantos testes havia e quantos há agora.

Não comece a Fase 1 sem eu pedir.
```

Para as fases seguintes, o pedido é curto: "Execute a Fase N do plano, com os critérios de pronto da seção 5, e pare ao final". Na fase 3 e nas seguintes, acrescente: "crie os arquivos de `config/pixel_knowledge/` da trilha de base de conhecimento previstos para esta fase, a partir do `PIXEL_KNOWLEDGE.md`".

**Liberar espaço no seu PC**, depois da fase 0, em pedido separado: "identifique a subpasta de cache de modelos dentro de `backend/data/` e os pacotes de IA instalados na venv, diga quanto ocupam e pergunte antes de apagar".
