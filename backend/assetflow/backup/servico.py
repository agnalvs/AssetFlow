"""A cópia de segurança de ``backend/data/`` (lote 9).

``backend/data/`` não vai ao git: se a pasta se perder, vão junto os desenhos,
a fila, as lições, as opiniões e a banca. A cópia é um zip datado, gravado
**fora do repositório** (``settings.backup.pasta``, por padrão
``~/AssetFlow-copias``), com:

    assets/        os PNG e relatórios de cada job
    history/       o histórico de gerações (a receita de cada asset)
    pedidos/       a fila (SQLite)
    aprendizado/   lições, opiniões e exemplos mostrados (SQLite)
    banca/         rodadas e votos (SQLite)
    referencias/   os pacotes importados à mão (com ``referencias: true``)
    copia.json     o que foi copiado, com tamanho e sha256 de cada arquivo

Ficam de fora os caches (``cache/``, ``engines/``: modelos da era da difusão,
vários GB), os logs e os relatórios de diagnóstico, que se refazem.

**Bancos de forma consistente.** Um SQLite em WAL é três arquivos: o banco, o
``-wal`` (o que foi gravado e ainda não voltou para o banco) e o ``-shm`` (um
índice do ``-wal``). Copiá-los soltos enquanto a API ou o MCP escrevem pode
pegar um no meio de uma gravação. Por isso cada banco sai pela cópia do próprio
SQLite (``Connection.backup``): um arquivo só, de um instante só, que **já
incorpora o conteúdo do ``-wal``**. O ``-shm`` não tem dado: o SQLite o refaz
ao abrir.

**Restaurar** confere os hashes, recusa se algum banco estiver em uso por outro
processo (feche a API e o servidor MCP antes) e não apaga nada: o que havia vai
para ``data/antes-da-restauracao-<data>/``.

Este módulo não importa API, MCP, gaveta nem jobs.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..settings import Settings

__all__ = [
    "BANCOS",
    "Copia",
    "ErroDaCopia",
    "Restauracao",
    "criar_copia",
    "listar_copias",
    "restaurar_copia",
]

#: Os bancos, pelo nome dentro do zip.
BANCOS = ("pedidos", "aprendizado", "banca")
PREFIXO = "assetflow-dados-"


class ErroDaCopia(RuntimeError):
    """A cópia ou a restauração não pôde ser feita; a mensagem diz por quê."""


@dataclass(frozen=True, slots=True)
class Copia:
    arquivo: Path
    criada_em: str
    tamanho: int
    arquivos: int
    commit: str | None = None


@dataclass(slots=True)
class Restauracao:
    copia: Path
    #: As partes que voltaram (``assets``, ``pedidos``…).
    partes: list[str] = field(default_factory=list)
    #: Onde ficou o que havia antes (``None`` num ensaio).
    guardado_em: Path | None = None
    ensaio: bool = True


# ---------------------------------------------------------------------------
# Onde mora cada parte
# ---------------------------------------------------------------------------
def _partes(settings: Settings) -> dict[str, Path]:
    """Nome dentro do zip -> caminho na instalação."""
    partes = {
        "assets": settings.storage_root,
        "history": settings.history_path.parent,
        "pedidos": settings.pedidos_path,
        "aprendizado": settings.aprendizado_path,
        "banca": settings.banca_path,
    }
    if settings.backup.referencias:
        partes["referencias"] = settings.referencias_dir
    return partes


def pasta_das_copias(settings: Settings) -> Path:
    return Path(settings.backup.pasta).expanduser().resolve()


def _dentro_do_repositorio(caminho: Path, settings: Settings) -> bool:
    raiz = settings.base_dir.resolve().parent  # backend/ -> a raiz do projeto
    try:
        caminho.resolve().relative_to(raiz)
    except ValueError:
        return False
    return True


def _commit(settings: Settings) -> str | None:
    try:
        saida = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=settings.base_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return saida.stdout.strip() or None


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos(pasta: Path) -> Iterator[Path]:
    if pasta.is_dir():
        yield from sorted(p for p in pasta.rglob("*") if p.is_file())


# ---------------------------------------------------------------------------
# Criar
# ---------------------------------------------------------------------------
def _copiar_banco(origem: Path, destino: Path, espera_s: float) -> None:
    """A cópia consistente de um SQLite em WAL: um arquivo, de um instante."""
    fonte = sqlite3.connect(f"file:{origem}?mode=ro", uri=True, timeout=espera_s)
    try:
        alvo = sqlite3.connect(destino)
        try:
            fonte.backup(alvo)
        finally:
            alvo.close()
    finally:
        fonte.close()


def criar_copia(settings: Settings, pasta: Path | None = None) -> Copia:
    """Grava o zip datado e devolve onde ficou."""
    destino = (pasta or pasta_das_copias(settings)).resolve()
    if _dentro_do_repositorio(destino, settings):
        raise ErroDaCopia(
            f"a pasta das cópias ({destino}) fica dentro do repositório; use uma fora dele "
            "(ASSETFLOW_BACKUP_DIR), para a cópia nunca ir parar no git"
        )
    destino.mkdir(parents=True, exist_ok=True)
    agora = datetime.now(UTC)
    carimbo = agora.astimezone().strftime("%Y%m%d-%H%M%S")
    arquivo = destino / f"{PREFIXO}{carimbo}.zip"
    numero = 1
    while arquivo.exists():
        numero += 1
        arquivo = destino / f"{PREFIXO}{carimbo}-{numero}.zip"

    itens: list[dict[str, Any]] = []
    temporario = arquivo.with_suffix(".zip.parcial")
    with tempfile.TemporaryDirectory() as provisoria, zipfile.ZipFile(
        temporario, "w", compression=zipfile.ZIP_DEFLATED
    ) as zip_:
        for nome, caminho in _partes(settings).items():
            if nome in BANCOS:
                if not caminho.is_file():
                    continue
                copia = Path(provisoria) / caminho.name
                _copiar_banco(caminho, copia, settings.pedidos.espera_s)
                interno = f"{nome}/{caminho.name}"
                zip_.write(copia, interno)
                itens.append({"caminho": interno, "tamanho": copia.stat().st_size,
                              "sha256": _sha256(copia), "banco": True})
                continue
            for item in _arquivos(caminho):
                interno = f"{nome}/{item.relative_to(caminho).as_posix()}"
                zip_.write(item, interno)
                itens.append({"caminho": interno, "tamanho": item.stat().st_size,
                              "sha256": _sha256(item)})
        manifesto = {
            "copia": arquivo.name,
            "criada_em": agora.isoformat(),
            "commit": _commit(settings),
            "partes": sorted({i["caminho"].split("/", 1)[0] for i in itens}),
            "arquivos": itens,
        }
        zip_.writestr("copia.json", json.dumps(manifesto, ensure_ascii=False, indent=2))
    temporario.replace(arquivo)
    return Copia(
        arquivo=arquivo,
        criada_em=manifesto["criada_em"],
        tamanho=arquivo.stat().st_size,
        arquivos=len(itens),
        commit=manifesto["commit"],
    )


def listar_copias(settings: Settings, pasta: Path | None = None) -> list[Copia]:
    """As cópias da pasta, da mais nova para a mais antiga."""
    destino = (pasta or pasta_das_copias(settings)).resolve()
    copias = []
    for arquivo in sorted(destino.glob(f"{PREFIXO}*.zip"), reverse=True) if destino.is_dir() else ():
        try:
            with zipfile.ZipFile(arquivo) as zip_:
                manifesto = json.loads(zip_.read("copia.json"))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            continue
        copias.append(
            Copia(
                arquivo=arquivo,
                criada_em=manifesto.get("criada_em", ""),
                tamanho=arquivo.stat().st_size,
                arquivos=len(manifesto.get("arquivos", [])),
                commit=manifesto.get("commit"),
            )
        )
    return copias


# ---------------------------------------------------------------------------
# Restaurar
# ---------------------------------------------------------------------------
def _em_uso(banco: Path) -> bool:
    """Outro processo tem o banco aberto numa transação? (Tenta a trava exclusiva.)"""
    if not banco.is_file():
        return False
    try:
        conexao = sqlite3.connect(banco, timeout=0.2)
    except sqlite3.Error:
        return True
    try:
        conexao.execute("BEGIN EXCLUSIVE")
        conexao.execute("ROLLBACK")
        return False
    except sqlite3.OperationalError:
        return True
    finally:
        conexao.close()


def restaurar_copia(settings: Settings, arquivo: Path, *, confirmar: bool = False) -> Restauracao:
    """Põe a cópia no lugar. Sem ``confirmar``, só confere e diz o que mudaria."""
    arquivo = Path(arquivo).expanduser().resolve()
    try:
        zip_ = zipfile.ZipFile(arquivo)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ErroDaCopia(f"'{arquivo}' não é uma cópia legível: {exc}") from exc
    with zip_:
        try:
            manifesto = json.loads(zip_.read("copia.json"))
        except KeyError as exc:
            raise ErroDaCopia(f"'{arquivo.name}' não tem copia.json: não é uma cópia do AssetFlow") from exc
        for item in manifesto["arquivos"]:
            if hashlib.sha256(zip_.read(item["caminho"])).hexdigest() != item["sha256"]:
                raise ErroDaCopia(f"'{item['caminho']}' não confere com o copia.json: a cópia está danificada")
        partes = _partes(settings)
        presentes = [p for p in manifesto.get("partes", []) if p in partes]
        resultado = Restauracao(copia=arquivo, partes=presentes, ensaio=not confirmar)
        if not confirmar:
            return resultado

        ocupados = [n for n in BANCOS if n in presentes and _em_uso(partes[n])]
        if ocupados:
            raise ErroDaCopia(
                f"os bancos {', '.join(ocupados)} estão em uso: feche a API e o servidor MCP "
                "(/mcp) antes de restaurar"
            )

        carimbo = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
        guarda = settings.data_dir / f"antes-da-restauracao-{carimbo}"
        guarda.mkdir(parents=True, exist_ok=False)
        for nome in presentes:
            caminho = partes[nome]
            if nome in BANCOS:
                for extra in (caminho, caminho.with_name(caminho.name + "-wal"),
                              caminho.with_name(caminho.name + "-shm")):
                    if extra.exists():
                        (guarda / nome).mkdir(exist_ok=True)
                        shutil.move(str(extra), guarda / nome / extra.name)
            elif caminho.exists():
                shutil.move(str(caminho), guarda / nome)
        for item in manifesto["arquivos"]:
            nome, resto = item["caminho"].split("/", 1)
            if nome not in presentes:
                continue
            alvo = partes[nome] if nome in BANCOS else partes[nome] / resto
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(zip_.read(item["caminho"]))
        resultado.guardado_em = guarda
        return resultado
