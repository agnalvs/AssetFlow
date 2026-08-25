"""O comando de desenho e o histórico dele (plano de correção §16 e §19).

Um comando é uma intenção declarada: *qual ferramenta, com quais parâmetros e
por quê*. Ele existe separado da execução porque é o objeto que atravessa o
agente inteiro — o planner produz comandos, o executor os aplica, o log os
guarda, e o histórico resultante reconstrói o desenho passo a passo.

É essa propriedade que dá ao agente algo que nenhum modelo generativo tem: um
sprite que saiu errado não exige adivinhar o que aconteceu. O log diz em qual
comando aconteceu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ToolCall", "ToolCallRecord", "ToolCallLog"]


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
    """O que aconteceu quando um comando foi executado."""

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
        """Resumo para os metadados — o log inteiro pode ser longo."""
        by_tool: dict[str, int] = {}
        for record in self.records:
            by_tool[record.call.tool] = by_tool.get(record.call.tool, 0) + 1
        return {
            "calls": len(self.records),
            "pixels_changed": self.pixels_changed,
            "by_tool": by_tool,
            "errors": list(self.errors),
        }


def _jsonable(params: dict[str, Any]) -> dict[str, Any]:
    """Deixa os parâmetros graváveis em JSON, sem perder informação.

    Só tuplas viram listas; o resto passa direto. O log é escrito em disco
    (``engine_output.json``) e precisa sobreviver a ``json.dumps``.
    """
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, tuple):
            clean[key] = list(value)
        elif isinstance(value, list):
            clean[key] = [
                list(item) if isinstance(item, tuple) else item for item in value
            ]
        else:
            clean[key] = value
    return clean
