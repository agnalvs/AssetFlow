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
| `consultar_pedido` | `pedido`, `perfil?` | o que o spec resolveu + o formato da receita + o recorte de conhecimento |
| `desenhar` | `pedido?`, `receita?`, `base?`, `perfil?` | o laudo em texto |
| `ver_asset` | `id` | uma legenda e o PNG ampliado |

- **`perfil`** é o profile de partida, e só vale no que o texto não disser. O
  padrão é `pixel_character_32`. A lista de opções na descrição sai dos
  profiles Pixel do `profiles.yaml`, no boot.
- **O formato da receita vem na resposta de `consultar_pedido`**, e não na
  descrição de `desenhar`: assim ele só ocupa contexto quando há desenho.
- **O recorte de conhecimento vem vazio** até a Fase 3, que cria
  `config/pixel_knowledge/`.
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

## 4. Rodar e testar

```bash
cd backend
pip install -e ".[mcp]"                      # SDK `mcp` 2.x, opcional
python -m assetflow.mcp                      # sobe por stdio (Ctrl+C para sair)
pytest tests/test_mcp.py tests/test_mcp_servidor.py -q
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
