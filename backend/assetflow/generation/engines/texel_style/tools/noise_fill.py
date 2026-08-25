"""``noise_fill_rect`` — textura pontilhada dentro de uma área (plano de motores §9.3).

O que ela resolve: uma copa de árvore preenchida com uma cor só parece um
adesivo. Duas ou três cores próximas salpicadas na mesma região criam a
leitura de volume que a pixel art consegue com pouquíssimos pixels.

O ruído é **semeado**: a mesma seed produz exatamente o mesmo salpicado. Sem
isso o engine deixaria de ser reproduzível — e reproduzir é metade do valor de
guardar um log de tool calls (§9.5).
"""

from __future__ import annotations

import random
from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["noise_fill_rect"]


def noise_fill_rect(canvas: PixelCanvas, **params: Any) -> int:
    """``{x0, y0, x1, y1, color, density=0.3, seed=0, only_over_opaque=False}``.

    ``only_over_opaque`` limita o ruído ao que já foi desenhado: é assim que a
    copa ganha textura sem espalhar pontos verdes no céu em volta dela.
    """
    x0 = as_int(params["x0"], "x0")
    y0 = as_int(params["y0"], "y0")
    x1 = as_int(params["x1"], "x1")
    y1 = as_int(params["y1"], "y1")
    color = as_color(params["color"])
    density = float(params.get("density", 0.3))
    seed = as_int(params.get("seed", 0), "seed")
    only_over_opaque = bool(params.get("only_over_opaque", False))

    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0

    rng = random.Random(seed)
    changed = 0
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            # O sorteio acontece para toda posição da área, inclusive as que
            # serão puladas: assim o padrão não "anda" quando
            # `only_over_opaque` muda o que é pintado, e duas execuções
            # continuam comparáveis pixel a pixel.
            draw = rng.random() < density
            if not draw:
                continue
            if only_over_opaque and not canvas.is_opaque(x, y):
                continue
            if canvas.set(x, y, color):
                changed += 1
    return changed


noise_fill_rect.name = "noise_fill_rect"  # type: ignore[attr-defined]
