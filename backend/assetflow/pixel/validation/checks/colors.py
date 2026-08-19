"""PX-COLOR-001 — a paleta cabe no limite do profile (plano Pixel §42).

Contagem de cores é o indicador mais direto de que a imagem passou mesmo pelo
caminho Pixel Exact: uma saída de motor tem milhares de cores, um asset de 16
cores tem 16. Se o número estourar, a quantização não fez o trabalho e o
resultado é "arte que parece pixel art", exatamente o que o plano §1 recusa.

Pixels transparentes não entram na conta: o RGB que existe atrás de alpha 0 é
invisível e não gasta entrada de paleta (plano Pixel §22).
"""

from __future__ import annotations

from ...contracts.validation_report import HardCheckResult
from ...imaging import count_colors
from .base import HardCheck, ValidationContext

__all__ = ["ColorCountCheck"]


class ColorCountCheck(HardCheck):
    """Cores únicas não transparentes ``<= spec.max_colors``."""

    code: str = "PX-COLOR-001"
    name: str = "Maximum Colors"

    def applies_to(self, context: ValidationContext) -> bool:
        spec = context.spec
        return spec.validation.require_palette_limit and spec.max_colors is not None

    def skip_reason(self, context: ValidationContext) -> str:
        if not context.spec.validation.require_palette_limit:
            return "require_palette_limit desligado no profile"
        return "o profile não define um teto de cores"

    def run(self, context: ValidationContext) -> HardCheckResult:
        limit = context.spec.max_colors
        if limit is None:  # `applies_to` já barra; guarda para chamada direta
            return self.skipped(self.skip_reason(context))

        count = count_colors(context.array)
        expected = f"<={limit}"
        actual = str(count)
        excess = max(0, count - limit)

        if excess:
            return self.failed(
                f"limite de cores estourado — cores únicas: {count}, "
                f"limite: {limit}, excesso: {excess}",
                expected=expected,
                actual=actual,
                max_colors=limit,
                color_count=count,
                excess=excess,
            )
        return self.passed(
            f"cores únicas: {count} (limite: {limit})",
            expected=expected,
            actual=actual,
            max_colors=limit,
            color_count=count,
            excess=0,
        )
