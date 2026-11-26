"""``python -m assetflow.backup`` — cópia de segurança de ``backend/data/`` (lote 9).

    python -m assetflow.backup criar                 # grava o zip datado
    python -m assetflow.backup listar                # as cópias da pasta
    python -m assetflow.backup restaurar <zip>       # ensaio: confere e diz o que muda
    python -m assetflow.backup restaurar <zip> --sim # restaura (feche API e MCP antes)

A pasta das cópias é ``ASSETFLOW_BACKUP_DIR`` (padrão ``~/AssetFlow-copias``),
sempre fora do repositório.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..settings import load_settings
from .servico import (
    ErroDaCopia,
    criar_copia,
    listar_copias,
    pasta_das_copias,
    restaurar_copia,
)


def _mb(tamanho: int) -> str:
    return f"{tamanho / 1_048_576:.1f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m assetflow.backup", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("criar", help="grava a cópia de backend/data/")
    sub.add_parser("listar", help="as cópias da pasta")
    restaurar = sub.add_parser("restaurar", help="põe uma cópia no lugar")
    restaurar.add_argument("arquivo", type=Path)
    restaurar.add_argument("--sim", action="store_true", help="restaura de verdade (sem ele, é ensaio)")
    args = parser.parse_args(argv)

    settings = load_settings()
    try:
        if args.comando == "criar":
            copia = criar_copia(settings)
            print(f"cópia gravada: {copia.arquivo} ({copia.arquivos} arquivos, {_mb(copia.tamanho)})")
        elif args.comando == "listar":
            copias = listar_copias(settings)
            if not copias:
                print(f"nenhuma cópia em {pasta_das_copias(settings)}")
            for copia in copias:
                print(f"{copia.arquivo.name}  {copia.criada_em}  {copia.arquivos} arquivos  "
                      f"{_mb(copia.tamanho)}  commit {copia.commit or '?'}")
        else:
            feito = restaurar_copia(settings, args.arquivo, confirmar=args.sim)
            if feito.ensaio:
                print(f"ensaio: a cópia confere; voltariam {', '.join(feito.partes)}. "
                      "Feche a API e o servidor MCP e rode de novo com --sim.")
            else:
                print(f"restaurado: {', '.join(feito.partes)}. O que havia antes está em {feito.guardado_em}.")
    except ErroDaCopia as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
