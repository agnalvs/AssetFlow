"""``inspect_canvas`` — o Optimizer olha o sprite inteiro (§40).

Não altera nada. Devolve medidas — ocupação, cores, caixa do conteúdo, pixels
órfãos —, que é o bastante para as perguntas que o revisor faz.
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas

__all__ = ["inspect_canvas"]


def inspect_canvas(canvas: PixelCanvas, **params: Any) -> int:
    """Devolve ``0``: o retrato é lido pelo executor, que o grava no log."""
    return 0


inspect_canvas.name = "inspect_canvas"  # type: ignore[attr-defined]
