"""``draw_pixel`` — pinta uma posição (plano de motores §9.3).

A ferramenta mais simples e a mais importante: é a que dá nome ao estilo. Um
alpha 0 aqui é um apagador, e é assim que o Review Loop remove pixel órfão sem
precisar de uma ferramenta nova.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_pixel"]


def draw_pixel(canvas: PixelCanvas, **params: Any) -> int:
    """``{x, y, color}``. Fora do canvas é ignorado, não é erro."""
    x = as_int(params["x"], "x")
    y = as_int(params["y"], "y")
    color = as_color(params["color"])
    return 1 if canvas.set(x, y, color) else 0


draw_pixel.name = "draw_pixel"  # type: ignore[attr-defined]
