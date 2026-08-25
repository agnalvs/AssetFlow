"""``view_canvas`` — o agente olha o que desenhou (plano de motores §9.3 e §9.4).

É a única ferramenta que não pinta, e é ela que fecha o laço da etapa 4: sem
poder inspecionar o canvas, a revisão seria uma lista de correções escrita às
cegas.

Ela devolve medidas, não pixels — ocupação, número de cores, caixa do
conteúdo, pixels órfãos. É o bastante para responder as três perguntas que o
Review Loop faz: está vazio demais? passou do orçamento de cores? sobrou
sujeira solta?
"""

from __future__ import annotations

from typing import Any

from ..canvas import PixelCanvas

__all__ = ["view_canvas"]


def view_canvas(canvas: PixelCanvas, **params: Any) -> int:
    """Não altera nada; devolve ``0`` para caber no contrato das ferramentas.

    O retrato em si é lido pelo executor, que grava ``canvas.stats()`` no
    registro da chamada. Manter a assinatura idêntica à das outras ferramentas
    é o que faz a inspeção aparecer no histórico na ordem exata em que
    aconteceu, entre as pinceladas.
    """
    return 0


view_canvas.name = "view_canvas"  # type: ignore[attr-defined]
