"""``draw_pixels`` — pinta uma lista de posições (plano Optimizer §40).

O reparo em lote. Um contorno remendado pode envolver dezenas de posições, e
registrá-las como dezenas de ações tornaria ``optimizer_actions.json``
ilegível — que é justamente o artefato que o §47 pede para guardar.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["draw_pixels"]


def draw_pixels(canvas: PixelCanvas, **params: Any) -> int:
    """``{pixels: [[x, y], ...], color}``.

    Aceita também ``points``: o vocabulário do §12 diz ``pixels`` e o resto do
    sistema já dizia ``points``, e recusar um plano por causa do sinônimo
    custaria mais do que aceitá-lo.
    """
    color = as_color(params["color"])
    raw = params.get("pixels")
    if raw is None:
        raw = params.get("points") or ()

    changed = 0
    for index, point in enumerate(raw):
        x = as_int(point[0], f"pixels[{index}].x")
        y = as_int(point[1], f"pixels[{index}].y")
        if canvas.set(x, y, color):
            changed += 1
    return changed


draw_pixels.name = "draw_pixels"  # type: ignore[attr-defined]
