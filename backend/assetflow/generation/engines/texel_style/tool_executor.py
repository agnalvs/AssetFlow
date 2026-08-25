"""ToolExecutor e ToolCallLog — quem aplica as ferramentas (plano de motores §9.3 e §9.5).

Toda alteração do canvas passa por aqui, e nenhuma passa por fora. Essa regra
é o que dá ao engine a propriedade mais útil que ele tem: **o log de tool
calls reconstrói o desenho inteiro**. Um sprite que saiu errado não exige
adivinhar o que aconteceu — o histórico diz em qual chamada aconteceu.

O executor é deliberadamente burro. Ele não sabe desenhar árvore, não escolhe
cor e não decide ordem: ele procura a ferramenta pelo nome, chama, conta os
pixels que mudaram e registra. Planejar é do :mod:`.planner`, revisar é do
:mod:`.review_loop`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .canvas import PixelCanvas
from .tools import ALL_TOOLS

__all__ = ["ToolCall", "ToolCallRecord", "ToolCallLog", "ToolExecutor"]

_LOG = logging.getLogger("assetflow.engine.texel_style")

#: Chamadas cujo log guarda o retrato do canvas junto (§9.4).
_INSPECTION_TOOLS = frozenset({"view_canvas"})


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Uma intenção de desenho: qual ferramenta, com quais parâmetros."""

    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    #: Por que esta chamada existe — "tronco", "copa", "contorno". Aparece no
    #: log e é o que o torna legível por gente, em vez de uma lista de
    #: coordenadas.
    note: str = ""

    def document(self) -> dict[str, Any]:
        return {"tool": self.tool, "params": _jsonable(self.params), "note": self.note}


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    """O que aconteceu quando uma chamada foi executada."""

    call: ToolCall
    pixels_changed: int
    duration_ms: float
    error: str | None = None
    #: Retrato do canvas, só nas chamadas de inspeção.
    snapshot: dict[str, Any] | None = None

    def document(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            **self.call.document(),
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
    """O histórico completo da execução (plano de motores §9.5)."""

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
        """Resumo para o ``engine_metadata`` — o log inteiro pode ser longo."""
        by_tool: dict[str, int] = {}
        for record in self.records:
            by_tool[record.call.tool] = by_tool.get(record.call.tool, 0) + 1
        return {
            "calls": len(self.records),
            "pixels_changed": self.pixels_changed,
            "by_tool": by_tool,
            "errors": list(self.errors),
        }


class ToolExecutor:
    """Aplica :class:`ToolCall` sobre um :class:`PixelCanvas`."""

    def __init__(self, tools: Iterable[Any] | None = None) -> None:
        self._tools = {tool.name: tool for tool in (tools or ALL_TOOLS)}

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

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
                changed = int(tool(canvas, **call.params))
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


def _jsonable(params: dict[str, Any]) -> dict[str, Any]:
    """Deixa os parâmetros gravável em JSON, sem perder informação.

    Só tuplas viram listas; o resto passa direto. O log é escrito em disco
    (``engine_output.json``) e precisa sobreviver a ``json.dumps``.
    """
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, tuple):
            clean[key] = list(value)
        elif isinstance(value, list):
            clean[key] = [list(item) if isinstance(item, tuple) else item for item in value]
        else:
            clean[key] = value
    return clean
