"""PixelToolExecutor — quem aplica as ferramentas (plano de correção §19).

Toda alteração do canvas passa por aqui, e nenhuma passa por fora. Essa regra
é o que dá ao agente a propriedade mais útil que ele tem: **o log de tool
calls reconstrói o desenho inteiro**. Um sprite que saiu errado não exige
adivinhar o que aconteceu — o histórico diz em qual chamada aconteceu.

O executor é deliberadamente burro. Ele não sabe desenhar árvore, não escolhe
cor e não decide ordem: ele procura a ferramenta pelo nome, chama, conta os
pixels que mudaram e registra. Planejar é do :mod:`.planner`, revisar é do
:mod:`.reviewer`, e decidir o que fazer com a revisão é do :mod:`.agent`.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Sequence

from .canvas import PixelCanvas
from .contracts.command import ToolCall, ToolCallLog, ToolCallRecord
from .palette import PaletteManager
from .tools import ALL_TOOLS

__all__ = ["PixelToolExecutor", "ToolExecutor"]

_LOG = logging.getLogger("assetflow.pixel_agent.executor")

#: Chamadas cujo log guarda o retrato do canvas junto (plano de correção §23).
_INSPECTION_TOOLS = frozenset({"inspect_canvas"})


class PixelToolExecutor:
    """Aplica :class:`ToolCall` sobre um :class:`PixelCanvas`.

    Duas guardas passam por aqui, e as duas são regras do plano de correção:

    **§21 — nada de coordenada fracionária.** Quem recusa é ``as_int``, nas
    ferramentas; o executor apenas transforma a recusa em um registro de erro
    em vez de deixar a exceção subir.

    **§22 — nada de cor fora da paleta.** Todo parâmetro de cor passa pelo
    :class:`PaletteManager` antes de chegar à ferramenta. Sem ele, o agente
    poderia pintar 40 tons e o orçamento de 16 cores viraria trabalho do
    pós-processamento — que remapeia pixels já pintados, sem saber que papel
    cada um cumpria.
    """

    #: Parâmetros que carregam cor e por isso passam pelo Palette Manager.
    _COLOR_PARAMS = ("color", "fill", "stroke")

    def __init__(
        self,
        tools: Iterable[Any] | None = None,
        *,
        palette: PaletteManager | None = None,
    ) -> None:
        self._tools = {tool.name: tool for tool in (tools or ALL_TOOLS)}
        self._palette = palette

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    @property
    def palette(self) -> PaletteManager | None:
        return self._palette

    def _guarded(self, params: dict[str, Any]) -> dict[str, Any]:
        """Os parâmetros com as cores já resolvidas pela paleta."""
        if self._palette is None:
            return params
        guarded = dict(params)
        for name in self._COLOR_PARAMS:
            if name in guarded:
                guarded[name] = self._palette.resolve(guarded[name])
        return guarded

    # ------------------------------------------------------------------
    def execute(
        self, canvas: PixelCanvas, call: ToolCall, log: ToolCallLog | None = None
    ) -> ToolCallRecord:
        """Executa uma chamada e registra o que aconteceu.

        Uma chamada inválida **não** derruba o desenho: ela vira um registro
        com ``error`` e a execução continua. Um plano com uma coordenada ruim
        deve produzir um sprite com um defeito e um log que aponta o defeito —
        não um job perdido inteiro.
        """
        started = time.perf_counter()
        tool = self._tools.get(call.tool)

        if tool is None:
            record = ToolCallRecord(
                call=call,
                pixels_changed=0,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=f"ferramenta desconhecida: '{call.tool}'",
            )
        else:
            try:
                changed = int(tool(canvas, **self._guarded(call.params)))
                error = None
            except Exception as exc:
                changed = 0
                error = f"{type(exc).__name__}: {exc}"
                _LOG.debug("tool call '%s' falhou: %s", call.tool, exc)
            record = ToolCallRecord(
                call=call,
                pixels_changed=changed,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=error,
                snapshot=(
                    _snapshot(canvas) if call.tool in _INSPECTION_TOOLS else None
                ),
            )

        if log is not None:
            log.add(record)
        return record

    def execute_all(
        self,
        canvas: PixelCanvas,
        calls: Sequence[ToolCall],
        log: ToolCallLog | None = None,
    ) -> int:
        """Executa uma sequência; devolve o total de pixels alterados."""
        return sum(
            self.execute(canvas, call, log).pixels_changed for call in calls
        )


#: Nome anterior, de quando o agente ainda era uma gaveta. Mantido porque não
#: custa nada e porque o nome curto é o que aparece nas conversas.
ToolExecutor = PixelToolExecutor


def _snapshot(canvas: PixelCanvas) -> dict[str, Any]:
    stats = canvas.stats()
    return {
        "size": [stats.width, stats.height],
        "opaque_pixels": stats.opaque_pixels,
        "color_count": stats.color_count,
        "occupancy": round(stats.occupancy, 4),
        "bounds": list(stats.bounds) if stats.bounds else None,
        "orphan_pixels": stats.orphan_pixels,
    }
