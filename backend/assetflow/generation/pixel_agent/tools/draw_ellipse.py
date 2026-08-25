"""``draw_ellipse`` — elipse na grade (plano de correção §16).

O círculo resolve bolha, cabeça e moeda; a elipse resolve o que é redondo mas
não é quadrado — copa larga e baixa, bojo de poção, sombra no chão, corpo de
slime. Sem ela, o plano teria de aproximar essas formas com dois círculos
sobrepostos, e a silhueta sairia com degraus onde deveria haver curva.

Mesma decisão do ``draw_circle``: teste de distância normalizada, não
algoritmo de ponto médio. Em raios de 3 a 8 pixels — a escala de tudo que se
desenha em 32×32 — o ponto médio produz cantos assimétricos, e o teste de
distância dá uma forma simétrica, que é o que o olho espera.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_ellipse"]


def draw_ellipse(canvas: PixelCanvas, **params: Any) -> int:
    """``{cx, cy, rx, ry, color, filled=True}``."""
    cx = as_int(params["cx"], "cx")
    cy = as_int(params["cy"], "cy")
    rx = as_int(params["rx"], "rx")
    ry = as_int(params["ry"], "ry")
    color = as_color(params["color"])
    filled = bool(params.get("filled", True))
    if rx < 0 or ry < 0:
        return 0

    # O +0.5 põe o teste no *centro* do pixel: sem ele, um raio inteiro corta
    # a coluna da borda pela metade e a elipse sai com as pontas achatadas.
    limit_x = rx + 0.5
    limit_y = ry + 0.5
    inner_x = rx - 0.5
    inner_y = ry - 0.5

    changed = 0
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            outside = _normalized(x - cx, y - cy, limit_x, limit_y) > 1.0
            if outside:
                continue
            if not filled and rx > 0 and ry > 0:
                if _normalized(x - cx, y - cy, inner_x, inner_y) < 1.0:
                    continue
            if canvas.set(x, y, color):
                changed += 1
    return changed


def _normalized(dx: int, dy: int, rx: float, ry: float) -> float:
    """``(dx/rx)² + (dy/ry)²`` — a equação da elipse, com raio zero tratado.

    Raio zero em um eixo é uma linha, não um erro: dividir por zero aqui
    derrubaria uma chamada perfeitamente razoável do plano.
    """
    if rx <= 0:
        return 0.0 if dx == 0 else float("inf")
    if ry <= 0:
        return 0.0 if dy == 0 else float("inf")
    return (dx / rx) ** 2 + (dy / ry) ** 2


draw_ellipse.name = "draw_ellipse"  # type: ignore[attr-defined]
