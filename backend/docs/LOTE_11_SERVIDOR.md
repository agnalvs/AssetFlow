# Lote 11 — aviso de servidor desatualizado

> Décimo primeiro lote da sessão (pedido da autora em 2026-11-26;
> SUGESTOES_DE_MELHORIA §15). Proposta seguida sem consulta; decisões e
> dúvidas também no [RELATORIO_ESTADO.md](RELATORIO_ESTADO.md). Código:
> `assetflow/servidores.py`, `assetflow/versao.py`,
> `frontend/src/components/AvisoDeServidor.tsx`.

## 1. O que entrou

**Cada processo se registra ao subir.** A API (no `lifespan`) e o servidor MCP
(no `main`) gravam `backend/data/servidores/<processo>-<pid>.json` com o pid,
o commit (lido do `.git`, sem chamar o git) e a hora; ao encerrar, apagam o
arquivo. O de um processo que morreu sem apagar é descartado na leitura.

**A tela pergunta à API** (`GET /api/servidores`, a cada minuto) e mostra uma
faixa no topo quando algum processo **vivo** está desatualizado:

| Processo | Desatualizado quando | A faixa diz |
|---|---|---|
| servidor MCP | um arquivo de `assetflow/` ou `config/` mudou depois que ele subiu | "reconecte pelo /mcp no Claude Code" |
| API | um arquivo de `config/` mudou depois que ela subiu (os `.py` o `--reload` já recarrega) | "reinicie a API" |

`config/pixel_knowledge/propostas/` não conta: nada a lê. O **commit** fica
registrado só como informação.

> **Corrigido em 2026-11-26.** A primeira versão também avisava quando o processo
> tinha subido noutro commit. Era falso positivo: o `--reload` reinicia a API
> assim que o `.py` muda, **antes** do commit, e ela sempre ficava "um commit
> atrás" rodando o código certo. Um `git pull` ou `checkout` regrava os
> arquivos alterados, e o horário deles já avisa.

## 2. Interruptor

`ASSETFLOW_AVISO_SERVIDOR` (`settings.servidores.aviso`, ligado). Desligado, a
rota devolve `aviso: null` e a faixa não aparece; o registro continua.

## 3. Decisões tomadas sem consulta

1. **Um arquivo por processo** em `data/servidores/`, porque API e MCP são
   processos diferentes, e pode haver mais de um MCP (uma sessão do Claude Code
   cada).
2. **"Vivo" sem `os.kill`**: no Windows, `os.kill(pid, 0)` encerra o processo;
   a conferência usa `OpenProcess` e `GetExitCodeProcess`.
3. **O horário dos arquivos decide, não o commit** (corrigido; ver acima).
4. **O leitor de commit saiu de `banca/config.py` para `assetflow/versao.py`**
   e continua exportado pela banca.

## 4. Dúvidas para a autora

1. **Os processos que subiram antes deste lote não se registram**: o servidor
   MCP desta sessão, por exemplo. Depois de uma reconexão pelo `/mcp`, ele passa
   a aparecer.
2. **Trocar de branch** com o MCP aberto avisa (os arquivos são regravados), e
   reconectar resolve.
