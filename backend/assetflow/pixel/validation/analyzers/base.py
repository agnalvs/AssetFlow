"""Contrato dos QUALITY ANALYZERS (plano Pixel §47 a §55).

Diferença de propósito em relação aos hard checks:

    HardCheck   ->  "isto atende à especificação?"   pass / fail
    Analyzer    ->  "isto tem cara de problema?"     métrica + aviso

Um analisador **não reprova** nada e **não altera** nada. Ele produz números.
O plano §51 é explícito: não existe regra universal dizendo que um cluster de
um pixel está errado — Pixel Art profissional usa pixels isolados de
propósito. Portanto: detectar não significa remover (§29).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ...contracts.validation_report import QualityWarning
from ..checks.base import ValidationContext

__all__ = ["AnalysisResult", "QualityAnalyzer", "ValidationContext"]


@dataclass(slots=True)
class AnalysisResult:
    """O que um analisador devolve.

    ``metrics`` são campos de
    :class:`~assetflow.pixel.contracts.validation_report.QualityMetrics`; o
    serviço junta os dicionários de todos os analisadores e valida o conjunto.
    """

    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[QualityWarning, ...] = ()

    def with_warning(
        self, code: str, message: str, *, count: int = 0, **detail: Any
    ) -> AnalysisResult:
        warning = QualityWarning(code=code, message=message, count=count, detail=detail)
        return AnalysisResult(metrics=self.metrics, warnings=(*self.warnings, warning))


class QualityAnalyzer(ABC):
    """Um analisador estrutural."""

    name: str = "analyzer"
    version: str = "1.0.0"

    @abstractmethod
    def analyze(self, context: ValidationContext) -> AnalysisResult:
        """Mede a imagem. Nunca a modifica."""

    def applies_to(self, context: ValidationContext) -> bool:
        return True
