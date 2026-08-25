# AssetFlow — instalação

Do clone até a primeira imagem gerada. O [README.md](README.md) descreve **o que**
o produto é; este arquivo é **como** colocá-lo para rodar.

---

## 1. O que o repositório traz e o que ele não traz

Vale entender isso antes, porque explica os passos seguintes:

| | Vem no clone? | Como se obtém |
|---|---|---|
| Código do backend e do frontend | ✅ | `git clone` |
| **Gaveta** SDXL (o adaptador em `backend/assetflow/generation/engines/diffusers_sdxl/`) | ✅ | `git clone` |
| Dependências Python (`torch`, `diffusers`, `peft`, …) | ❌ | `pip install` (passo 3) |
| Dependências do front (`node_modules/`) | ❌ | `npm ci` (passo 4) |
| **Pesos do modelo SDXL** (~7GB de `.safetensors`) | ❌ | Baixados do HuggingFace na 1ª geração (passo 6) |

Os pesos não são versionados de propósito: o GitHub rejeita arquivo acima de
100MB e a UNet do SDXL sozinha tem ~5GB. Eles vão para um cache local, que o
`.gitignore` cobre via `backend/data/`.

---

## 2. Requisitos

- **Python 3.11+** (a máquina de referência usa 3.13.1)
- **Node 18+** (referência: 24.12.0, npm 11.6.2)
- **Git**
- Para o SDXL: **GPU NVIDIA**. O manifesto da gaveta declara
  `recommended_vram_mb: 12000` e `minimum_vram_mb: 8000` — números do SDXL
  base. O perfil que vem ativo usa SDXL-Turbo com offload sequencial e roda em
  4GB; veja o passo 7.
- **~15GB livres em disco** — ~7GB dos pesos, o resto entre venv (o torch com
  CUDA sozinho passa de 2GB) e `node_modules`.

Sem GPU o sistema **continua funcionando**: a gaveta `mock-image-v1` gera
placeholders e todo o fluxo (job, fila, Pixel Exact, histórico, UI) roda igual.
Só não sai arte de verdade — veja o passo 6.1.

---

## 3. Backend

```bash
git clone https://github.com/agnalvs/AssetFlow.git
cd AssetFlow/backend

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
```

### 3.1 O torch com CUDA — não pule esta parte

Instale o **torch primeiro, do índice da PyTorch**, antes de qualquer outra coisa:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

Depois o resto:

```bash
pip install -e ".[diffusers,dev]"
```

**Por que nessa ordem.** O `pyproject.toml` declara `torch>=2.2` e o pip, sozinho,
resolve isso **do PyPI** — onde o wheel de Windows é **CPU-only**. O resultado é
um SDXL que roda na CPU: dezenas de minutos por imagem, quando não estoura a RAM.
Instalando do índice da PyTorch antes, o requisito já está satisfeito e o pip não
o substitui.

Confira que deu certo:

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Você precisa ver `+cu126` na versão **e** `True`:

```
2.6.0+cu126 True
```

Se aparecer `2.6.0 False`, veio o wheel errado. Corrija com:

```bash
pip uninstall -y torch
pip install torch --index-url https://download.pytorch.org/whl/cu126
```

> O `+cu126` é um *local version identifier*, que o PyPI proíbe. Se ele está lá,
> o wheel só pode ter vindo do índice da PyTorch — é um sinal confiável.

### 3.2 Sanidade

```bash
pytest -q
```

Hoje: **`812 passed, 10 skipped`**. O número cresce a cada recurso — o que
importa é não haver `failed`. Os testes não usam GPU nem rede: a gaveta
`mock-image-v1` existe para isso.

Os 10 pulados são deliberados, e a contagem varia com o ambiente: 8 são os
testes de contrato da gaveta pesada, que baixariam o modelo, e 2 só existem
para o caso de o `torch` **não** estar instalado — com ele presente, eles se
pulam. Para exercitar a gaveta de verdade (GPU + download):

```bash
ASSETFLOW_TEST_REAL_ENGINES=1 pytest -q
```

O lint é opcional e **já vem com achados**:

```bash
ruff check .        # 127 achados pré-existentes
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

Dois modos — **Pixel Art** e **2D Normal** —, um campo de descrição e o botão de
gerar. A interface não conhece motor nenhum: ela pede uma *capacidade*, e quem
escolhe o que atende é o backend.

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

### 6.1 Sem GPU, ou só para ver o fluxo de ponta a ponta

A gaveta `mock-image-v1` percorre o caminho inteiro — job, fila, Pixel Exact,
validação, storage, histórico — em segundos e sem baixar nada:

```bash
cd backend
python scripts/preview_engine.py --engine mock-image-v1 -n 2
```

Os arquivos saem em `backend/data/preview/`, onde dá para abrir e olhar: o asset
lógico, a ampliação de visualização, a saída crua do motor e os relatórios de
processamento e validação em JSON.

> Sempre nomeie a gaveta. `--engine all` e `--engine config` (o padrão) alcançam
> a `diffusers-sdxl-v1`, que está habilitada — e aí a primeira execução baixa
> ~7GB.

### 6.2 Com SDXL — faça o aquecimento antes

Na primeira vez, o `from_pretrained` baixa ~7GB. **Não dispare isso pela
interface**, por um motivo concreto:

O worker envolve o pipeline inteiro em `asyncio.wait_for(..., timeout=job_timeout_s)`,
e `job_timeout_s` vale **900s (15 min) por padrão**. O carregamento do modelo
acontece *dentro* dessa janela. Ou seja: o download de 7GB precisaria sustentar
~8 MB/s do começo ao fim, senão o job morre com `job excedeu o tempo máximo de 900s`.
Os valores de `timeouts` no `engines.yaml` **não salvam** — eles são deadlines
internos, e o teto do worker mata antes de qualquer um deles ser atingido.

Baixe fora do caminho da API, com um teto próprio:

```bash
cd backend
python scripts/preview_engine.py --engine diffusers-sdxl-v1 --timeout 3600 -n 1
```

Esse script existe justamente para isso: ele controla o próprio
`worker.job_timeout_s` (padrão `--timeout 3600`) e escreve os PNGs em
`backend/data/preview/`, onde dá para abrir e olhar.

Depois que o modelo está em cache, a interface responde normal — as gerações
seguintes só pagam a inferência, bem dentro dos 900s.

### 6.3 Os outros motores de Pixel Art

O AssetFlow tem três gavetas de Pixel Art além do SDXL (veja
[backend/docs/ENGINES.md](backend/docs/ENGINES.md)). **Nenhuma delas funciona
sem configuração**:

| motor | para habilitar |
|---|---|
| **FLUX Pixel** | `pip install -e ".[diffusers]"` + GPU + `enabled: true` em `engines.yaml` |
| **SD-πXL** | clone do projeto + `options.command` apontando para a CLI dele |
| **Pixel Forge** | binário Rust compilado + `options.binary` |

Para conferir o fluxo inteiro — escolha automática com motivo, Pixel Exact,
revisão do Pixel Optimizer, selo técnico — antes de qualquer download, use a
gaveta de referência `mock-image-v1`. Ela não gera arte: produz um padrão
determinístico, e serve exatamente para exercitar o caminho.

```bash
cd backend
python scripts/benchmark_engines.py --targets mock-image-v1 --cases tree_32
```

> O AssetFlow já teve um "Agente Pixel" que desenhava sozinho e servia de
> caminho sem GPU. Ele não é mais uma alternativa ao motor: virou o
> **AssetFlow Pixel Optimizer**, que revisa o sprite depois de qualquer motor
> ([backend/docs/PIXEL_OPTIMIZER.md](backend/docs/PIXEL_OPTIMIZER.md)). A
> contrapartida é esta seção: sem um motor configurado, não há geração Pixel
> Art de verdade fora do ambiente de desenvolvimento.

Ao habilitar o **FLUX Pixel**, confira os dois ids no HuggingFace antes
(`model.id` e `options.lora.id` em `engines.yaml`): um repositório pode mudar
de nome, e o id errado só aparece como falha de download no primeiro job. Vale
o mesmo aquecimento do SDXL — baixe pelo `preview_engine.py --timeout 3600`,
nunca pela interface.

O **SD-πXL** merece um aviso à parte: o projeto declara execuções de **horas**
por imagem e recomenda 24GB de VRAM. Habilitá-lo sem alargar
`ASSETFLOW_JOB_TIMEOUT_S` garante que todo job dele morra no teto do worker
antes de terminar.

Se ainda assim precisar de mais folga na API:

```bash
export ASSETFLOW_JOB_TIMEOUT_S=1800     # Linux/macOS
```
```powershell
$env:ASSETFLOW_JOB_TIMEOUT_S = 1800     # PowerShell
```

---

## 7. Ajustar ao seu hardware

O perfil ativo em `backend/config/engines.yaml` é o de **GPU pequena (4-6GB)**:
SDXL-Turbo, que gera em 1-4 passos em vez de 30, com `sequential_cpu_offload`
ligado.

Ele exige **`ASSETFLOW_JOB_TIMEOUT_S=1800`** no ambiente que sobe o backend. O
`timeout_s: 1800` declarado no YAML é inalcançável sob o teto padrão de 900s do
worker, que envolve o pipeline inteiro — o worker mataria o job antes. (A tarefa
do VS Code deste checkout já carrega a variável, mas `.vscode/` não é
versionado: em um clone novo, defina-a você mesmo.)

- **GPU de 12GB+**: o arquivo traz o **PERFIL B** comentado logo abaixo do ativo
  — SDXL base, 30 passos, sem offload. Mais qualidade por imagem. Copie por
  cima dos campos ativos, e repare que `guidance_scale` anda junto com o
  modelo: o Turbo exige `0.0`, o base usa `6.5`. Trocar um e esquecer o outro
  devolve imagem lavada.
- **Trocar de perfil troca o modelo**, e um modelo novo é um download novo de
  ~7GB. Refaça o aquecimento do passo 6.2 antes de gerar pela interface.
- **`CUDA out of memory`** numa placa grande: ligue `enable_model_cpu_offload: true`.
  Ele troca velocidade por VRAM, mas é bem menos drástico que o sequencial.
- **Sem GPU / só testar o fluxo**: desligue a gaveta pesada sem editar arquivo:

  ```bash
  ASSETFLOW_ENGINES_DISABLED=diffusers-sdxl-v1
  ```

Como `engines.yaml` é versionado, prefira as variáveis de ambiente para
diferenças de máquina — evita conflito de merge a cada `pull`. A precedência é
**variável de ambiente > YAML > padrão do código**; a lista completa está em
`backend/.env.example`.

A escolha de perfil acima é a exceção conhecida a essa regra: as `ASSETFLOW_*`
cobrem motor, device, precisão e tetos, mas **não trocam o modelo** — e é a
troca de modelo que separa uma placa de 4GB de uma de 12GB. Trocar de perfil
edita o YAML mesmo; o arquivo explica os dois lado a lado para que a edição
seja copiar e colar.

> Três delas são lidas por `assetflow/main.py`, não pelo módulo de configuração:
> `ASSETFLOW_HOST`, `ASSETFLOW_PORT` e `ASSETFLOW_RELOAD` só valem quando o
> servidor sobe por `python -m assetflow.main`. Com o comando `uvicorn` do passo
> 5, quem manda são as flags da linha de comando.

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

Por padrão pip, HuggingFace e TEMP escrevem no perfil do usuário, que costuma
estar no disco pequeno. Para manter tudo dentro do projeto:

```powershell
cd backend
. .\scripts\use-local-cache.ps1
```

Vale só para a sessão atual do terminal.

---

## 10. Onde ler mais

| Arquivo | Assunto |
|---|---|
| [README.md](README.md) | A especificação do produto. O código inteiro cita as seções dele como `plano §N`. |
| [backend/docs/ARCHITECTURE.md](backend/docs/ARCHITECTURE.md) | A infraestrutura de geração: trocar o motor sem tocar no produto. |
| [backend/docs/PIXEL_EXACT.md](backend/docs/PIXEL_EXACT.md) | A tecnologia de Pixel Art: por que "parecer Pixel Art" não basta. |
| [CLAUDE.md](CLAUDE.md) | Mapa curto do repositório e as armadilhas conhecidas. |
| `backend/config/*.yaml` | Gavetas, Generation Profiles, contratos Pixel Exact e capacidades — cada arquivo comentado. |
