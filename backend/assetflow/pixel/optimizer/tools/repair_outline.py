"""``repair_outline`` — fecha o contorno da silhueta (plano Optimizer §40).

O reparo mais frequente em saída de modelo de difusão reduzida: o contorno
existe em quase toda a volta e falha em alguns pontos, e um contorno
interrompido faz o sprite vazar no fundo exatamente ali.

A ferramenta pinta as posições **vazias que encostam em pixel opaco não
contornado**. Ela não engorda um contorno que já está fechado: um sprite
contornado não tem cor exposta na fronteira, e o laço percebe isso e não faz
nada — é o que impede o reparo de crescer o sprite a cada volta.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color

__all__ = ["repair_outline"]


def repair_outline(canvas: PixelCanvas, **params: Any) -> int:
    """``{color}`` — e, opcionalmente, ``{only: [[x, y], ...]}``.

    Sem ``only``, remenda a silhueta inteira. Com ``only``, corrige apenas as
    posições que o planejador listou — que é como um reparo localizado não
    vira uma repintura do sprite.
    """
    color = as_color(params["color"])
    only = params.get("only")

    if only is not None:
        positions = [(int(point[0]), int(point[1])) for point in only]
    else:
        positions = _exposed(canvas, color)

    changed = 0
    for x, y in positions:
        if canvas.set(x, y, color):
            changed += 1
    return changed


def _exposed(canvas: PixelCanvas, outline) -> list[tuple[int, int]]:
    """Vazios que encostam em pixel opaco que **não** é o contorno."""
    found: list[tuple[int, int]] = []
    for x, y, color in canvas:
        if color[3] != 0:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = canvas.get(x + dx, y + dy)
            if neighbour[3] > 0 and neighbour != outline:
                found.append((x, y))
                break
    return found


repair_outline.name = "repair_outline"  # type: ignore[attr-defined]
