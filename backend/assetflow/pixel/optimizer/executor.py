"""PixelToolExecutor — quem aplica os reparos (plano Optimizer §13 e §67).

Toda alteração do sprite passa por aqui, e nenhuma passa por fora. É o que dá
ao Optimizer a propriedade que o §47 exige: ``optimizer_actions.json``
reconstrói exatamente o que foi mudado, e um asset que piorou tem um log que
diz em qual ação piorou.

Duas guardas, e as duas são regras do plano:

**§15 — coordenadas inteiras.** ``13.5`` é recusado, não truncado. Meio pixel
não existe na grade, e truncar em silêncio esconderia um erro de planejamento
até ele aparecer na imagem.

**§16 e §67 — a paleta manda.** Toda cor passa pelo :class:`PaletteGuard`
antes de chegar à ferramenta. Com ``palette.mode = locked``, uma cor de fora é
**recusada**; com ``max_colors``, ela é resolvida para a mais próxima já em
uso quando o orçamento está cheio.

A diferença entre recusar e resolver não é capricho. Em paleta travada, a
lista de cores é o contrato do projeto — inventar uma cor é quebrar o asset.
Em orçamento de cores, o que importa é o número, e trocar por um tom vizinho
preserva a pincelada que o planejador quis dar.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .canvas import PixelCanvas
from .contracts import RepairAction
from .palette import PaletteGuard, PaletteViolation
from .tools import ALL_TOOLS

__all__ = ["PixelToolExecutor", "ToolCallLog", "ToolCallRecord"]

_LOG = logging.getLogger("assetflow.pixel.optimizer")

#: Ferramentas que só leem o canvas — o log guarda o retrato junto.
_INSPECTION_TOOLS = frozenset({"inspect_canvas", "inspect_region"})


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """O que aconteceu quando uma ação foi executada."""

    action: RepairAction
    pixels_changed: int
    duration_ms: float
    error: str | None = None
    snapshot: dict[str, Any] | None = None

    def document(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self.action.document(),
            "pixels_changed": self.pixels_changed,
            "duration_ms": round(self.duration_ms, 3),
        }
        if self.error:
            payload["error"] = self.error
        if self.snapshot is not None:
            payload["canvas"] = self.snapshot
        return payload


@dataclass(slots=True)
class ToolCallLog:
    """O histórico das correções (plano Optimizer §47)."""

    records: list[ToolCallRecord] = field(default_factory=list)

    def add(self, record: ToolCallRecord) -> None:
        self.records.append(record)

    @property
    def pixels_changed(self) -> int:
        return sum(record.pixels_changed for record in self.records)

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(record.error for record in self.records if record.error)

    def document(self) -> list[dict[str, Any]]:
        return [record.document() for record in self.records]

    def summary(self) -> dict[str, Any]:
        by_tool: dict[str, int] = {}
        for record in self.records:
            by_tool[record.action.tool] = by_tool.get(record.action.tool, 0) + 1
        return {
            "calls": len(self.records),
            "pixels_changed": self.pixels_changed,
            "by_tool": by_tool,
            "errors": list(self.errors),
        }


class PixelToolExecutor:
    """Aplica :class:`RepairAction` sobre um :class:`PixelCanvas`."""

    #: Parâmetros que carregam cor e por isso passam pela guarda da paleta.
    _COLOR_PARAMS = ("color", "to_color", "fill")

    def __init__(
        self,
        tools: Iterable[Any] | None = None,
        *,
        palette: PaletteGuard | None = None,
    ) -> None:
        self._tools = {tool.name: tool for tool in (tools or ALL_TOOLS)}
        self._palette = palette

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    @property
    def palette(self) -> PaletteGuard | None:
        return self._palette

    # ------------------------------------------------------------------
    def execute(
        self,
        canvas: PixelCanvas,
        action: RepairAction,
        log: ToolCallLog | None = None,
    ) -> ToolCallRecord:
        """Executa uma ação e registra o que aconteceu.

        Uma ação inválida **não** derruba a otimização: ela vira um registro
        com ``error`` e o laço continua. Um plano com uma coordenada ruim deve
        produzir um reparo a menos e um log que aponta o problema — nunca um
        asset perdido.
        """
        started = time.perf_counter()
        tool = self._tools.get(action.tool)

        if tool is None:
            record = ToolCallRecord(
                action=action,
                pixels_changed=0,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=f"ferramenta desconhecida: '{action.tool}'",
            )
        else:
            try:
                changed = int(tool(canvas, **self._guarded(action.params)))
                error = None
            except PaletteViolation as exc:
                # §67: cor fora da paleta travada é recusa, não aproximação.
                changed = 0
                error = str(exc)
            except Exception as exc:
                changed = 0
                error = f"{type(exc).__name__}: {exc}"
                _LOG.debug("reparo '%s' falhou: %s", action.tool, exc)
            record = ToolCallRecord(
                action=action,
                pixels_changed=changed,
                duration_ms=(time.perf_counter() - started) * 1000.0,
                error=error,
                snapshot=(
                    _snapshot(canvas) if action.tool in _INSPECTION_TOOLS else None
                ),
            )

        if log is not None:
            log.add(record)
        return record

    def execute_all(
        self,
        canvas: PixelCanvas,
        actions: Sequence[RepairAction],
        log: ToolCallLog | None = None,
    ) -> int:
        """Executa uma sequência; devolve o total de pixels alterados."""
        return sum(self.execute(canvas, action, log).pixels_changed for action in actions)

    # ------------------------------------------------------------------
    def _guarded(self, params: dict[str, Any]) -> dict[str, Any]:
        """Os parâmetros com as cores já passadas pela guarda da paleta."""
        if self._palette is None:
            return params
        guarded = dict(params)
        for name in self._COLOR_PARAMS:
            if name in guarded and guarded[name] is not None:
                guarded[name] = self._palette.resolve(guarded[name])
        return guarded


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
