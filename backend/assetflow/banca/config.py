"""Os pedidos da banca (``config/banca.yaml``) e a versão da base de uma rodada."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "Banca",
    "BancaInvalida",
    "ItemDaBanca",
    "commit_do_git",
    "impressao_da_base",
    "ler_banca",
]


class BancaInvalida(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ItemDaBanca:
    id: str
    texto: str
    perfil: str
    testa: str = ""


@dataclass(frozen=True, slots=True)
class Banca:
    itens: tuple[ItemDaBanca, ...]
    liberdade: str = "equilibrado"


def ler_banca(caminho: Path) -> Banca:
    """Lê ``config/banca.yaml``; erro claro se faltar ou estiver torto."""
    if not caminho.is_file():
        raise BancaInvalida(f"não há banca configurada: falta {caminho}")
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise BancaInvalida(f"{caminho.name}: {exc}") from exc
    if not isinstance(dados, Mapping):
        raise BancaInvalida(f"{caminho.name}: a raiz não é um mapeamento")
    itens = []
    vistos: set[str] = set()
    for i, bruto in enumerate(dados.get("itens") or []):
        if not isinstance(bruto, Mapping):
            raise BancaInvalida(f"{caminho.name}: itens[{i}] não é um mapeamento")
        item = ItemDaBanca(
            id=str(bruto.get("id") or "").strip(),
            texto=str(bruto.get("texto") or "").strip(),
            perfil=str(bruto.get("perfil") or "").strip(),
            testa=str(bruto.get("testa") or "").strip(),
        )
        if not (item.id and item.texto and item.perfil):
            raise BancaInvalida(f"{caminho.name}: itens[{i}] precisa de id, texto e perfil")
        if item.id in vistos:
            raise BancaInvalida(f"{caminho.name}: id '{item.id}' repetido")
        vistos.add(item.id)
        itens.append(item)
    if not itens:
        raise BancaInvalida(f"{caminho.name}: a banca não tem itens")
    return Banca(itens=tuple(itens), liberdade=str(dados.get("liberdade") or "equilibrado"))


def impressao_da_base(diretorio: Path, extras: Mapping[str, Any] | None = None) -> str:
    """Uma impressão (12 hexadecimais) de ``config/pixel_knowledge/`` e dos interruptores.

    Muda quando qualquer arquivo da base muda, ou quando um interruptor muda.
    É o que liga uma rodada a "uma versão da base", sem a base ter versão.
    """
    soma = hashlib.sha256()
    if diretorio.is_dir():
        for arquivo in sorted(p for p in diretorio.rglob("*") if p.is_file()):
            soma.update(arquivo.relative_to(diretorio).as_posix().encode("utf-8"))
            soma.update(b"\0")
            soma.update(arquivo.read_bytes())
    for chave, valor in sorted((extras or {}).items()):
        soma.update(f"{chave}={valor}".encode())
    return soma.hexdigest()[:12]


def commit_do_git(raiz: Path) -> str | None:
    """O commit em que o repositório está, lido do ``.git`` sem chamar o git."""
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
