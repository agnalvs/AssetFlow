"""``set_pixel`` — pinta uma posição (plano Optimizer §40)."""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas
from .base import as_color, as_int

__all__ = ["set_pixel"]


def set_pixel(canvas: PixelCanvas, **params: Any) -> int:
    """``{x, y, color}``. Fora do canvas é ignorado, não é erro."""
    x = as_int(params["x"], "x")
    y = as_int(params["y"], "y")
    return 1 if canvas.set(x, y, as_color(params["color"])) else 0


set_pixel.name = "set_pixel"  # type: ignore[attr-defined]
