"""PX-DIM-001 — a resolução lógica é a resolução do arquivo (plano Pixel §40).

A regra de ouro nº 1 do Pixel Exact: um asset 64×64 é um PNG de 64×64 pixels,
nunca um PNG grande com quadradinhos desenhados (plano Pixel §3 e §103).

Este é o check mais fundamental do conjunto: se ele falha, todos os outros
números do relatório foram medidos na imagem errada — paleta, alpha e
ocupação de um PNG 512×512 não dizem nada sobre o asset que deveria existir.
"""

from __future__ import annotations

from ...contracts.validation_report import HardCheckResult
from .base import HardCheck, ValidationContext

__all__ = ["DimensionsCheck"]


class DimensionsCheck(HardCheck):
    """A imagem final tem exatamente ``spec.logical_size``."""

    code: str = "PX-DIM-001"
    name: str = "Logical Dimensions"

    def applies_to(self, context: ValidationContext) -> bool:
        return context.spec.validation.require_exact_dimensions

    def skip_reason(self, context: ValidationContext) -> str:
        return "require_exact_dimensions desligado no profile"

    def run(self, context: ValidationContext) -> HardCheckResult:
        expected_size = context.spec.logical_size.as_tuple
        actual_size = context.size
        expected = f"{expected_size[0]}x{expected_size[1]}"
        actual = f"{actual_size[0]}x{actual_size[1]}"
        detail = {
            "expected_size": list(expected_size),
            "actual_size": list(actual_size),
        }

        if actual_size != expected_size:
            return self.failed(
                f"resolução lógica incorreta: esperado {expected}, obtido {actual}",
                expected=expected,
                actual=actual,
                **detail,
            )
        return self.passed(
            f"resolução lógica exata: {actual}",
            expected=expected,
            actual=actual,
            **detail,
        )
