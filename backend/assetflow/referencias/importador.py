"""Importar um pacote baixado à mão e medi-lo.

Arquivo baixado é dado não confiável. Por isso:

- o zip nunca é extraído inteiro: cada entrada é conferida e copiada para
  dentro de ``original/``; caminho absoluto, com ``..`` ou com letra de drive
  é recusado;
- só entram PNGs que casam com alguma parte do manifesto, mais os textos de
  licença e leia-me — e há teto de arquivos, de bytes e de pixels;
- lixo de sistema (``__MACOSX/``, ``._*``, ``.DS_Store``) é ignorado.

Nada é baixado da internet: a origem é sempre um zip ou uma pasta local.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from .medidor import (
    carregar_com_fundo,
    detectar_escala,
    fatiar,
    medir_quadro,
    quadro_do_nome,
)
from .pacote import (
    Manifesto,
    Parte,
    ReferenciaInvalida,
    ler_manifesto,
    normalizar_licenca,
)

__all__ = ["MAX_ARQUIVOS", "MAX_BYTES", "Importacao", "importar", "medir_pacote"]

#: Tetos por importação. Um pacote de verdade fica muito abaixo deles.
MAX_ARQUIVOS = 5000
MAX_BYTES = 400 * 1024 * 1024
_TEXTO_MAX = 1024 * 1024

_TEXTO_DE_LICENCA = re.compile(r"(?i)(licen|readme|leia|credit|copying|terms)[^/]*\.(txt|md)$")
_SEQUENCIA = re.compile(r"(?i)^(.*?)[\s_-]*(?:f|frame)?[\s_-]*(\d+)$")


@dataclass
class Importacao:
    """O que aconteceu numa importação, para a saída do comando."""

    pacote: str
    copiados: int = 0
    textos: int = 0
    #: Arquivos que casariam com uma parte, mas casam com ``excluir``.
    excluidos: int = 0
    ignorados: Counter = field(default_factory=Counter)
    recusados: list[str] = field(default_factory=list)
    medicao: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Importar
# ---------------------------------------------------------------------------
def importar(
    origem: Path,
    raiz: Path,
    *,
    pacote: str,
    fonte: str,
    autor: str,
    licenca: str,
    licenca_url: str,
    partes: tuple[Parte, ...],
    excluir: tuple[str, ...] = (),
    nome: str = "",
    verificada_em: str | None = None,
    observacoes: str = "",
    substituir: bool = False,
) -> Importacao:
    """Copia as partes escolhidas de ``origem`` para ``raiz/<pacote>`` e mede."""
    if not origem.exists():
        raise ReferenciaInvalida(f"origem '{origem}' não existe")
    manifesto = Manifesto(
        id=pacote,
        nome=nome or pacote,
        source_url=fonte,
        autor=autor,
        license_id=normalizar_licenca(licenca),
        license_url=licenca_url,
        # Sem data informada, vale hoje no fuso de quem importa.
        license_verified_at=verificada_em or datetime.now(UTC).astimezone().date().isoformat(),
        partes=partes,
        observacoes=observacoes,
        importado_em=datetime.now(UTC).isoformat(timespec="seconds"),
        origem=origem.name,
        origem_sha256=_sha256(origem) if origem.is_file() else "",
        excluir=excluir,
    )

    destino = raiz / pacote
    if destino.exists():
        if not substituir:
            raise ReferenciaInvalida(
                f"o pacote '{pacote}' já existe em {destino}; use --substituir para importar de novo"
            )
        shutil.rmtree(destino)
    copias = destino / "original"
    copias.mkdir(parents=True)

    relatorio = Importacao(pacote=pacote)
    total = 0
    for caminho, abrir, tamanho in _entradas(origem):
        relativo = _seguro(caminho)
        if relativo is None:
            relatorio.recusados.append(caminho)
            continue
        if _lixo(relativo):
            continue
        texto = _TEXTO_DE_LICENCA.search(relativo.name) is not None and tamanho <= _TEXTO_MAX
        imagem = relativo.suffix.lower() == ".png" and manifesto.parte_de(str(relativo)) is not None
        if (
            relativo.suffix.lower() == ".png"
            and manifesto.excluido(str(relativo))
            and any(parte.casa(str(relativo)) for parte in manifesto.partes)
        ):
            relatorio.excluidos += 1
            continue
        if not (texto or imagem):
            relatorio.ignorados[relativo.suffix.lower() or "(sem extensão)"] += 1
            continue
        total += tamanho
        if relatorio.copiados + relatorio.textos >= MAX_ARQUIVOS or total > MAX_BYTES:
            raise ReferenciaInvalida(
                f"o pacote passa do teto ({MAX_ARQUIVOS} arquivos ou {MAX_BYTES // 2**20} MB); "
                "importe uma parte com --parte"
            )
        alvo = copias / relativo
        if copias.resolve() not in alvo.resolve().parents:  # defesa em dobro
            relatorio.recusados.append(caminho)
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        with abrir() as dados, alvo.open("wb") as saida:
            shutil.copyfileobj(dados, saida)
        if imagem:
            relatorio.copiados += 1
        else:
            relatorio.textos += 1

    if not relatorio.copiados:
        shutil.rmtree(destino)
        raise ReferenciaInvalida(
            "nenhum PNG casou com as partes informadas; confira os padrões de --parte "
            "(relativos à raiz do zip ou da pasta, com /)"
        )
    manifesto.gravar(destino)
    try:
        relatorio.medicao = medir_pacote(destino)
    except Exception:
        # Pacote pela metade não fica para trás: a próxima tentativa começa limpa.
        shutil.rmtree(destino, ignore_errors=True)
        raise
    return relatorio


def _entradas(origem: Path) -> Iterator[tuple[str, Callable[[], Any], int]]:
    if origem.is_dir():
        for arquivo in sorted(origem.rglob("*")):
            if arquivo.is_file() and not arquivo.is_symlink():
                yield (
                    arquivo.relative_to(origem).as_posix(),
                    lambda arquivo=arquivo: arquivo.open("rb"),
                    arquivo.stat().st_size,
                )
        return
    if not zipfile.is_zipfile(origem):
        raise ReferenciaInvalida(f"'{origem.name}' não é zip nem pasta")
    with zipfile.ZipFile(origem) as arquivo_zip:
        for info in arquivo_zip.infolist():
            if info.is_dir():
                continue
            yield info.filename, (lambda info=info: arquivo_zip.open(info)), info.file_size


def _seguro(caminho: str) -> PurePosixPath | None:
    """O caminho relativo, ou ``None`` se ele tentar sair da pasta."""
    normal = caminho.replace("\\", "/")
    if normal.startswith("/") or re.match(r"^[A-Za-z]:", normal):
        return None
    relativo = PurePosixPath(normal)
    if not relativo.parts or any(parte in ("..", "") for parte in relativo.parts):
        return None
    return relativo


def _lixo(relativo: PurePosixPath) -> bool:
    return (
        "__MACOSX" in relativo.parts
        or relativo.name.startswith("._")
        or relativo.name in {".DS_Store", "Thumbs.db"}
    )


def _sha256(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with arquivo.open("rb") as dados:
        for bloco in iter(lambda: dados.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


# ---------------------------------------------------------------------------
# Medir
# ---------------------------------------------------------------------------
def medir_pacote(pasta: Path) -> dict[str, Any]:
    """Mede todos os PNGs de ``original/`` e grava ``medidas.json``.

    O mesmo quadro aparece muitas vezes num pacote — no arquivo individual e
    de novo no atlas. Ele é medido **uma** vez, pelo conteúdo, e de
    preferência a partir do arquivo individual: entre cópias, ganha o arquivo
    com menos quadros.
    """
    manifesto = ler_manifesto(pasta)
    originais = pasta / "original"
    candidatos: list[tuple[int, str, int, dict[str, Any]]] = []
    animacoes: list[dict[str, Any]] = []
    ignorados: list[dict[str, str]] = []
    individuais: dict[tuple[str, str], list[str]] = defaultdict(list)

    for arquivo in sorted(originais.rglob("*.png")):
        relativo = arquivo.relative_to(originais).as_posix()
        parte = manifesto.parte_de(relativo)
        if parte is None:
            continue
        try:
            rgba, fundo = carregar_com_fundo(arquivo)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:  # corrompida ou grande
            ignorados.append({"arquivo": relativo, "motivo": str(exc)})
            continue
        escala = detectar_escala(rgba)
        if escala > 1:
            rgba = rgba[::escala, ::escala]
        quadro = parte.quadro or quadro_do_nome(arquivo.name)
        recortes = fatiar(rgba, quadro)
        if not recortes:
            ignorados.append({"arquivo": relativo, "motivo": "imagem vazia"})
            continue

        if len(recortes) > 1:
            por_linha = Counter(r.linha for r in recortes)
            nome = re.sub(r"\s*\(\d+\s*x\s*\d+\)", "", arquivo.stem, flags=re.IGNORECASE).strip()
            for linha, frames in sorted(por_linha.items()):
                animacoes.append({
                    "arquivo": relativo,
                    "nome": nome if len(por_linha) == 1 else f"{nome} · linha {linha + 1}",
                    "frames": frames,
                    "tipo": parte.tipo,
                })
        else:
            casou = _SEQUENCIA.match(arquivo.stem)
            if casou and casou.group(1):
                individuais[(str(PurePosixPath(relativo).parent), casou.group(1))].append(relativo)

        for indice, recorte in enumerate(recortes):
            pedaco = rgba[recorte.y : recorte.y + recorte.altura, recorte.x : recorte.x + recorte.largura]
            medidas = medir_quadro(pedaco, conhecido=recorte.conhecido)
            if medidas is None:
                continue
            medidas.update(
                arquivo=relativo,
                indice=indice,
                caixa=[recorte.x, recorte.y, recorte.largura, recorte.altura],
                quadro_conhecido=recorte.conhecido,
                escala=escala,
                tipo=parte.tipo,
                corpo=parte.corpo,
                fundo_removido=fundo,
            )
            candidatos.append((len(recortes), relativo, indice, medidas))

    for (pasta_rel, nome), arquivos in sorted(individuais.items()):
        if len(arquivos) > 1:
            parte = manifesto.parte_de(arquivos[0])
            animacoes.append({
                "arquivo": f"{pasta_rel}/{nome}*" if pasta_rel != "." else f"{nome}*",
                "nome": nome,
                "frames": len(arquivos),
                "tipo": parte.tipo if parte else None,
            })

    quadros, repetidos = [], 0
    vistos: set[str] = set()
    for _, _, _, medidas in sorted(candidatos, key=lambda c: (c[0], c[1], c[2])):
        if medidas["hash"] in vistos:
            repetidos += 1
            continue
        vistos.add(medidas["hash"])
        quadros.append(medidas)

    resultado = {
        "versao": 1,
        "pacote": manifesto.id,
        "medido_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "quadros": quadros,
        "repetidos": repetidos,
        "animacoes": animacoes,
        "ignorados": ignorados,
    }
    (pasta / "medidas.json").write_text(
        json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return {
        "quadros": len(quadros),
        "repetidos": repetidos,
        "animacoes": len(animacoes),
        "ignorados": len(ignorados),
        "por_tipo": dict(Counter(q["tipo"] for q in quadros)),
    }
