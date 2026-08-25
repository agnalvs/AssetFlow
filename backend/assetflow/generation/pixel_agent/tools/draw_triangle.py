"""``draw_triangle`` — triângulo cheio (plano de motores §9.3).

Serve ao que retângulo e círculo não resolvem: telhado, ponta de espada, copa
de conífera. O preenchimento é por varredura com coordenadas baricêntricas em
inteiros — mesmo motivo do Bresenham em ``draw_line``: resultado idêntico a
cada execução, e portanto reproduzível a partir do log de tool calls.
"""

from __future__ import annotations

from typing import Any

from ..canvas import RGBA, PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_triangle"]


def draw_triangle(canvas: PixelCanvas, **params: Any) -> int:
    """``{x0, y0, x1, y1, x2, y2, color}``."""
    points = [
        (as_int(params["x0"], "x0"), as_int(params["y0"], "y0")),
        (as_int(params["x1"], "x1"), as_int(params["y1"], "y1")),
        (as_int(params["x2"], "x2"), as_int(params["y2"], "y2")),
    ]
    color = as_color(params["color"])

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)

    (ax, ay), (bx, by), (cx, cy) = points
    area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if area == 0:
        # Triângulo degenerado é uma reta. Desenhá-lo como reta é mais útil do
        # que não desenhar nada, e poupa o plano de desenho de um caso
        # especial para copas e telhados muito baixos.
        return _degenerate_line(canvas, points, color)

    changed = 0
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            w0 = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
            w1 = (cx - bx) * (y - by) - (cy - by) * (x - bx)
            w2 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx)
            inside = (w0 >= 0 and w1 >= 0 and w2 >= 0) or (
                w0 <= 0 and w1 <= 0 and w2 <= 0
            )
            if inside and canvas.set(x, y, color):
                changed += 1
    return changed


def _degenerate_line(
    canvas: PixelCanvas, points: list[tuple[int, int]], color: RGBA
) -> int:
    from .draw_line import draw_line

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return draw_line(
        canvas, x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys), color=color
    )


draw_triangle.name = "draw_triangle"  # type: ignore[attr-defined]
