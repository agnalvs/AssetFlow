"""``draw_circle`` — círculo na grade, cheio ou só o contorno (plano de motores §9.3).

Implementado por teste de distância ao centro, e não pelo algoritmo do ponto
médio. A razão é específica de pixel art: em raios pequenos — 3, 4, 5 pixels,
que é a escala de uma copa de árvore em 32×32 — o ponto médio produz cantos
irregulares e assimétricos. O teste de distância dá um disco simétrico, que é
o que o olho espera de uma bolha desenhada à mão.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_circle"]


def draw_circle(canvas: PixelCanvas, **params: Any) -> int:
    """``{cx, cy, radius, color, filled=True}``."""
    cx = as_int(params["cx"], "cx")
    cy = as_int(params["cy"], "cy")
    radius = as_int(params["radius"], "radius")
    color = as_color(params["color"])
    filled = bool(params.get("filled", True))
    if radius < 0:
        return 0

    # O +0.5 põe o teste no *centro* do pixel: sem ele, um raio inteiro corta
    # a coluna da borda pela metade e o disco sai com as pontas achatadas.
    limit = (radius + 0.5) ** 2
    inner = (radius - 0.5) ** 2 if radius > 0 else -1.0

    changed = 0
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            distance = (x - cx) ** 2 + (y - cy) ** 2
            if distance > limit:
                continue
            if not filled and distance < inner:
                continue
            if canvas.set(x, y, color):
                changed += 1
    return changed


draw_circle.name = "draw_circle"  # type: ignore[attr-defined]
