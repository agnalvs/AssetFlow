"""``inspect_canvas`` — o agente olha o que desenhou (plano de correção §16 e §23).

É a única ferramenta que não pinta, e é ela que fecha o laço da revisão: sem
poder inspecionar o canvas, a revisão seria uma lista de correções escrita às
cegas.

Ela devolve medidas, não pixels — ocupação, número de cores, caixa do
conteúdo, pixels órfãos. É o bastante para as perguntas que o revisor faz:
está vazio demais? passou do orçamento de cores? sobrou sujeira solta? o
desenho encosta na borda?
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas

__all__ = ["inspect_canvas"]


def inspect_canvas(canvas: PixelCanvas, **params: Any) -> int:
    """Não altera nada; devolve ``0`` para caber no contrato das ferramentas.

    O retrato em si é lido pelo executor, que grava ``canvas.stats()`` no
    registro da chamada. Manter a assinatura idêntica à das outras ferramentas
    é o que faz a inspeção aparecer no histórico na ordem exata em que
    aconteceu, entre as pinceladas.
    """
    return 0


inspect_canvas.name = "inspect_canvas"  # type: ignore[attr-defined]
