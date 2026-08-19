"""PX-EMPTY-001 — o asset precisa ter conteúdo (plano Pixel §44 e §88).

Um PNG 64×64 totalmente transparente passa em dimensão, em alpha binário e em
paleta: zero cor cabe em qualquer limite. Sem este check, o pipeline
entregaria um arquivo vazio com nota técnica perfeita — o caso de borda que o
plano §88 manda tratar explicitamente.

O piso é duplo de propósito: ``min_foreground_pixels`` protege contra o vazio
absoluto e ``min_foreground_ratio`` acompanha o tamanho do canvas, porque três
pixels sobrando em um 128×128 são tão inúteis quanto nenhum.
"""

from __future__ import annotations

from math import ceil

from ...contracts.validation_report import HardCheckResult
from .base import HardCheck, ValidationContext

__all__ = ["EmptyImageCheck"]


class EmptyImageCheck(HardCheck):
    """A imagem tem foreground suficiente para ser um asset."""

    code: str = "PX-EMPTY-001"
    name: str = "Non Empty"

    def applies_to(self, context: ValidationContext) -> bool:
        return context.spec.validation.require_non_empty

    def skip_reason(self, context: ValidationContext) -> str:
        return "require_non_empty desligado no profile"

    def run(self, context: ValidationContext) -> HardCheckResult:
        rules = context.spec.validation
        canvas_pixels = context.canvas_pixels
        foreground = int(context.mask.sum())
        required = max(
            rules.min_foreground_pixels,
            ceil(rules.min_foreground_ratio * canvas_pixels),
        )
        occupancy = round(foreground / canvas_pixels, 6) if canvas_pixels else 0.0
        detail = {
            "foreground_pixels": foreground,
            "required_pixels": required,
            "canvas_pixels": canvas_pixels,
            "occupancy": occupancy,
            "min_foreground_pixels": rules.min_foreground_pixels,
            "min_foreground_ratio": rules.min_foreground_ratio,
        }
        expected = f">={required}"
        actual = str(foreground)

        if foreground < required:
            message = (
                "imagem 100% transparente: nenhum pixel opaco"
                if foreground == 0
                else (
                    f"conteúdo insuficiente — pixels opacos: {foreground}, "
                    f"mínimo exigido: {required}"
                )
            )
            return self.failed(message, expected=expected, actual=actual, **detail)

        return self.passed(
            f"pixels opacos: {foreground} ({occupancy:.1%} do canvas)",
            expected=expected,
            actual=actual,
            **detail,
        )
