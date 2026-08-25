"""Os contratos do Pixel Agent (plano de correção §16).

Eles ficam separados das implementações pelo motivo de sempre: o planner
produz um :class:`DrawingPlan`, o executor consome :class:`ToolCall`, o
revisor devolve :class:`ReviewInstructions` — e nenhum dos três precisa
conhecer o outro para isso.

É o que permite trocar o planner determinístico de hoje por um com LLM
(plano de correção §18) sem tocar em executor, canvas ou revisor.
"""

from .command import ToolCall, ToolCallLog, ToolCallRecord
from .plan import DrawingBrief, DrawingPlan, ReviewInstructions, ReviewIssue

__all__ = [
    "DrawingBrief",
    "DrawingPlan",
    "ReviewInstructions",
    "ReviewIssue",
    "ToolCall",
    "ToolCallLog",
    "ToolCallRecord",
]
