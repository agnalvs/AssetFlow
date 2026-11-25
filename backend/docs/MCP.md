# Servidor MCP — o Claude desenha pela conversa

> Plano desenhista ([PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md)),
> Fase 2. Código em `assetflow/mcp/`; testes em `tests/test_mcp.py` e
> `tests/test_mcp_servidor.py`. O formato da receita está em
> [DESENHISTA.md](DESENHISTA.md). Para registrar no Claude Code, veja o
> [SETUP.md](../../SETUP.md) §10.

O servidor expõe três ferramentas por stdio. Ele chama o `GenerationService`
direto, sem HTTP, montado pelo mesmo `bootstrap.py` da API. E pede sempre a
gaveta `desenhista-v1` **pelo nome, sem fallback**: motor escolhido é motor
usado, e um desenho que não sai falha dizendo por quê, em vez de virar a
saída de um mock.

```
assetflow/mcp/
  servico.py    o que as ferramentas fazem — não depende do SDK
  servidor.py   o protocolo (SDK `mcp`, dependência opcional)
  laudo.py      os textos que o Claude lê
  remendo.py    receita parcial sobre a receita de um asset anterior
  __main__.py   python -m assetflow.mcp
```

## 1. As ferramentas

As descrições são curtas de propósito: o Claude carrega todas em **toda**
conversa, use ele o AssetFlow ou não. `tests/test_mcp_servidor.py` põe um teto
nelas.

| Ferramenta | Recebe | Devolve |
|---|---|---|
| `consultar_pedido` | `pedido`, `perfil?`, `molde?` | o que o spec resolveu + o formato da receita + o recorte de conhecimento |
| `desenhar` | `pedido?`, `receita?`, `base?`, `perfil?` | o laudo em texto |
| `ver_asset` | `id` | uma legenda e o PNG ampliado |
| `ver_referencia` | `pedido`, `perfil?` | um quadro de referência do tipo do pedido, ampliado, com origem e licença ([REFERENCIAS.md](REFERENCIAS.md)) |

- **`perfil`** é o profile de partida, e só vale no que o texto não disser. O
  padrão é `pixel_character_32`. A lista de opções na descrição sai dos
  profiles Pixel do `profiles.yaml`, no boot.
- **O formato da receita vem na resposta de `consultar_pedido`**, e não na
  descrição de `desenhar`: assim ele só ocupa contexto quando há desenho.
- **O recorte de conhecimento** fecha a resposta de `consultar_pedido`: as
  linhas de `config/pixel_knowledge/` que valem para aquele spec (§4).
  **`molde`** (padrão `false`) troca a linha de camadas pela receita inteira
  do molde-base.
- Cada desenho é uma variação, no projeto `mcp`: os arquivos ficam em
  `backend/data/assets/projects/mcp/`.

Erros — receita inválida, perfil que não é de Pixel Art, asset que não existe —
chegam ao Claude como erro da ferramenta, com a mensagem em português que diz
o que corrigir.

## 2. O laudo

O veredito vem primeiro; depois, o que fazer com ele.

```text
NÃO APROVADO (qualidade abaixo do mínimo) · asset_722d7c77872d · fagulhas 16x16
Pixel Exact ✓ · qualidade 59/100 (mínimo 70)
grade 16×16 · 4 de 16 cores · fundo transparente
problemas:
- 48 pixels isolados (100.00% do sprite) — possível ruído de redução; confira antes de aceitar
  onde: (0,4) (2,4) (4,4) (6,4) (8,4) (10,4) (12,4) (14,4) +40
- 48 de 48 blocos de cor têm 3 pixels ou menos (100.00%) — a imagem pode não ter superfícies sólidas
- o conteúdo encosta na borda do canvas — parte do sprite pode ter ficado de fora
  onde: esquerda, direita
- o contorno está em 10 pedaços para 48 pixels (fragmentação 0.21) — a silhueta pode ter se desfeito na redução
Optimizer: nenhum reparo seguro; manteve de propósito pixels isolados ×48, contorno fragmentado ×1, encosto na borda ×1 (motivos no optimizer.json ao lado do PNG)
arquivo: D:\...\backend\data\assets\projects\mcp\jobs\job_…\000.png
```

| Primeira linha | Quando |
|---|---|
| `APROVADO` | requisitos técnicos ok e nota ≥ mínimo |
| `NÃO APROVADO (qualidade abaixo do mínimo)` | requisitos ok, nota abaixo do mínimo |
| `REPROVADO (falhou requisito técnico)` | falhou dimensão, alpha ou paleta; as falhas vêm listadas |

O laudo **lê** os relatórios que o Pixel Exact e o Optimizer já gravaram
(`validation.json`, `optimizer.json`, `engine_output.json`). Ele não mede nada
de novo e não recalcula o spec.

### Onde está cada problema

Só entra a posição que o validador expõe:

| Problema | Onde | De onde vem |
|---|---|---|
| pixels isolados | até 8 coordenadas `(x,y)`, e `+N` se houver mais | `quality.metrics.orphan_positions` e `orphan_pixel_count` |
| conteúdo na borda | os lados: cima, baixo, esquerda, direita | a caixa do conteúdo (`bounding_box`, inclusiva) e o tamanho da grade |
| contorno fragmentado | — | o validador só conta os pedaços (`count`, `fragmentation`), sem posição |

Para o contorno fragmentado entrar com lugar, o `OutlineAnalyzer`
(`pixel/validation/analyzers/outline.py`) teria de passar a expor os
componentes. O laudo não inventa uma posição que o validador não mediu.

### Avisos da receita

Operação parcialmente fora da grade é recortada pela gaveta, que grava o aviso
em `engine_metadata["avisos_receita"]`. O laudo lê de lá — e não da lista
geral de avisos do job, onde o kernel acrescenta, por exemplo, que a gaveta
ignora negative prompt.

## 3. O remendo

Uma chamada de `desenhar` com `base` e uma receita **parcial**:

```json
desenhar(base="asset_eb8d6855b548", receita={
  "paleta": {"r": "#2e8b57", "R": "#4fbf7f"},
  "camadas": [{"nome": "brilho", "ops": [{"px": ["b"], "em": [5, 7]}]}]
})
```

```text
remendo de asset_eb8d6855b548: paleta r, R; trocou camada brilho
APROVADO · asset_6a6e9074e482 · poção vermelha 16x16
...
```

1. O servidor acha a `base` no histórico (`data/history/generations.jsonl`),
   que guarda a receita completa em `engine_options`. Funciona depois de
   reiniciar o servidor.
2. A receita parcial é juntada à da base:
   - `paleta` — por chave: existente é trocada, nova entra;
   - camada com `nome` existente — trocada **no mesmo lugar**;
   - camada com `nome` novo — entra no fim;
   - `{"nome": "brilho", "remover": true}` — tira a camada;
   - `grade` — não muda; vir diferente é erro.
3. Sem `pedido`, valem o texto e o perfil da base, e o spec sai igual.
4. Sai um **asset novo**; a base fica como era. A receita gravada é a inteira,
   então dá para remendar um remendo.

No remendo, toda camada precisa de `nome`. Camadas da base sem nome são
conhecidas pelo nome que a gaveta dá a elas, `"camada N"`, congelado antes da
junção — remover a primeira não renomeia a segunda.

**Outro tamanho não é remendo.** Um `pedido` novo com `base` resolve o spec de
novo, mas as coordenadas da receita não escalam. Se a receita da base declara
`grade`, a gaveta recusa o tamanho diferente; para desenhar em outro tamanho,
mande uma receita nova.

## 4. O recorte de conhecimento

`consultar_pedido` termina com as linhas da base de conhecimento que valem
para o pedido — nunca a base inteira. Quem monta é
`assetflow/pixel_knowledge/recorte.py`, a partir de `config/pixel_knowledge/`:

| Arquivo | O que entra no recorte |
|---|---|
| `proporcoes.yaml` | faixas de y de cabeça, tronco e pernas, chão, folga acima da cabeça, larguras, onde o corpo fica no quadro, e as regras de silhueta |
| `luz.yaml` | a direção padrão, quando o pedido não define uma, e as regras de luz e sombra |
| `paletas.yaml` | o limite de cores do spec e as rampas da paleta-mestra |
| `silhuetas/*.yaml` | os nomes das camadas do molde-base; a receita inteira só com `molde=true` |

Para "cavaleiro 32x32, 8 cores, sem fundo":

```text
conhecimento:
humanóide 32×32: cabeça y3–12 (10 px) · tronco y13–20 (8 px) · pernas y21–30 (10 px) · chão y=30 (pixel opaco mais baixo) · folga y1–2 acima da cabeça, para crista, penacho ou cabelo · larguras com contorno: cabeça 12, tronco 12, braço 5, perna 5 · olho 2×2 com brilho de 1 px · 3 tons por material
quadro: corpo centrado entre x=15 e x=16, com braços em x4–27 (colunas contando o braço separado do tronco por 1 px, o que só vale com o membro à mostra); livre x1–3 e x28–30 dos lados, para arma, escudo, crista e animação
luz: de cima e da esquerda (padrão da base; o pedido não definiu) · luz do lado de onde ela vem e sombra no oposto, nunca só acompanhando o contorno · sombra principal com o vizinho imediato da rampa; o tom mais escuro só em pontos pequenos, nunca em faixa
cores: até 8, contorno incluído · paleta-mestra endesga-32, rampas do escuro ao claro; cada material usa tons vizinhos de uma rampa:
  contorno #181425
  metal #262b44 #3a4466 #5a6988 #8b9bb4 #c0cbdc #ffffff · pedra #262b44 #3a4466 #5a6988 #8b9bb4
  ...
silhueta: arma e escudo fora do corpo, com vão de 1 px, mudando o contorno · o equipamento muda o contorno do corpo (ombreiras, elmo com crista, capa), não só a cor por dentro · ...
camadas: pernas, tronco, braco_dir, braco_esq, cabeca (direita e esquerda do personagem) · a receita do molde-base vem com molde=true
```

Com `molde=true`, a última linha dá lugar à receita do molde, entre uma linha
de descrição e chaves e a instrução de uso:

```text
molde humanoid_32x32: manequim de frente, pose neutra; ...; camadas pernas, tronco, braco_dir, braco_esq, cabeca; chaves k contorno · p pele · ...
{"grade":[32,32],"paleta":{...},"camadas":[...]}
o molde é guia de medidas e de camadas, não desenho a copiar: mantenha as proporções, a linha de chão e os nomes das camadas; redesenhe pose, silhueta e detalhes para o pedido
```

### Corpo num quadro maior

A grade do spec é o **quadro**. O corpo que vive nele sai de
`proporcoes.yaml`: do mesmo tamanho (`tamanhos`) ou menor (`quadros`). Um
personagem de 32 num quadro de 48×48 — o caso do §2 do PIXEL_KNOWLEDGE.md, com
folga para arma, escudo, crista e animação — vem do bloco:

```yaml
quadros:
  "48x48":
    corpo: "32x32"
    chao_y: {valor: 46, classe: semantic, secao: "§2", a_calibrar: true}
```

As medidas do corpo não mudam: ele fica centrado na horizontal, e as faixas de
y descem junto com o chão do quadro. O seletor continua lendo só a grade do
spec; "corpo de 32" no texto não é lido — é a tabela que diz qual corpo vive
em 48×48. Para o pedido não depender de o texto dizer "48x48", o profile
`pixel_character_48` já resolve a grade em 48×48:

```text
humanóide, corpo 32×32 num quadro 48×48: cabeça y19–28 (10 px) · tronco y29–36 (8 px) · pernas y37–46 (10 px) · chão y=46 (pixel opaco mais baixo) · folga y17–18 acima da cabeça, ...
quadro: corpo centrado entre x=23 e x=24, com braços em x12–35 (colunas contando o braço separado do tronco por 1 px, o que só vale com o membro à mostra); livre x1–11 e x36–46 dos lados e y1–16 acima, para arma, escudo, crista e animação
```

Com `molde=true`, a receita do molde vem **deslocada** para o quadro (+8 em x,
+16 em y, grade 48×48), e a linha do molde diz isso. O molde da base continua
em 32×32. Acrescentar 64×64 é acrescentar um bloco em `quadros`.

A receita deixou de vir por padrão porque virava o desenho em vez de
orientá-lo: o primeiro cavaleiro com ela saiu com o corpo fino e reto do
manequim, sem ombreiras nem penacho. As medidas bastam para a consistência
entre personagens; o molde fica para quem quer partir dele.

Quatro regras:

- **O seletor só lê o spec**: `logical_resolution`, `asset.type`,
  `character.body_type`, `palette` e `style.shading.light_direction`. Paleta
  travada tira as rampas; luz do pedido ganha do padrão; corpo `unknown` fica
  sem proporções e sem camadas, em vez de virar humanoide, e o recorte diz
  isso na primeira linha: `corpo não identificado: sem medidas; informe
  humanoide, quadrúpede etc. no pedido` (`SEM_CORPO`). A dedução do corpo pela
  categoria acontece antes, no resolvedor do spec (`RESOLVED_SPEC.md`, "O
  corpo que a categoria implica"); quando é ela que responde, a linha `tipo:`
  diz `corpo humanoid (inferido da categoria)`. A linha `estilo:` da consulta
  continua dizendo o que o spec resolveu.
- **Paleta-mestra e luz vêm da configuração**, por um ponto só:
  `BaseDeConhecimento.estilo()`. O código não tem paleta nem direção próprias;
  sem `mestra` ou sem `luz.yaml`, a linha some. Uma fase futura de estilos
  troca paleta, luz, contorno e proporções juntos mudando só esse método.
- **Teto de 4.000 caracteres** (`TETO_CARACTERES`, cerca de 1.300 tokens). As
  seções entram na ordem proporções, luz, cores, silhueta, molde; a que não
  cabe sai inteira, e a última linha diz qual saiu. O cavaleiro usa ~1.800
  caracteres (~1.850 no quadro de 48), ou ~3.100 a 3.200 com `molde=true`.
- **Diretório ausente não quebra o boot**: o recorte sai vazio, e a consulta
  diz `conhecimento: (nada da base para este pedido)`. Arquivo fora do formato
  é ignorado com aviso no log e em `BaseDeConhecimento.problemas`.

A desenhista conta cor por **chave** da paleta, então os moldes têm no máximo
8 chaves — cabem direto num pedido de 8 cores.

Com pacotes de referência ativos, o recorte ganha uma última linha,
`referências:`, com o que os pacotes dizem de estilo e de porte — e é a
primeira a sair quando o teto aperta. O recorte não importa o módulo de
referências: o serviço passa a linha por um parâmetro. Detalhes em
[REFERENCIAS.md](REFERENCIAS.md) §5.

## 5. Rodar e testar

```bash
cd backend
pip install -e ".[mcp]"                      # SDK `mcp` 2.x, opcional
python -m assetflow.mcp                      # sobe por stdio (Ctrl+C para sair)
pytest tests/test_mcp.py tests/test_mcp_servidor.py tests/test_pixel_knowledge.py -q
```

`python -m assetflow.mcp` fica esperando mensagens no stdin — é o esperado:
quem conversa com ele é o Claude Code. Sem o SDK instalado, ele diz como
instalar e sai.

**stdout é o canal do protocolo.** Nada no servidor escreve nele; log vai para
stderr. Um `print()` perdido no caminho de um job quebraria a conexão.

O servidor roda o worker ele mesmo, um job por chamada
(`ServicoDesenhista._executar`), com o worker embutido desligado — um worker
em segundo plano disputaria a fila com ele.

O SDK é a **v2** do pacote `mcp`, em que `FastMCP` virou `MCPServer` e o import
antigo foi removido. O `pyproject.toml` fixa `mcp>=2.3,<3`. Em `servidor.py`
não há `from __future__ import annotations` de propósito: o SDK lê as
anotações das ferramentas para montar o schema, e a descrição de `perfil` é uma
variável local.
