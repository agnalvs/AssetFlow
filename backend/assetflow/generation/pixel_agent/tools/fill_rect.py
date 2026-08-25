"""``fill_rect`` — preenche um retângulo (plano de motores §9.3).

O retângulo é a forma que mais aparece em pixel art pequena: tronco de árvore,
corpo de baú, lâmina de espada, face de bloco. Coordenadas com fim
**inclusivo**, porque é assim que se pensa desenhando na grade — "da coluna 5
até a coluna 12" são oito colunas, não sete.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["fill_rect"]


def fill_rect(canvas: PixelCanvas, **params: Any) -> int:
    """``{x0, y0, x1, y1, color}`` — cantos inclusivos, em qualquer ordem."""
    x0 = as_int(params["x0"], "x0")
    y0 = as_int(params["y0"], "y0")
    x1 = as_int(params["x1"], "x1")
    y1 = as_int(params["y1"], "y1")
    color = as_color(params["color"])

    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0

    changed = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if canvas.set(x, y, color):
                changed += 1
    return changed


fill_rect.name = "fill_rect"  # type: ignore[attr-defined]
