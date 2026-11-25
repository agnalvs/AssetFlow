# Biblioteca de referências

> Adiantada antes da Fase 4 do [PLANO_DESENHISTA_MCP.md](PLANO_DESENHISTA_MCP.md),
> na trilha de base de conhecimento ("calibrar com exemplos reais").

O app importa pacotes de pixel art de licença livre **baixados à mão**, mede
cada quadro com código comum — numpy e Pillow, sem IA — e soma o que os
pacotes ativos dizem. O Claude só consulta o resultado:

- uma linha `referências:` no recorte de `consultar_pedido` ([MCP.md](MCP.md) §4);
- a ferramenta `ver_referencia`, que devolve **uma** imagem de exemplo.

Nada é baixado da internet, e nenhum sprite de terceiro vira receita: o recorte
traz números somados, e `ver_referencia` traz uma imagem.

Código em `assetflow/referencias/`. Ele não importa gaveta, kernel, pipeline,
job, API, storage nem MCP; a base de conhecimento não o importa; e nenhuma
gaveta o importa — `tests/test_architecture_boundaries.py` cobra as três.

## 1. Onde fica cada coisa

```
backend/data/referencias/            # o git ignora: é arte de terceiros
  <pacote>/
    manifesto.yaml                   # escrito pelo importador
    original/…                       # os PNGs das partes escolhidas e os textos de licença
    medidas.json                     # o que o medidor extraiu
  calibracao.md                      # o último relatório
backend/config/pixel_knowledge/referencias.yaml   # quais pacotes estão ativos (versionado)
```

O manifesto guarda `source_url`, `autor`, `license_id` (SPDX),
`license_url`, `license_verified_at`, `observacoes`, as partes e o
`origem_sha256` do zip. **Só `CC0-1.0` entra na coleção principal**; qualquer
outra licença vai para `atribuicao`, com `attribution_required: true`, e fica
fora do recorte até ser aceita na lista de ativos.

## 2. Importar

```bash
python -m assetflow.referencias importar <zip|pasta> --pacote <id> \
    --fonte <url> --autor "<nome>" --licenca CC0-1.0 --licenca-url <url> \
    [--licenca-verificada-em AAAA-MM-DD] [--nome "<nome>"] [--obs "<texto>"] \
    --parte "PADRAO:TIPO[:CORPO][:QUADRO]" [--parte …]      # ou --tipo/--corpo/--quadro
    [--excluir "PADRAO" …] [--substituir]
python -m assetflow.referencias listar       # pacotes, licença, ativo e avisos
python -m assetflow.referencias medir [<id>] # refaz medidas.json
python -m assetflow.referencias calibrar     # relatório (§6)
```

**Partes.** Um zip mistura personagens, itens, tiles, retratos e camadas soltas
de roupa. Cada `--parte` diz quais arquivos entram e o que eles são:

- `PADRAO` é um glob sobre o caminho dentro do zip ou da pasta, com `/`: `*`
  não atravessa pasta, `**` atravessa; sem diferença de maiúsculas;
- `TIPO` é o `asset.type` (`character`, `prop`, `tile`…); `CORPO`, o
  `body_type` (`humanoid`…), quando o pedido o conhece;
- `QUADRO` é a grade das folhas (`16x16`). `PADRAO:tile:16x16` também vale;
- a primeira parte que casa decide; arquivo que não casa com nenhuma não entra.

Sem `--parte`, `--tipo` (com `--corpo` e `--quadro`) vale para o pacote todo.

`--excluir PADRAO` (repetível, mesmo glob) tira arquivos de **qualquer** parte —
retratos (`**/Faceset.png`) ou sprites "na mão" que casam com um padrão largo
como `Monster/**`. A exclusão fica no manifesto e vale também para `medir`.
`--substituir` reimporta um pacote que já existe.

**Segurança.** Arquivo baixado é dado não confiável: o zip nunca é extraído
inteiro, caminho com `..`, absoluto ou com drive é recusado, só entram PNGs
das partes e textos de licença, há teto de 5.000 arquivos, 400 MB e 16
milhões de pixels por imagem, e `__MACOSX/`, `._*` e `.DS_Store` são
ignorados. GIF e `.aseprite` ficam de fora nesta fase.

## 3. O que o medidor extrai

| Medida | Como | Confiança |
|---|---|---|
| Escala do arquivo | blocos k×k iguais em todo o desenho; o resto é medido em 1× | alta |
| Fundo sólido | só sem transparência, com os 4 cantos iguais e ≥ 30% da imagem nessa cor | alta |
| Quadro | grade da parte; senão `(LxA)` no nome do arquivo; senão recortes separados por linhas transparentes | alta / alta / média |
| Frames por animação | quadros por linha da folha; ou sequência de nomes (`andar_f0`, `andar_f1`) | média; o nome da animação é o do arquivo |
| Altura e largura | caixa dos pixels opacos | alta — mas é **conteúdo**: inclui chapéu, penacho e arma |
| Cores e paleta | cores opacas únicas | alta |
| Contorno | borda opaca comparada com o vizinho de dentro: escuro único, colorido, seletivo ou misto, nenhum; e a cor mais comum | alta (escuro, colorido, nenhum); média (seletivo) |
| Tons por grupo de matiz | cores agrupadas por matiz, neutros à parte | média: material não se separa por matiz |
| Rampas prováveis | grupo do escuro ao claro cujas cores vizinhas se encostam | média |
| Ocupação, chão, folga, margem | só com o quadro conhecido | alta, mas não comparável entre pacotes |

**O que não se mede**, para não chutar: proporção em cabeças, altura do corpo
sem o equipamento, largura de braço e perna, tamanho do olho, vão entre
membros, material, direção da luz e o tipo do asset (que você declara).

O mesmo quadro aparece no arquivo individual e de novo no atlas: ele é medido
**uma** vez, pelo conteúdo, preferindo o arquivo individual (o que tem menos
quadros).

## 4. Ativar

```yaml
# config/pixel_knowledge/referencias.yaml
ativos:
  - ninja-adventure                               # CC0: entra direto
  - pacote-cc-by: {aceitar_atribuicao: true}      # não CC0: só com aceite
porte:
  faixa_altura:      {valor: 0.2, ..., a_calibrar: true}
  minimo_de_quadros: {valor: 3,   ..., a_calibrar: true}
  minimo_por_pacote: {valor: 30,  ..., a_calibrar: true}
  minimo_de_pacotes: {valor: 2,   ..., a_calibrar: true}
```

`minimo_por_pacote` e `minimo_de_pacotes` valem **parte a parte** (estilo e
porte), na linha, no `ver_referencia` e no `calibrar` (§5 e §6).

Pacote ativo que não está na pasta vira aviso no `listar` e no log, e fica de
fora. Lista vazia ou pasta ausente: tudo funciona como antes, e a linha some.
Reinicie o backend e o servidor MCP depois de mudar a lista (`/mcp`).

## 5. Como chega ao Claude

**A linha `referências:`**, a última seção do recorte — a primeira a sair
quando o teto aperta. Ela tem duas partes, e cada uma some sozinha. Com os dez
pacotes ativos em 2026-11-25, o humanóide 32 (e o quadro 48×48, que tem o mesmo
corpo) recebe:

```text
referências: estilo de 2985 quadros (9 pacotes, peso igual): contorno escuro único em 58% (cor mais comum #222222) · 3 tons por grupo de matiz (mediana); porte de 23–33 px de altura, 515 quadros (3 pacotes, peso igual): 7–24 cores (mediana 11) · largura 0,81× a altura · preenchimento 76% da caixa
```

Com os cinco da primeira leva, o porte tinha ficado com um pacote só e a parte
saía da linha (ver abaixo).

- **estilo** vale de qualquer tamanho: quadros do mesmo tipo (e do mesmo
  corpo, quando o pedido o conhece);
- **porte** compara pelo **corpo**, não pelo quadro: só os quadros cuja
  altura de conteúdo fica em `altura do corpo × (1 ± faixa_altura)`. A altura
  do corpo sai de `proporcoes.yaml` (`tamanhos` ou `quadros`), lida do spec
  como o resto do recorte — num quadro 48×48 vale o corpo de 32;
- linha de chão, margem e ocupação não entram: o quadro é outro;
- **cada pacote pesa igual**: um pacote de 2.600 quadros não decide sozinho;
- **e por isso um pacote precisa de amostra**: com menos de
  `minimo_por_pacote` quadros **naquela parte**, ele sai dela (um pacote pode
  estar no estilo e fora do porte). Sem isso, 1 quadro pesava como 400;
- **uma parte com menos de `minimo_de_pacotes` some**: um pacote só é o
  estilo dele, não uma referência. Foi o caso do porte do humanóide 32: depois
  do mínimo por pacote, sobrava só o corpo-base sem roupa do
  `customizable-character-pack` (6 a 8 cores, largura 0,57×), que não
  representa personagens vestidos.

**`ver_referencia(pedido, perfil?)`** resolve o spec como `consultar_pedido` e
devolve o quadro mais típico (mais perto das medianas), ampliado para uns
256 px, com pacote, autor, licença e arquivo na legenda. O conjunto segue a
regra da linha: o porte, se ele bastar; senão o estilo, de qualquer tamanho;
senão nenhum, e o erro diz como importar.

## 6. Calibrar

`calibrar` compara as referências ativas com cada número de
`proporcoes.yaml` e grava `data/referencias/calibracao.md`. **Só propõe**:
nenhum YAML é alterado. Cada medida sai como uma de quatro:

- **comparada** — `tons_por_material`, com proposta;
- **circular** — `altura_px`: é ela que escolhe os quadros de porte parecido;
- **não comparável** — `chao_y`, `margem_px`, `folga_topo_px`, `ocupacao_min`;
- **não medida** — cabeças, partes e larguras (a de tronco ganha a largura do
  conteúdo do mesmo porte como nota).

Cada parte segue as regras da linha: o pacote abaixo de `minimo_por_pacote`
sai, com nome e contagem ("fora por amostra pequena"); a parte com menos de
`minimo_de_pacotes` **continua no relatório**, com os números, marcada
**insuficiente** e sem proposta — ela só não chega ao Claude.

A última seção roda o validador sobre as referências, com os limiares de
`config/quality.yaml` (até 300 quadros por pacote, espaçados por igual), e
mostra por pacote a nota mediana, quantos quadros levariam os avisos de blocos
pequenos e de cor rara, e o p90 das duas medidas. Fecha com a proposta desses
limiares pela regra escrita no `quality.yaml` — o p90 do pacote mais alto,
arredondado para cima, para nenhum pacote receber o aviso em mais de 10% dos
quadros — ao lado do valor configurado. Como o resto, só propõe.
