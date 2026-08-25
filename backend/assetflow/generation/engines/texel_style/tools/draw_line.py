"""``draw_line`` — segmento de reta na grade (plano de motores §9.3).

Bresenham, em inteiros. Não é nostalgia: qualquer traçado com ponto flutuante
produziria posições diferentes conforme o arredondamento, e o desenho deixaria
de ser reproduzível a partir do log de tool calls.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_line"]


def draw_line(canvas: PixelCanvas, **params: Any) -> int:
    """``{x0, y0, x1, y1, color}`` — extremos inclusivos."""
    x0 = as_int(params["x0"], "x0")
    y0 = as_int(params["y0"], "y0")
    x1 = as_int(params["x1"], "x1")
    y1 = as_int(params["y1"], "y1")
    color = as_color(params["color"])

    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    step_x = 1 if x0 < x1 else -1
    step_y = 1 if y0 < y1 else -1
    error = dx + dy

    changed = 0
    x, y = x0, y0
    while True:
        if canvas.set(x, y, color):
            changed += 1
        if x == x1 and y == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += step_x
        if doubled <= dx:
            error += dx
            y += step_y
    return changed


draw_line.name = "draw_line"  # type: ignore[attr-defined]
