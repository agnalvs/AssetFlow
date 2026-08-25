"""O plano de desenho e o resultado da revisão (plano de correção §16 a §24).

Três contratos, e a separação entre eles é a arquitetura do agente:

:class:`DrawingBrief`
    o pedido, traduzido para o que o planner precisa — canvas, sujeito,
    cores. Não fala de capacidade, motor nem job.
:class:`DrawingPlan`
    o que o agente **pretende** desenhar: regiões nomeadas, papéis de cor e a
    sequência de comandos. Existe separado da execução para que se possa
    olhar a intenção antes de olhar o resultado — quando um sprite sai
    errado, a primeira pergunta é se o plano estava errado ou se a execução
    estava, e sem plano explícito não há como separar.
:class:`ReviewInstructions`
    o que o revisor **encontrou**, e o que ele recomenda. O plano §24 é
    explícito: o revisor não altera o canvas. Ele descreve; quem corrige é o
    agente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..palette import SpritePalette
from .command import ToolCall

__all__ = [
    "DrawingBrief",
    "DrawingPlan",
    "ReviewIssue",
    "ReviewInstructions",
]


@dataclass(frozen=True, slots=True)
class DrawingBrief:
    """O pedido, na forma de que o planner precisa."""

    subject: str
    asset_type: str
    width: int
    height: int
    max_colors: int | None = None
    transparent: bool = True
    seed: int = 0


@dataclass(frozen=True, slots=True)
class DrawingPlan:
    """O plano intermediário (plano de motores §9.2, plano de correção §17)."""

    canvas: tuple[int, int]
    asset_type: str
    subject: str
    recipe: str
    palette: SpritePalette
    #: ``{"copa": (x0, y0, x1, y1)}`` — as regiões que a receita reconhece.
    regions: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    calls: tuple[ToolCall, ...] = ()

    def document(self) -> dict[str, Any]:
        """O plano como JSON, no formato que o §17 mostra."""
        return {
            "canvas": list(self.canvas),
            "asset_type": self.asset_type,
            "subject": self.subject,
            "recipe": self.recipe,
            #: Papéis, e não uma lista solta de cores: é o papel que diz para
            #: que serve cada uma, e é por ele que uma correção pede "mais
            #: highlight" em vez de "mais #74AA59".
            "palette_roles": self.palette.roles(),
            "regions": [
                {"name": name, "bounds": list(bounds)}
                for name, bounds in self.regions.items()
            ],
            "calls": len(self.calls),
        }


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    """Um problema encontrado em uma região do desenho."""

    code: str
    region: str
    problem: str
    #: Ações que o agente sabe executar para corrigir. Vazio = só observação:
    #: o revisor viu algo que não sabe consertar, e dizer isso é melhor do que
    #: fingir que está tudo bem.
    recommended_actions: tuple[str, ...] = ()

    def document(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "region": self.region,
            "problem": self.problem,
            "recommended_actions": list(self.recommended_actions),
        }


@dataclass(slots=True)
class ReviewInstructions:
    """O laudo de uma passada de revisão (plano de correção §23 e §24)."""

    issues: list[ReviewIssue] = field(default_factory=list)
    #: Medidas do canvas no momento da revisão — o que o revisor viu.
    canvas: dict[str, Any] = field(default_factory=dict)

    def add(
        self, code: str, region: str, problem: str, *actions: str
    ) -> None:
        self.issues.append(
            ReviewIssue(
                code=code, region=region, problem=problem, recommended_actions=actions
            )
        )

    @property
    def actionable(self) -> list[ReviewIssue]:
        """Os problemas que o agente sabe corrigir."""
        return [issue for issue in self.issues if issue.recommended_actions]

    @property
    def is_clean(self) -> bool:
        return not self.issues

    def document(self) -> dict[str, Any]:
        return {
            "issues": [issue.document() for issue in self.issues],
            "canvas": self.canvas,
        }
