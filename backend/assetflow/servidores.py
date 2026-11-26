"""Em que código a API e o servidor MCP estão rodando (lote 11).

O servidor MCP carrega código e ``config/`` uma vez, quando o Claude Code o
sobe, e não recarrega: um desenho feito depois de uma mudança sai pelo código
antigo, sem sinal nenhum. A API recarrega ``*.py`` (``--reload``), mas não o
``config/``. Por isso cada processo grava, ao subir, um arquivo em
``data/servidores/`` (``api-<pid>.json``, ``mcp-<pid>.json``) com o pid, o
commit e a hora; e a tela pergunta à API se algum processo **vivo** está
desatualizado:

* subiu num **commit diferente** do atual do repositório; ou
* subiu **antes da última alteração** de um arquivo de ``assetflow/`` ou de
  ``config/`` (código mudado sem commit também é código que ele não roda) —
  para a API, só ``config/``, porque o ``--reload`` cuida dos ``.py``.

Arquivo de processo que já morreu é descartado na leitura. Este módulo não
importa API, MCP, gaveta nem jobs.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .versao import commit_do_git, ultima_alteracao

if TYPE_CHECKING:  # pragma: no cover
    from .settings import Settings

__all__ = ["Processo", "registrar", "remover_registro", "situacao", "vivo"]

PROCESSOS = ("api", "mcp")


@dataclass(frozen=True, slots=True)
class Processo:
    processo: str
    pid: int
    commit: str | None
    subiu_em: str
    #: ``time.time()`` da subida, para comparar com o mtime dos arquivos.
    subiu_ts: float


def _pasta(settings: Settings) -> Path:
    return settings.data_dir / "servidores"


def vivo(pid: int) -> bool:
    """O processo ``pid`` existe? (No Windows, sem ``os.kill``, que o encerraria.)"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        alca = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not alca:
            return False
        try:
            codigo = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(alca, ctypes.byref(codigo)):
                return False
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(alca)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def registrar(settings: Settings, processo: str) -> Path:
    """Grava ``<processo>-<pid>.json``: o commit e a hora em que este processo subiu."""
    if processo not in PROCESSOS:
        raise ValueError(f"processo '{processo}' desconhecido ({', '.join(PROCESSOS)})")
    agora = datetime.now(UTC)
    registro = Processo(
        processo=processo,
        pid=os.getpid(),
        commit=commit_do_git(settings.base_dir),
        subiu_em=agora.isoformat(),
        subiu_ts=agora.timestamp(),
    )
    pasta = _pasta(settings)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{processo}-{registro.pid}.json"
    arquivo.write_text(json.dumps(asdict(registro), ensure_ascii=False), encoding="utf-8")
    return arquivo


def remover_registro(settings: Settings, processo: str) -> None:
    with contextlib.suppress(OSError):
        (_pasta(settings) / f"{processo}-{os.getpid()}.json").unlink()


def _registros(settings: Settings) -> list[Processo]:
    pasta = _pasta(settings)
    encontrados = []
    for arquivo in sorted(pasta.glob("*.json")) if pasta.is_dir() else ():
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            registro = Processo(**dados)
        except (OSError, ValueError, TypeError):
            continue
        if not vivo(registro.pid):
            with contextlib.suppress(OSError):
                arquivo.unlink()  # o processo já morreu: o arquivo não diz mais nada
            continue
        encontrados.append(registro)
    return encontrados


def _hora(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).astimezone().strftime("%d/%m %H:%M")


def situacao(settings: Settings) -> dict[str, Any]:
    """O código de agora, os processos vivos e o aviso, se algum estiver desatualizado."""
    commit = commit_do_git(settings.base_dir)
    pacote = settings.base_dir / "assetflow"
    config = settings.config_dir
    codigo_ts = ultima_alteracao(pacote, config)
    config_ts = ultima_alteracao(config)
    processos = []
    avisos = []
    for registro in _registros(settings):
        motivo = None
        if commit and registro.commit and registro.commit != commit:
            motivo = f"subiu no commit {registro.commit}, e o código está no {commit}"
        else:
            limite = codigo_ts if registro.processo == "mcp" else config_ts
            if limite > registro.subiu_ts + 1:
                onde = "o código ou o config/" if registro.processo == "mcp" else "o config/"
                motivo = f"{onde} mudou às {_hora(limite)}, depois que ele subiu ({_hora(registro.subiu_ts)})"
        processos.append({**asdict(registro), "desatualizado": motivo is not None, "motivo": motivo})
        if motivo and registro.processo == "mcp":
            avisos.append(f"O servidor MCP {motivo}: reconecte pelo /mcp no Claude Code.")
        elif motivo:
            avisos.append(f"A API {motivo}: reinicie a API.")
    return {
        "codigo": {
            "commit": commit,
            "alterado_em": datetime.fromtimestamp(codigo_ts, UTC).isoformat() if codigo_ts else None,
        },
        "processos": processos,
        "aviso": " ".join(dict.fromkeys(avisos)) or None,
    }
