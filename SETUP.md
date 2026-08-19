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
| Dependências Python (`torch`, `diffusers`, …) | ❌ | `pip install` (passo 3) |
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
  `recommended_vram_mb: 12000` e `minimum_vram_mb: 8000`.
- **~15GB livres em disco** — ~7GB dos pesos, o resto entre venv (o torch com
  CUDA sozinho passa de 2GB) e `node_modules`.

Sem GPU o sistema **continua funcionando**: a gaveta `mock-image-v1` gera
placeholders e todo o fluxo (job, fila, pós-processamento, histórico, UI) roda
igual. Só não sai arte de verdade.

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

Esperado: `355 passed, 10 skipped`. Os testes não usam GPU nem rede — a gaveta
`mock-image-v1` existe para isso.

---

## 4. Frontend

```bash
cd ../frontend
npm ci
```

`npm ci` (e não `npm install`) reproduz exatamente a árvore do `package-lock.json`.

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

---

## 6. Primeira geração com SDXL — faça o aquecimento antes

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

Se ainda assim precisar de mais folga na API:

```bash
export ASSETFLOW_JOB_TIMEOUT_S=1800     # Linux/macOS
```
```powershell
$env:ASSETFLOW_JOB_TIMEOUT_S = 1800     # PowerShell
```

---

## 7. Ajustar ao seu hardware

O perfil ativo em `backend/config/engines.yaml` assume **12GB+ de VRAM**, com
offload desligado (mais rápido).

- **GPU de 4-6GB**: o arquivo traz o **PERFIL B** comentado logo abaixo do ativo
  — usa SDXL-Turbo (1-4 passos em vez de 30) e `sequential_cpu_offload`. Copie
  por cima dos campos ativos e alargue também `ASSETFLOW_JOB_TIMEOUT_S=1800`.
- **`CUDA out of memory`** com 12GB: ligue `enable_model_cpu_offload: true`.
  Ele troca velocidade por VRAM, mas é bem menos drástico que o sequencial.
- **Sem GPU / só testar o fluxo**: desligue a gaveta pesada sem editar arquivo:

  ```bash
  ASSETFLOW_ENGINES_DISABLED=diffusers-sdxl-v1
  ```

Como `engines.yaml` é versionado, prefira as variáveis de ambiente para
diferenças de máquina — evita conflito de merge a cada `pull`. A precedência é
**variável de ambiente > YAML > padrão do código**; veja `backend/.env.example`
para a lista completa.

---

## 8. Cache em outro disco (opcional)

Por padrão pip, HuggingFace e TEMP escrevem no perfil do usuário, que costuma
estar no disco pequeno. Para manter tudo dentro do projeto:

```powershell
cd backend
. .\scripts\use-local-cache.ps1
```

Vale só para a sessão atual do terminal.
