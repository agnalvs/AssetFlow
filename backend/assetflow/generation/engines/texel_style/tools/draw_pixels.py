"""``draw_pixels`` — pinta uma lista de posições com a mesma cor (plano de motores §9.3).

Existe por dois motivos, e nenhum deles é açúcar sintático: um plano de
desenho de 32×32 pode ter centenas de pixels avulsos, e registrá-los como
centenas de tool calls tornaria o log ilegível — que é justamente o artefato
que o §9.5 pede para guardar.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_pixels"]


def draw_pixels(canvas: PixelCanvas, **params: Any) -> int:
    """``{points: [[x, y], ...], color}``."""
    color = as_color(params["color"])
    changed = 0
    for index, point in enumerate(params.get("points") or ()):
        x = as_int(point[0], f"points[{index}].x")
        y = as_int(point[1], f"points[{index}].y")
        if canvas.set(x, y, color):
            changed += 1
    return changed


draw_pixels.name = "draw_pixels"  # type: ignore[attr-defined]
