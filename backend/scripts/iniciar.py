"""Um clique para abrir o AssetFlow (lote 10). Chamado pelo ``iniciar.bat`` da raiz.

1. **A API.** Se já há uma API do AssetFlow respondendo na 8000, ela é usada
   (uma segunda não sobe). Se a 8000 está ocupada por outro programa, a API
   sobe na próxima porta livre, e a tela é apontada para ela
   (``ASSETFLOW_API_URL``, que o ``vite.config.ts`` lê).
2. **A tela.** Sobe na 5173 ou, ocupada, na próxima livre — sempre com
   ``--strictPort``, para o Vite não trocar de porta por conta própria e o
   endereço aberto ser o que ele de fato usa.
3. **Espera as duas responderem** e confere que o endereço é o AssetFlow: o
   título da página e o ``/api/health`` **pelo proxy da tela**. Uma porta com
   outro app nunca é aberta.
4. **Abre o navegador** no endereço certo e fica rodando; Ctrl+C (ou fechar a
   janela) encerra o que ele subiu. A saída de cada parte vai para
   ``backend/data/iniciar/``.

    python backend/scripts/iniciar.py [--sem-navegador] [--espera 90]
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
FRONTEND = RAIZ / "frontend"
LOGS = BACKEND / "data" / "iniciar"
API_PADRAO = 8000
TELA_PADRAO = 5173
HOST = "127.0.0.1"
#: A gaveta que identifica uma API do AssetFlow no /api/health.
GERADOR = "desenhista-v1"


# ---------------------------------------------------------------------------
# Portas e respostas
# ---------------------------------------------------------------------------
def em_uso(porta: int, host: str = HOST) -> bool:
    """Alguém atende nesta porta (IPv4 ou, no ``localhost``, IPv6)?"""
    for familia, endereco in ((socket.AF_INET, host), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(familia, socket.SOCK_STREAM) as s:
                s.settimeout(0.3)
                if s.connect_ex((endereco, porta)) == 0:
                    return True
        except OSError:
            continue
    return False


def porta_livre(inicio: int, tentativas: int = 50, host: str = HOST) -> int:
    """A primeira porta a partir de ``inicio`` em que ninguém atende e dá para escutar."""
    for porta in range(inicio, inicio + tentativas):
        if em_uso(porta, host):
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, porta))
            except OSError:
                continue
        return porta
    raise RuntimeError(f"nenhuma porta livre entre {inicio} e {inicio + tentativas - 1}")


def _ler(url: str, tempo: float = 2.0) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=tempo) as resposta:
            return resposta.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def e_a_api(base: str) -> bool:
    """``base`` (``http://127.0.0.1:8000``) é uma API do AssetFlow?"""
    corpo = _ler(f"{base}/api/health")
    if not corpo:
        return False
    try:
        saude = json.loads(corpo)
    except json.JSONDecodeError:
        return False
    return isinstance(saude, dict) and GERADOR in (saude.get("engines") or {})


def e_a_tela(base: str) -> bool:
    """``base`` é a tela do AssetFlow, com o proxy chegando à API?"""
    pagina = _ler(base + "/")
    return bool(pagina and "<title>AssetFlow" in pagina and e_a_api(base))


def _bases(porta: int) -> list[str]:
    """Os dois endereços locais: no Windows, ``localhost`` costuma ser o IPv6."""
    return [f"http://{HOST}:{porta}", f"http://[::1]:{porta}"]


def ja_rodando(porta: int, teste: Callable[[str], bool]) -> str | None:
    """O endereço em que ``teste`` passa nesta porta (IPv4 ou IPv6), ou ``None``."""
    return next((base for base in _bases(porta) if teste(base)), None)


def para_o_navegador(base: str) -> str:
    """O endereço a abrir: ``localhost`` no lugar do IPv6 entre colchetes."""
    return base.replace("[::1]", "localhost") + "/"


def esperar(teste: Callable[[], bool], segundos: float, passo: float = 0.5) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if teste():
            return True
        time.sleep(passo)
    return False


# ---------------------------------------------------------------------------
# Processos
# ---------------------------------------------------------------------------
def _python() -> Path:
    janelas = BACKEND / ".venv" / "Scripts" / "python.exe"
    return janelas if janelas.exists() else BACKEND / ".venv" / "bin" / "python"


def _subir(comando: list[str], pasta: Path, log: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    saida = log.open("w", encoding="utf-8")
    extras = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    return subprocess.Popen(
        comando, cwd=pasta, stdout=saida, stderr=subprocess.STDOUT, env=env, **extras
    )


def _encerrar(processo: subprocess.Popen) -> None:
    if processo.poll() is not None:
        return
    if os.name == "nt":
        # O npm e o --reload do uvicorn sobem filhos: taskkill /T leva a árvore.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(processo.pid)], capture_output=True, check=False)
    else:
        os.killpg(processo.pid, signal.SIGTERM)


def _faltando() -> list[str]:
    faltas = []
    if not _python().exists():
        faltas.append("o ambiente do backend (backend/.venv): SETUP.md, passo do backend")
    if not (FRONTEND / "node_modules").is_dir():
        faltas.append("as dependências da tela (frontend/node_modules): rode npm ci em frontend/")
    return faltas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sobe a API e a tela do AssetFlow e abre o navegador.")
    parser.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    parser.add_argument("--espera", type=float, default=90.0, help="segundos de espera por cada parte")
    args = parser.parse_args(argv)

    faltas = _faltando()
    if faltas:
        print("Falta instalar:\n- " + "\n- ".join(faltas))
        return 1

    subidos: list[subprocess.Popen] = []
    try:
        api_base = ja_rodando(API_PADRAO, e_a_api)
        if api_base:
            print(f"API do AssetFlow já rodando em {api_base}: uso essa.")
        else:
            porta = API_PADRAO if not em_uso(API_PADRAO) else porta_livre(API_PADRAO + 1)
            if porta != API_PADRAO:
                print(f"A porta {API_PADRAO} está ocupada por outro programa; a API sobe na {porta}.")
            api_base = f"http://{HOST}:{porta}"
            subidos.append(_subir(
                [str(_python()), "-m", "uvicorn", "assetflow.main:app", "--host", HOST, "--port", str(porta),
                 "--reload", "--reload-dir", "assetflow", "--reload-dir", "config"],
                BACKEND, LOGS / "api.log",
            ))
            print(f"Subindo a API em {api_base}…")
            if not esperar(lambda: e_a_api(api_base), args.espera):
                print(f"A API não respondeu em {args.espera:.0f} s. Veja {LOGS / 'api.log'}.")
                return 1

        aberta = ja_rodando(TELA_PADRAO, e_a_tela)
        if aberta:
            print(f"Tela do AssetFlow já rodando em {aberta}: uso essa.")
            print(f"\nAssetFlow pronto: {para_o_navegador(aberta)}  (API em {api_base})")
            if not args.sem_navegador:
                webbrowser.open(para_o_navegador(aberta))
            if not subidos:
                return 0
            print("Deixe esta janela aberta; Ctrl+C encerra a API que subiu aqui.")
            while all(p.poll() is None for p in subidos):
                time.sleep(1)
            return 1
        tela = TELA_PADRAO if not em_uso(TELA_PADRAO) else porta_livre(TELA_PADRAO + 1)
        if tela != TELA_PADRAO:
            print(f"A porta {TELA_PADRAO} está ocupada por outro programa; a tela sobe na {tela}.")
        tela_base = f"http://{HOST}:{tela}"
        npm = "npm.cmd" if os.name == "nt" else "npm"
        subidos.append(_subir(
            [npm, "run", "dev", "--", "--host", HOST, "--port", str(tela), "--strictPort"],
            FRONTEND, LOGS / "tela.log", env={**os.environ, "ASSETFLOW_API_URL": api_base},
        ))
        print(f"Subindo a tela em {tela_base}…")
        if not esperar(lambda: e_a_tela(tela_base), args.espera):
            print(f"A tela não respondeu como o AssetFlow em {args.espera:.0f} s. Veja {LOGS / 'tela.log'}.")
            return 1

        print(f"\nAssetFlow pronto: {tela_base}/  (API em {api_base})")
        if not args.sem_navegador:
            webbrowser.open(f"{tela_base}/")
        if not subidos:
            return 0
        print("Deixe esta janela aberta; Ctrl+C encerra o que foi subido aqui.")
        while all(p.poll() is None for p in subidos):
            time.sleep(1)
        print("Uma das partes parou; veja os logs em", LOGS)
        return 1
    except KeyboardInterrupt:
        print("\nEncerrando…")
        return 0
    finally:
        for processo in subidos:
            _encerrar(processo)


if __name__ == "__main__":
    raise SystemExit(main())
