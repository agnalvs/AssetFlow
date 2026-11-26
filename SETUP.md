# AssetFlow — instalação

Do clone até a primeira imagem gerada. O [README.md](README.md) descreve **o que**
o produto é; este arquivo é **como** colocá-lo para rodar.

---

## 1. O que o repositório traz e o que ele não traz

Vale entender isso antes, porque explica os passos seguintes:

| | Vem no clone? | Como se obtém |
|---|---|---|
| Código do backend e do frontend | ✅ | `git clone` |
| Gaveta `desenhista-v1` (`backend/assetflow/generation/engines/desenhista/`) | ✅ | `git clone` |
| Gavetas de referência (`mock-image-v1`, `mock-pixel-alt-v1`) | ✅ | `git clone` |
| Dependências Python (`fastapi`, `pydantic`, `Pillow`, `numpy`, …) | ❌ | `pip install` (passo 3) |
| Dependências do front (`node_modules/`) | ❌ | `npm ci` (passo 4) |

Não há modelo de IA para baixar nem GPU para configurar. Os motores de difusão
e as pontes para projetos externos saíram na Fase 0 do plano desenhista
([backend/docs/PLANO_DESENHISTA_MCP.md](backend/docs/PLANO_DESENHISTA_MCP.md)).
O motor real é a gaveta `desenhista-v1`: o Claude desenha, como uma receita
curta de camadas, e ela transforma a receita em sprite na grade lógica. Ela
não exige GPU nem baixa nada.

---

## 2. Requisitos

- **Python 3.11+** (a máquina de referência usa 3.13.1)
- **Node 18+** (referência: 24.12.0, npm 11.6.2)
- **Git**

A gaveta desenhista só gera a partir de uma receita, que chega pelo servidor
MCP (passo 10) ou, para testar, por arquivo (passo 6). As gavetas de
referência rodam o fluxo inteiro (job, fila, Pixel Exact, Pixel Optimizer,
histórico, UI), mas o que sai delas é um padrão determinístico, não arte.

---

## 3. Backend

```bash
git clone https://github.com/agnalvs/AssetFlow.git
cd AssetFlow/backend

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -e ".[dev,mcp]"
```

O extra `mcp` é o SDK do servidor MCP (passo 10). Sem ele, tudo funciona menos
o desenho pela conversa, e os testes do protocolo MCP são pulados.

### 3.1 Sanidade

```bash
pytest -q
```

Hoje: **`1254 passed, 1 skipped`**. O número muda a cada recurso — o que
importa é não haver `failed`. Os testes não usam GPU nem rede.

O pulado é deliberado: o caso de seed do contrato de gavetas, que a
`desenhista-v1` não suporta (a mesma receita dá sempre o mesmo sprite). Uma
gaveta cujas dependências não estão instaladas, ou que se declara indisponível
na máquina, também tem os testes de contrato **pulados**, não falhados.
Gavetas que exijam GPU ficam fora da suíte e entram com
`ASSETFLOW_TEST_REAL_ENGINES=1`; hoje nenhuma exige.

O lint é opcional e **já vem com achados**:

```bash
ruff check .        # 154 achados pré-existentes
```

O projeto não tem config própria de ruff, então valem os defaults, bem mais
rígidos que o estilo do código. Compare com esse número antes de concluir que
uma alteração sua introduziu lint novo.

---

## 4. Frontend

```bash
cd ../frontend
npm ci
```

`npm ci` (e não `npm install`) reproduz exatamente a árvore do `package-lock.json`.

Sanidade:

```bash
npm run typecheck
npm run build
```

---

## 5. Rodar

O frontend **não abre por `file://` nem por Live Server**: `src/main.tsx` é
TypeScript + JSX, que browser nenhum executa, e os imports são bare specifiers
(`"react"`) que só o Vite resolve. Quem traduz isso em tempo real é o dev server.

O backend também é obrigatório: o front chama `/api/generation/*` na própria
origem e o proxy do `vite.config.ts` encaminha para a `:8000`.

**No VS Code:** abrir a pasta já sobe os dois (via `.vscode/tasks.json`). Na
primeira vez o VS Code pede autorização — aceite o aviso, ou rode
`Tasks: Allow Automatic Tasks` na paleta de comandos (`Ctrl+Shift+P`).

**Na mão**, dois terminais:

```bash
cd backend  && .venv\Scripts\python.exe -m uvicorn assetflow.main:app --port 8000 --reload --reload-dir assetflow --reload-dir config
cd frontend && npm run dev
```

Depois: **http://localhost:5173**

> O `--reload-dir` não é enfeite. Sem ele o uvicorn vigia o `backend/` inteiro,
> e `backend/data/` é onde os PNGs são gravados: cada geração reiniciaria o
> servidor no meio do próprio job.

> **Mexeu em `config/*.yaml`? Reinicie o backend na mão.** O reload do uvicorn
> só observa `*.py` — `--reload-include "*.yaml"` existe, mas o próprio uvicorn
> avisa que a flag não faz nada sem o pacote `watchfiles`, que não está entre as
> dependências do projeto. Ou seja: o `--reload-dir config` do comando acima
> vigia uma pasta que não contém `.py` nenhum, e uma troca de motor ou de
> profile **não** entra em vigor sozinha. O servidor segue rodando a
> configuração que ele leu quando subiu, sem nenhum sinal de que está velha.

### 5.1 O que você vê

Um campo de descrição, os controles do asset (tipo, resolução, cores, vista,
corpo, detalhe, contorno) e o botão de gerar. Só Pixel Art: o modo 2D Normal, o
seletor de motor e o modo "Automático" saíram na Fase A do plano do app
([backend/docs/PLANO_APP_DESENHISTA.md](backend/docs/PLANO_APP_DESENHISTA.md)).

O único gerador é a desenhista, que precisa de uma receita escrita pelo Claude
— e a tela não manda receita. Por isso **"Gerar" cria um pedido numa fila**
(Fase B do plano do app). Na conversa com o Claude Code, com o servidor MCP
registrado (passo 10), diga *"desenhe os pedidos pendentes do AssetFlow"*: o
Claude pega a fila, desenha cada pedido, e o resultado aparece na tela sem
recarregar. Abaixo dos controles ficam a **liberdade criativa** (fiel,
equilibrado, ousado) e a **direção de arte**, que vão para o Claude e não
mudam grade, cores nem fundo. A fila mora em `backend/data/pedidos/`;
detalhes em [backend/docs/PEDIDOS.md](backend/docs/PEDIDOS.md).

Entre a descrição e o botão fica o painel **"O que o AssetFlow entendeu"**,
fechado por padrão. Ele mostra a estrutura que o sistema montou da sua frase —
vista, pose, composição, a lista de termos barrados para o modelo não devolver
uma folha de sprite — e deixa **editar esse JSON** antes de gerar. É por onde se
conserta uma leitura errada sem ficar reescrevendo a frase até acertar por
tentativa. Detalhe que importa: o que está no quadro é literalmente o que será
enviado; o AssetFlow não reaplica os padrões dele por cima da sua correção.

No modo Pixel Art, um asset aprovado ganha o selo **PIXEL EXACT ✓** — resolução
lógica real, alpha binário e paleta dentro do limite, medidos no arquivo
entregue. Veja [backend/docs/PIXEL_EXACT.md](backend/docs/PIXEL_EXACT.md).

---

## 6. A primeira geração

A gaveta `mock-image-v1` percorre o caminho inteiro — job, fila, Pixel Exact,
Pixel Optimizer, validação, storage, histórico — em segundos e sem baixar nada.
Ela só existe nos testes e no script de prévia, que monta o ambiente de testes;
o app não a registra:

```bash
cd backend
python scripts/preview_engine.py --engine mock-image-v1 -n 2
```

Os arquivos saem em `backend/data/preview/`, onde dá para abrir e olhar: o asset
lógico, a ampliação de visualização, a saída crua do motor e os relatórios de
processamento e validação em JSON.

Para ver a **gaveta desenhista** transformar uma receita em sprite, passe a
receita em arquivo. O exemplo é uma poção 16×16:

```bash
python scripts/preview_engine.py --engine desenhista-v1 \
    --receita assetflow/generation/engines/desenhista/exemplos/pocao_16x16.json \
    --profile pixel_prop_64 --prompt "poção vermelha 16x16"
```

O `16x16` no texto é o que faz o pedido sair em 16×16. O formato da receita
está em [backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md).

> O AssetFlow já teve um "Agente Pixel" que desenhava sozinho. Ele não é mais
> uma alternativa ao motor: virou o **AssetFlow Pixel Optimizer**, que revisa o
> sprite depois de qualquer motor
> ([backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md)). A
> contrapartida: sem um motor real, não há geração Pixel Art de verdade. As
> gavetas de referência nem são registradas no app (em `development` ou em
> `production`); sobra só a desenhista, que exige receita.

Um job que precise de mais tempo pode alargar o teto do worker, que envolve o
pipeline inteiro (padrão 900s):

```bash
export ASSETFLOW_JOB_TIMEOUT_S=1800     # Linux/macOS
```
```powershell
$env:ASSETFLOW_JOB_TIMEOUT_S = 1800     # PowerShell
```

---

## 7. Diferenças de máquina

`backend/config/engines.yaml` é versionado e compartilhado. Diferenças de
máquina vão em variável de ambiente — evita conflito de merge a cada `pull`. A
precedência é **variável de ambiente > YAML > padrão do código**; a lista
completa está em `backend/.env.example`.

- **Ligar e desligar gavetas:** `ASSETFLOW_ENGINES_ENABLED` e
  `ASSETFLOW_ENGINES_DISABLED`, listas separadas por vírgula.
- **Opções de uma gaveta** (caminhos, limites): `ASSETFLOW_ENGINE_<ID>_OPTIONS`
  como JSON, com o id em maiúsculas e `-` virando `_`. O merge é por chave sobre
  o bloco do YAML:

  ```bash
  ASSETFLOW_ENGINE_MOCK_IMAGE_V1_OPTIONS='{"simulated_latency_ms": 0}'
  ```

> Três variáveis são lidas por `assetflow/main.py`, não pelo módulo de
> configuração: `ASSETFLOW_HOST`, `ASSETFLOW_PORT` e `ASSETFLOW_RELOAD` só valem
> quando o servidor sobe por `python -m assetflow.main`. Com o comando `uvicorn`
> do passo 5, quem manda são as flags da linha de comando.

---

## 8. Diagnóstico

Além da interface, quatro maneiras de olhar o sistema por dentro.

**A documentação viva da API** — com o backend rodando, `http://localhost:8000/docs`
lista todos os endpoints com os esquemas de request e response.

**O que o AssetFlow entende de uma descrição**, sem gerar nada e sem criar job:

```bash
curl -X POST http://localhost:8000/api/generation/prompt/preview \
  -H "Content-Type: application/json" \
  -d '{"project_id":"teste","profile":"pixel_character_64","prompt":"cavaleiro com armadura azul"}'
```

O corpo é o **mesmo** do `POST /api/generation/jobs`, de propósito: a pergunta é
"o que aconteceria se eu mandasse isto?", e ela só tem valor feita com o objeto
que seria mandado. É o mesmo endpoint que alimenta o painel do passo 5.1.

**Quão longe do Pixel Exact está a saída de um motor** — o endpoint de
diagnóstico recebe uma imagem em base64 e devolve o relatório completo, sem
passar por job e sem persistir nada. Ele fica desligado por padrão:

```bash
ASSETFLOW_DEV_ENDPOINTS=1
```

```bash
curl -X POST http://localhost:8000/api/dev/pixel/analyze \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"<PNG em base64>","profile":"pixel_character_64_strict","process":true}'
```

Com `process: true` a imagem passa pelo processamento antes de ser validada (o
caminho real do pipeline); com `false`, ela é julgada exatamente como chegou.
Desligado, a rota devolve **404**. Repare que ela **não aparece no `/docs` em
nenhum dos dois casos** quando o servidor sobe por `uvicorn assetflow.main:app`:
o `include_in_schema` é decidido na criação da aplicação, e nesse caminho a
configuração só é carregada depois, no lifespan. A rota funciona; ela só não se
documenta sozinha.

Para comparar RAW × LOGICAL × PREVIEW lado a lado em arquivos, sem subir
servidor:

```bash
cd backend
python scripts/pixel_report.py --profile pixel_character_64_strict
```

---

## 9. Cache em outro disco (opcional)

Por padrão o pip e o `TEMP` escrevem no perfil do usuário, que costuma estar no
disco pequeno. Para mantê-los dentro do projeto, defina na sessão antes do
`pip install`:

```powershell
$env:PIP_CACHE_DIR = "$PWD\data\cache\pip"
$env:TMP = "$PWD\data\cache\tmp"
$env:TEMP = "$PWD\data\cache\tmp"
```

Instalações anteriores à Fase 0 podem ter deixado gigabytes de cache de modelo
dentro de `backend/data/` e pacotes de IA (`torch`, `diffusers`, …) na venv.
Nada disso é usado mais. Para liberar espaço, apague só a subpasta de cache —
**nunca** `backend/data/` inteira, que também guarda assets gerados e histórico.

---

## 10. Desenhar pela conversa (servidor MCP)

O servidor MCP do AssetFlow deixa o Claude Code desenhar: ele consulta o
pedido, manda a receita, recebe o laudo e corrige com remendos. Detalhes das
ferramentas, do laudo e do remendo: [backend/docs/MCP.md](backend/docs/MCP.md).

**1. Instale o SDK** (se não instalou no passo 3), com a venv ativa:

```bash
cd backend
pip install -e ".[mcp]"
```

**2. Confira que o servidor sobe.** O comando abaixo fica parado, esperando
mensagens — é o esperado; saia com `Ctrl+C`. Se faltar o SDK, ele diz como
instalar e sai.

```bash
.venv\Scripts\python.exe -m assetflow.mcp
pytest tests/test_mcp.py tests/test_mcp_servidor.py -q
```

**3. Registre no Claude Code**, de um destes dois jeitos. Nos dois, o comando é
o Python **da venv**, com caminho absoluto, e não precisa de variável de
ambiente nem de diretório de trabalho: o pacote está instalado em modo
editável e acha o `backend/` sozinho.

*3a. Pelo terminal*, se o comando `claude` existir nele (CLI do Claude Code
instalada à parte; a extensão do VS Code **não** põe `claude` no PATH). Num
terminal aberto na **raiz do clone**:

```bash
claude mcp add --scope local assetflow -- <caminho-do-clone>\backend\.venv\Scripts\python.exe -m assetflow.mcp
```

- As opções vêm **antes** do nome; tudo depois de `--` é o comando do servidor.
- `--scope local` vale só para este projeto e fica no seu `~/.claude.json`. É o
  escopo certo porque o caminho da venv é desta máquina. Para usar em qualquer
  pasta, use `--scope user`.

*3b. Por arquivo*, para quem usa só a extensão do VS Code. Crie `.mcp.json` na
**raiz do clone**:

```json
{
  "mcpServers": {
    "assetflow": {
      "command": "<caminho-do-clone>\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "assetflow.mcp"]
    }
  }
}
```

- No JSON, cada `\` do caminho vira `\\`.
- Sem `"type"`, a entrada é lida como servidor stdio, que é o caso aqui.
- **O `.mcp.json` está no `.gitignore`**: ele guarda o caminho desta máquina.
  Normalmente esse arquivo é versionado para o time inteiro; aqui não deve ser.
- O Claude Code pede aprovação antes de usar um servidor de projeto vindo de
  `.mcp.json`. Se o pedido aparecer, aprove o `assetflow`.
- O `/mcp` da extensão também consegue acrescentar servidores (Claude Code
  2.1.261 ou mais novo), se preferir não criar o arquivo à mão.

**4. Verifique.** Abra uma **conversa nova** — a configuração vale para as
conversas que começam depois dela — e digite `/mcp`. O `assetflow` deve
aparecer como **Connected**, com as sete ferramentas: `consultar_pedido`,
`pedidos_pendentes`, `desenhar`, `concluir_pedido`, `registrar_licao`,
`ver_asset` e `ver_referencia`. Pelo terminal (3a), também dá para conferir com:

```bash
claude mcp list            # assetflow ... ✔ Connected
claude mcp get assetflow   # escopo e comando registrados
```

**5. Teste na conversa.** Peça, por exemplo:

> Usando o AssetFlow, desenhe uma poção vermelha 16x16 com contorno escuro e
> me mostre o laudo. Depois troque o líquido para verde com um remendo.

O Claude deve chamar `consultar_pedido`, depois `desenhar` com a receita — que
devolve o laudo e a imagem para o olhar dele —, e `desenhar` de novo com `base`. Os PNGs ficam em
`backend/data/assets/projects/mcp/jobs/<job>/000.png`, e o laudo traz o caminho.

**Depois de mudar código ou `config/*.yaml`**, reinicie a sessão do Claude
Code (ou reconecte o servidor pelo `/mcp`): o processo do servidor carrega
tudo uma vez, quando sobe.

**Se aparecer `✘ Failed to connect`** (ou **Failed** no `/mcp`), rode o comando
registrado à mão (passo 2): o erro de verdade aparece no terminal.

**Para remover:** `claude mcp remove assetflow` (3a), ou apague o `.mcp.json`
(3b), ou remova pelo `/mcp`.

---

## 11. Onde ler mais

| Arquivo | Assunto |
|---|---|
| [README.md](README.md) | A especificação do produto. O código inteiro cita as seções dele como `plano §N`. |
| [backend/docs/PLANO_DESENHISTA_MCP.md](backend/docs/PLANO_DESENHISTA_MCP.md) | O plano em andamento: o motor passa a ser o Claude, por MCP. |
| [backend/docs/PIXEL_KNOWLEDGE.md](backend/docs/PIXEL_KNOWLEDGE.md) | Práticas de pixel art e animação que viram configuração e validação. |
| [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) | A infraestrutura de geração: trocar o motor sem tocar no produto. |
| [backend/docs/ENGINES.md](backend/docs/ENGINES.md) | Catálogo, roteamento e como acrescentar uma gaveta. |
| [backend/docs/DESENHISTA.md](backend/docs/DESENHISTA.md) | O formato da receita de desenho da gaveta `desenhista-v1`. |
| [backend/docs/MCP.md](backend/docs/MCP.md) | O servidor MCP: ferramentas, laudo e remendo. |
| [backend/docs/PIXEL_EXACT.md](backend/docs/PIXEL_EXACT.md) | A tecnologia de Pixel Art: por que "parecer Pixel Art" não basta. |
| [CLAUDE.md](CLAUDE.md) | Mapa curto do repositório e as armadilhas conhecidas. |
| `backend/config/*.yaml` | Gavetas, Generation Profiles, contratos Pixel Exact e capacidades — cada arquivo comentado. |
