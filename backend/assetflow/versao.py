"""Em que versão do código o AssetFlow está (lotes 1 e 11).

O commit é lido do ``.git`` sem chamar o ``git``: a banca grava com qual base a
rodada foi desenhada, e a API e o servidor MCP gravam em que commit subiram.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["commit_do_git", "ultima_alteracao"]


def commit_do_git(raiz: Path) -> str | None:
    """O commit em que o repositório está (7 caracteres), lido do ``.git``."""
    for pasta in (raiz, *raiz.parents):
        git = pasta / ".git"
        if not git.is_dir():
            continue
        try:
            cabeca = (git / "HEAD").read_text(encoding="utf-8").strip()
            if not cabeca.startswith("ref:"):
                return cabeca[:7]
            ref = cabeca.split(":", 1)[1].strip()
            arquivo = git / ref
            if arquivo.is_file():
                return arquivo.read_text(encoding="utf-8").strip()[:7]
            empacotadas = git / "packed-refs"
            if empacotadas.is_file():
                for linha in empacotadas.read_text(encoding="utf-8").splitlines():
                    if linha.endswith(" " + ref):
                        return linha.split(" ", 1)[0][:7]
        except OSError:
            return None
        return None
    return None


def ultima_alteracao(*pastas: Path, sufixos: tuple[str, ...] = (".py", ".yaml", ".json")) -> float:
    """O ``mtime`` mais recente dos arquivos de código e configuração das pastas.

    O servidor MCP carrega o código e o ``config/`` uma vez, quando sobe; a API
    só recarrega ``*.py``. Um arquivo alterado depois da subida é código que o
    processo não está rodando, mesmo sem commit novo.
    """
    mais_recente = 0.0
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for arquivo in pasta.rglob("*"):
            if arquivo.suffix in sufixos and "__pycache__" not in arquivo.parts:
                try:
                    mais_recente = max(mais_recente, arquivo.stat().st_mtime)
                except OSError:
                    continue
    return mais_recente
