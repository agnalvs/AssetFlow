"""``inspect_region`` — o Optimizer olha um pedaço (plano Optimizer §40).

Existe porque um problema tem lugar. "A copa da esquerda está fragmentada" é
uma afirmação sobre uma região, e confirmá-la olhando o canvas inteiro
misturaria a copa com o tronco.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_int

__all__ = ["inspect_region"]


def inspect_region(canvas: PixelCanvas, **params: Any) -> int:
    """``{x0, y0, x1, y1}``. Não altera nada."""
    for key in ("x0", "y0", "x1", "y1"):
        as_int(params[key], key)
    return 0


inspect_region.name = "inspect_region"  # type: ignore[attr-defined]
