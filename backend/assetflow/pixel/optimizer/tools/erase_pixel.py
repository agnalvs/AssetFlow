"""``erase_pixel`` — apaga uma posição (plano Optimizer §40).

Existe separado de ``set_pixel`` com alpha 0 porque a **intenção** é outra, e
a intenção é o que fica no log. "Apaguei o pixel (6,17) porque era ruído" se
lê; "pintei (6,17) de transparente" faz o leitor traduzir.
"""

from __future__ import annotations

from typing import Any

from ..canvas import TRANSPARENT, PixelCanvas
from .base import as_int

__all__ = ["erase_pixel"]


def erase_pixel(canvas: PixelCanvas, **params: Any) -> int:
    """``{x, y}``."""
    x = as_int(params["x"], "x")
    y = as_int(params["y"], "y")
    return 1 if canvas.set(x, y, TRANSPARENT) else 0


erase_pixel.name = "erase_pixel"  # type: ignore[attr-defined]
