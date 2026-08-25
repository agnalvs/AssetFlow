"""A sessão de desenho: quanto esforço o agente pode gastar (§25 e §28).

Um agente sem limite de iterações é um job que não termina. O plano de
correção §25 fecha isso com três modos de qualidade, e a sessão é quem os
carrega:

    FAST        2 iterações
    BALANCED    4 iterações
    DETAILED    6 iterações

"Iteração" aqui é uma volta completa de *revisar e corrigir*, não uma
pincelada. O desenho do plano acontece uma vez; o que se repete é o laço do
§23 — inspecionar o canvas, receber o laudo, aplicar as correções que o agente
sabe aplicar.

A sessão também é o que acumula os metadados do §28: quantas iterações
rodaram, quantas tool calls foram feitas, o que cada revisão encontrou. Sem
isso, "o agente levou 34s" é a única coisa que se sabe sobre uma geração que
demorou 34 segundos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .contracts.command import ToolCallLog
from .contracts.plan import DrawingPlan, ReviewInstructions

__all__ = ["QualityMode", "AgentSession", "ITERATIONS_BY_QUALITY"]


class QualityMode(str, Enum):
    """Quanto esforço o agente pode gastar (plano de correção §25)."""

    #: Deixa o AssetFlow escolher a partir do tamanho e do tipo do asset.
    AUTO = "auto"
    FAST = "fast"
    BALANCED = "balanced"
    DETAILED = "detailed"


#: O orçamento de cada modo. Configurável em ``config/strategies.yaml``; estes
#: são os números do §25, usados quando o YAML não diz outra coisa.
ITERATIONS_BY_QUALITY: dict[QualityMode, int] = {
    QualityMode.FAST: 2,
    QualityMode.BALANCED: 4,
    QualityMode.DETAILED: 6,
}


@dataclass(slots=True)
class AgentSession:
    """O estado de uma execução do agente, do plano ao laudo final."""

    quality: QualityMode = QualityMode.BALANCED
    max_iterations: int = 4
    auto_review: bool = True
    log: ToolCallLog = field(default_factory=ToolCallLog)
    plan: DrawingPlan | None = None
    #: Um laudo por iteração, na ordem em que aconteceram.
    reviews: list[ReviewInstructions] = field(default_factory=list)
    #: Correções efetivamente aplicadas, por código de problema.
    repairs: dict[str, int] = field(default_factory=dict)
    iterations: int = 0

    @classmethod
    def for_quality(
        cls,
        quality: QualityMode | str,
        *,
        max_iterations: int | None = None,
        auto_review: bool = True,
        budgets: dict[QualityMode, int] | None = None,
    ) -> "AgentSession":
        """Monta a sessão a partir do modo de qualidade.

        ``max_iterations`` explícito ganha do modo: quem escreveu um número
        quis aquele número. É a mesma precedência do resto do sistema — uma
        escolha declarada vence um padrão.
        """
        mode = QualityMode(quality) if not isinstance(quality, QualityMode) else quality
        table = budgets or ITERATIONS_BY_QUALITY
        budget = table.get(mode, ITERATIONS_BY_QUALITY[QualityMode.BALANCED])
        return cls(
            quality=mode,
            max_iterations=max(0, max_iterations if max_iterations is not None else budget),
            auto_review=auto_review,
        )

    def record_review(self, review: ReviewInstructions) -> None:
        self.reviews.append(review)
        self.iterations += 1

    def record_repair(self, code: str, pixels: int) -> None:
        self.repairs[code] = self.repairs.get(code, 0) + pixels

    @property
    def tool_calls(self) -> int:
        return len(self.log.records)

    def document(self) -> dict[str, Any]:
        """Os metadados da sessão, no formato do §28."""
        return {
            "quality_mode": self.quality.value,
            "max_iterations": self.max_iterations,
            "auto_review": self.auto_review,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "repairs": dict(self.repairs),
            "reviews": [review.document() for review in self.reviews],
        }
