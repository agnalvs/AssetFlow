"""Os contratos do Pixel Optimizer (plano Optimizer §11, §12 e §23).

Três objetos, e a separação entre eles é a arquitetura do módulo:

:class:`PixelReview`
    o que o revisor **encontrou**. Diagnóstico puro: nenhuma ação, nenhum
    pixel tocado.
:class:`RepairPlan`
    o que o planejador decidiu **fazer** a respeito. Ações concretas, com
    justificativa por ação.
:class:`OptimizationReport`
    o que de fato **aconteceu**: quantas voltas, quais reparos, quantos
    pixels mudaram, e por que o laço parou.

Por que três, e não um
----------------------
Porque medir, decidir e executar falham de formas diferentes. Um sprite que
saiu pior depois da otimização precisa responder a três perguntas separadas —
o diagnóstico estava errado? o plano estava errado? a execução estava? — e um
objeto único não distingue nenhuma delas.

É a mesma fronteira que o AssetFlow já mantém entre o ``PixelValidator``, que
mede, e a ``PixelAcceptancePolicy``, que decide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "IssueSeverity",
    "OptimizationReport",
    "OptimizationStatus",
    "PixelIssue",
    "PixelReview",
    "RepairAction",
    "RepairPlan",
]


class IssueSeverity(str, Enum):
    """Quanto um problema pesa na decisão de corrigir."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OptimizationStatus(str, Enum):
    """Por que o Optimizer parou (plano Optimizer §23 e §45).

    ``SKIPPED`` merece atenção: ele **não** significa que o Optimizer é
    opcional. Ele significa que o asset chegou aprovado e com nota alta, e que
    a decisão segura foi não mexer. O Optimizer continua parte obrigatória do
    pipeline — ele só decidiu, por conta própria, que não havia o que fazer
    (§46).
    """

    #: O asset já estava bom; nenhuma correção foi aplicada.
    SKIPPED = "skipped"
    #: Correções aplicadas e o asset passou a valer a validação final.
    OPTIMIZED = "optimized"
    #: O revisor encontrou problemas, mas nenhum com correção segura.
    NO_SAFE_REPAIRS = "no_safe_repairs"
    #: O teto de iterações foi atingido antes de o asset ficar aprovado.
    EXHAUSTED = "exhausted"
    #: O Optimizer está desligado por configuração.
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class PixelIssue:
    """Um problema estrutural encontrado no sprite (plano Optimizer §11)."""

    type: str
    severity: IssueSeverity = IssueSeverity.LOW
    #: Região nomeada, quando o problema tem lugar — "left_canopy", "silhueta".
    region: str | None = None
    #: Posição exata, quando o problema é pontual.
    position: tuple[int, int] | None = None
    detail: str = ""
    #: Pixels envolvidos. É o que o planejador usa para montar a ação, e é
    #: por isso que o revisor os coleta em vez de só contar.
    pixels: tuple[tuple[int, int], ...] = ()

    def document(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type,
            "severity": self.severity.value,
            "detail": self.detail,
            "pixel_count": len(self.pixels),
        }
        if self.region:
            payload["region"] = self.region
        if self.position:
            payload["position"] = list(self.position)
        return payload


@dataclass(slots=True)
class PixelReview:
    """O laudo de uma passada de revisão (plano Optimizer §11)."""

    approved: bool = True
    issues: list[PixelIssue] = field(default_factory=list)
    #: Medidas do canvas no momento da revisão.
    canvas: dict[str, Any] = field(default_factory=dict)

    def add(self, issue: PixelIssue) -> None:
        self.issues.append(issue)
        self.approved = False

    @property
    def no_safe_repairs(self) -> bool:
        """Nada aqui tem correção segura conhecida (plano Optimizer §18)."""
        return not self.issues

    def of_type(self, kind: str) -> list[PixelIssue]:
        return [issue for issue in self.issues if issue.type == kind]

    def document(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "issues": [issue.document() for issue in self.issues],
            "canvas": self.canvas,
        }


@dataclass(frozen=True, slots=True)
class RepairAction:
    """Uma correção concreta, com o motivo junto (plano Optimizer §12).

    ``reason`` não é enfeite: ele é o que permite, meses depois, olhar
    ``optimizer_actions.json`` e entender por que aquele pixel sumiu.
    """

    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    #: O problema que esta ação corrige — liga o plano ao laudo.
    issue_type: str = ""

    def document(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "params": _jsonable(self.params),
            "reason": self.reason,
            "issue_type": self.issue_type,
        }


@dataclass(slots=True)
class RepairPlan:
    """As ações decididas para esta volta (plano Optimizer §12)."""

    actions: list[RepairAction] = field(default_factory=list)
    #: Problemas que o planejador viu e decidiu **não** corrigir, com o
    #: motivo. Guardar isso é o §17 em forma de dado: "1 pixel isolado" pode
    #: ser um olho, e a decisão de preservá-lo é informação.
    declined: list[tuple[str, str]] = field(default_factory=list)

    def add(self, action: RepairAction) -> None:
        self.actions.append(action)

    def decline(self, issue_type: str, reason: str) -> None:
        self.declined.append((issue_type, reason))

    @property
    def is_empty(self) -> bool:
        return not self.actions

    def document(self) -> dict[str, Any]:
        return {
            "actions": [action.document() for action in self.actions],
            "declined": [
                {"issue_type": kind, "reason": reason} for kind, reason in self.declined
            ],
        }


@dataclass(slots=True)
class OptimizationReport:
    """O que a otimização fez, para o histórico (plano Optimizer §48)."""

    status: OptimizationStatus = OptimizationStatus.SKIPPED
    iterations: int = 0
    tool_calls: int = 0
    pixels_changed: int = 0
    reviews: list[PixelReview] = field(default_factory=list)
    plans: list[RepairPlan] = field(default_factory=list)
    #: Nota do validador antes e depois — a medida do §69.
    score_before: int | None = None
    score_after: int | None = None
    duration_ms: float = 0.0
    #: Quem revisou: o revisor determinístico ou um modelo.
    reviewer: str = "heuristic"

    @property
    def changed_anything(self) -> bool:
        return self.pixels_changed > 0

    @property
    def improvement(self) -> int | None:
        if self.score_before is None or self.score_after is None:
            return None
        return self.score_after - self.score_before

    def document(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reviewer": self.reviewer,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "pixels_changed": self.pixels_changed,
            "score_before": self.score_before,
            "score_after": self.score_after,
            "improvement": self.improvement,
            "duration_ms": round(self.duration_ms, 3),
            "reviews": [review.document() for review in self.reviews],
            "plans": [plan.document() for plan in self.plans],
        }


def _jsonable(params: dict[str, Any]) -> dict[str, Any]:
    """Deixa os parâmetros graváveis em JSON, sem perder informação."""
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
