"""``replace_color`` — troca todos os pixels de uma cor (plano Optimizer §40).

A ferramenta de paleta. Ela é como uma cor a mais é absorvida sem que o sprite
perca a forma: em vez de apagar os pixels sobressalentes, eles passam a usar
uma cor que já está em uso.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color

__all__ = ["replace_color"]


def replace_color(canvas: PixelCanvas, **params: Any) -> int:
    """``{from_color, to_color}``."""
    source = as_color(params.get("from_color") or params["from"])
    target = as_color(params.get("to_color") or params["to"])
    if source == target:
        return 0

    changed = 0
    for x, y, current in list(canvas):
        if current == source and canvas.set(x, y, target):
            changed += 1
    return changed


replace_color.name = "replace_color"  # type: ignore[attr-defined]
