"""Rodadas e votos da banca, num SQLite em ``data/banca/``.

Mesmas regras de :mod:`assetflow.sqlite_curto` da fila e das lições: a API
cria rodadas e grava votos; o arquivo nunca é apagado.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..sqlite_curto import BancoCurto

__all__ = ["BancaIndisponivel", "CaixaDaBanca", "ErroDaBanca", "Rodada", "RodadaNaoEncontrada", "Voto"]

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS rodadas (
    numero        INTEGER PRIMARY KEY AUTOINCREMENT,
    rotulo        TEXT NOT NULL,
    modo_conceito TEXT NOT NULL,
    criada_em     TEXT NOT NULL,
    versao_base   TEXT NOT NULL,
    git_commit    TEXT,
    interruptores TEXT NOT NULL DEFAULT '{}',
    licoes        TEXT NOT NULL DEFAULT '[]',
    itens         TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS votos (
    a             TEXT NOT NULL,
    b             TEXT NOT NULL,
    item          TEXT NOT NULL,
    esquerda      TEXT NOT NULL,
    escolha       TEXT NOT NULL,
    nota_esquerda INTEGER NOT NULL,
    nota_direita  INTEGER NOT NULL,
    em            TEXT NOT NULL,
    PRIMARY KEY (a, b, item)
);
"""


class ErroDaBanca(Exception):
    codigo = "banca_indisponivel"


class BancaIndisponivel(ErroDaBanca):
    codigo = "banca_indisponivel"


class RodadaNaoEncontrada(ErroDaBanca):
    codigo = "rodada_nao_encontrada"


@dataclass(frozen=True, slots=True)
class Rodada:
    numero: int
    rotulo: str
    modo_conceito: str
    criada_em: datetime
    versao_base: str
    git_commit: str | None
    interruptores: dict[str, Any]
    licoes: list[dict[str, Any]]
    #: ``[{"item", "pedido_id", "ordem"}]``
    itens: list[dict[str, Any]]

    @property
    def id(self) -> str:
        return f"R{self.numero}"


@dataclass(frozen=True, slots=True)
class Voto:
    a: str
    b: str
    item: str
    #: A rodada que ficou à esquerda.
    esquerda: str
    #: ``esquerda``, ``direita`` ou ``empate``.
    escolha: str
    nota_esquerda: int
    nota_direita: int


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class CaixaDaBanca:
    def __init__(self, caminho: Path, *, espera_s: float = 5.0) -> None:
        self._caminho = Path(caminho)
        self._espera_s = espera_s
        self._banco = BancoCurto(self._caminho, esquema=_ESQUEMA, traduzir=self._traduzir, espera_s=espera_s)

    @contextmanager
    def _conexao(self) -> Iterator[sqlite3.Connection]:
        with self._banco.conexao() as conexao:
            yield conexao

    def _traduzir(self, exc: Exception) -> ErroDaBanca:
        return BancaIndisponivel(f"a banca de teste não respondeu ({self._caminho}): {exc}")

    def nova_rodada(
        self,
        *,
        rotulo: str,
        modo_conceito: str,
        versao_base: str,
        git_commit: str | None,
        interruptores: dict[str, Any],
        licoes: list[dict[str, Any]],
    ) -> Rodada:
        with self._conexao() as conexao:
            linha = conexao.execute(
                """
                INSERT INTO rodadas (rotulo, modo_conceito, criada_em, versao_base, git_commit,
                                     interruptores, licoes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING *
                """,
                (
                    rotulo,
                    modo_conceito,
                    _agora(),
                    versao_base,
                    git_commit,
                    json.dumps(interruptores, ensure_ascii=False),
                    json.dumps(licoes, ensure_ascii=False),
                ),
            ).fetchall()[0]
        return _rodada(linha)

    def gravar_itens(self, numero: int, itens: list[dict[str, Any]]) -> Rodada:
        with self._conexao() as conexao:
            linha = conexao.execute(
                "UPDATE rodadas SET itens = ? WHERE numero = ? RETURNING *",
                (json.dumps(itens, ensure_ascii=False), numero),
            ).fetchall()
        if not linha:
            raise RodadaNaoEncontrada(f"não há rodada R{numero}")
        return _rodada(linha[0])

    def rodadas(self) -> list[Rodada]:
        with self._conexao() as conexao:
            linhas = conexao.execute("SELECT * FROM rodadas ORDER BY numero DESC").fetchall()
        return [_rodada(linha) for linha in linhas]

    def rodada(self, rodada: str | int) -> Rodada:
        numero = _numero(rodada)
        with self._conexao() as conexao:
            linha = conexao.execute("SELECT * FROM rodadas WHERE numero = ?", (numero,)).fetchone()
        if linha is None:
            raise RodadaNaoEncontrada(f"não há rodada R{numero}")
        return _rodada(linha)

    def votar(self, voto: Voto) -> Voto:
        with self._conexao() as conexao:
            conexao.execute(
                """
                INSERT INTO votos (a, b, item, esquerda, escolha, nota_esquerda, nota_direita, em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(a, b, item) DO UPDATE SET
                    esquerda = excluded.esquerda, escolha = excluded.escolha,
                    nota_esquerda = excluded.nota_esquerda, nota_direita = excluded.nota_direita,
                    em = excluded.em
                """,
                (
                    voto.a, voto.b, voto.item, voto.esquerda, voto.escolha,
                    int(voto.nota_esquerda), int(voto.nota_direita), _agora(),
                ),
            ).fetchall()
        return voto

    def votos(self, a: str, b: str) -> dict[str, Voto]:
        with self._conexao() as conexao:
            linhas = conexao.execute("SELECT * FROM votos WHERE a = ? AND b = ?", (a, b)).fetchall()
        return {
            linha["item"]: Voto(
                a=linha["a"], b=linha["b"], item=linha["item"], esquerda=linha["esquerda"],
                escolha=linha["escolha"], nota_esquerda=int(linha["nota_esquerda"]),
                nota_direita=int(linha["nota_direita"]),
            )
            for linha in linhas
        }


def _numero(rodada: str | int) -> int:
    texto = str(rodada).strip().upper().lstrip("R")
    if not texto.isdigit():
        raise RodadaNaoEncontrada(f"'{rodada}' não é uma rodada (como R1)")
    return int(texto)


def _rodada(linha: sqlite3.Row) -> Rodada:
    return Rodada(
        numero=int(linha["numero"]),
        rotulo=linha["rotulo"],
        modo_conceito=linha["modo_conceito"],
        criada_em=datetime.fromisoformat(linha["criada_em"]),
        versao_base=linha["versao_base"],
        git_commit=linha["git_commit"],
        interruptores=json.loads(linha["interruptores"] or "{}"),
        licoes=json.loads(linha["licoes"] or "[]"),
        itens=json.loads(linha["itens"] or "[]"),
    )
