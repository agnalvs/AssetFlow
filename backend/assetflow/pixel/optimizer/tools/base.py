"""O contrato de uma ferramenta de reparo (plano Optimizer §13 e §15).

Uma ferramenta recebe o canvas e parâmetros nomeados, altera pixels, e devolve
quantos mudaram. Ela não sabe o que está sendo corrigido nem por quê: quem
diagnostica é o :mod:`..reviewer`, quem decide é o :mod:`..planner`.
"""

from __future__ import annotations

from typing import Any

from ..canvas import RGBA
from ..palette import as_rgba

__all__ = ["as_color", "as_int"]


def as_color(value: Any) -> RGBA:
    """Normaliza cor para ``(r, g, b, a)``.

    Aceita ``#rgb``, ``#rrggbb``, ``#rrggbbaa`` e tuplas. A tupla já
    normalizada passa direto — é o que o :class:`..palette.PaletteGuard`
    devolve depois de aprovar a cor.
    """
    return as_rgba(value)


def as_int(value: Any, name: str) -> int:
    """Uma coordenada inteira — e **só** inteira (plano Optimizer §15).

    ``13.5`` é recusado em vez de virar ``13``. Em uma grade de 32×32 meio
    pixel não existe, e truncar em silêncio esconderia um erro de planejamento
    até ele aparecer na imagem — quando já não há como saber qual ação o
    causou.

    ``13.0`` passa: é um inteiro escrito como float, o que acontece o tempo
    todo quando o plano vem de JSON.
    """
    if isinstance(value, bool):
        # `bool` é `int` em Python, e "corrija a coluna True" é sempre um bug.
        raise ValueError(f"parâmetro '{name}' precisa ser inteiro: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(
                f"parâmetro '{name}' não aceita coordenada fracionária: "
                f"{value!r} — a grade não tem meio pixel"
            )
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return as_int(float(text), name)
        except ValueError as exc:
            if "fracion" in str(exc):
                raise
            raise ValueError(
                f"parâmetro '{name}' precisa ser inteiro: {value!r}"
            ) from exc
    raise ValueError(f"parâmetro '{name}' precisa ser inteiro: {value!r}")
