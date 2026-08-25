"""``connect_cluster`` — liga um pedaço solto ao corpo (plano Optimizer §40).

O outro lado do ``erase_pixel``. Quando o revisor encontra um punhado de
pixels separados do resto, há duas correções possíveis e elas são opostas:
apagar (era ruído) ou ligar (era parte do desenho que se soltou na redução).

Quem decide é o planejador, com a regra do §17. Esta ferramenta só executa a
segunda: traça o caminho mais curto entre o pedaço e o corpo mais próximo.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["connect_cluster"]


def connect_cluster(canvas: PixelCanvas, **params: Any) -> int:
    """``{x, y, color}`` — liga o pixel a ``(x, y)`` ao opaco mais próximo."""
    x = as_int(params["x"], "x")
    y = as_int(params["y"], "y")
    color = as_color(params["color"])

    target = _nearest_opaque(canvas, x, y)
    if target is None:
        return 0

    changed = 0
    for px, py in _path(x, y, *target):
        if canvas.set(px, py, color):
            changed += 1
    return changed


def _nearest_opaque(
    canvas: PixelCanvas, x: int, y: int
) -> tuple[int, int] | None:
    """O pixel opaco mais próximo que **não** faz parte deste pedaço.

    "Não faz parte" é resolvido por distância: dois pixels a menos de duas
    posições um do outro são o mesmo pedaço, e ligá-los não conectaria nada.
    """
    best: tuple[int, int] | None = None
    best_distance = None
    for cx, cy, color in canvas:
        if color[3] == 0 or (cx == x and cy == y):
            continue
        distance = abs(cx - x) + abs(cy - y)
        if distance <= 1:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = (cx, cy), distance
    return best


def _path(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Bresenham em inteiros, como o resto do módulo."""
    points: list[tuple[int, int]] = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    step_x = 1 if x0 < x1 else -1
    step_y = 1 if y0 < y1 else -1
    error = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        doubled = 2 * error
        if doubled >= dy:
            error += dy
            x += step_x
        if doubled <= dx:
            error += dx
            y += step_y
    return points


connect_cluster.name = "connect_cluster"  # type: ignore[attr-defined]
