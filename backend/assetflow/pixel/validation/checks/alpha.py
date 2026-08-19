"""PX-ALPHA-001 — alpha binário, sem meio-termo (plano Pixel §41).

No Pixel Exact um pixel existe ou não existe: o canal alpha só pode conter 0
ou 255 (plano Pixel §21 a §23). Alpha intermediário é o rastro clássico de
uma redução interpolada — a borda do sprite vira uma franja de pixels
semitransparentes que, ampliada no jogo, aparece como sujeira em volta do
personagem e quebra o recorte contra qualquer fundo.

Quando falha, o relatório precisa dizer *quais* valores apareceram e em
quantos pixels: é a diferença entre "duas bordas ficaram a 254" e "a imagem
inteira saiu semitransparente" (plano Pixel §62).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ...contracts.validation_report import HardCheckResult
from ...imaging import alpha_values
from .base import HardCheck, ValidationContext

__all__ = ["AlphaCheck"]

#: Quantos valores proibidos entram no detalhe do relatório (plano Pixel §62).
_MAX_LISTED = 16
#: Quantos valores cabem na string ``actual`` sem virar uma parede de números.
_MAX_INLINE = 8


def _format_values(values: Sequence[int], *, limit: int = _MAX_INLINE) -> str:
    """Formata um conjunto de valores de alpha para leitura humana."""
    shown = ", ".join(str(value) for value in values[:limit])
    if len(values) > limit:
        return f"{{{shown}, ...}} ({len(values)} valores)"
    return f"{{{shown}}}"


class AlphaCheck(HardCheck):
    """Os valores presentes no canal alpha são subconjunto de ``{0, 255}``."""

    code: str = "PX-ALPHA-001"
    name: str = "Binary Alpha"

    def applies_to(self, context: ValidationContext) -> bool:
        return context.spec.validation.require_binary_alpha

    def skip_reason(self, context: ValidationContext) -> str:
        return "require_binary_alpha desligado no profile"

    def run(self, context: ValidationContext) -> HardCheckResult:
        allowed = context.spec.alpha.allowed_values
        present = alpha_values(context.array)
        forbidden = tuple(value for value in present if value not in allowed)

        expected = _format_values(allowed)
        actual = _format_values(present)

        if not forbidden:
            return self.passed(
                f"alpha binário: {actual}",
                expected=expected,
                actual=actual,
                alpha_values=list(present),
                forbidden_value_count=0,
            )

        # Na falha o detalhe não repete a lista completa de valores presentes
        # (uma imagem interpolada tem centenas deles, e `actual` já resume o
        # quadro): o que aponta a causa é a contagem por valor proibido, que
        # separa "franja de borda" de "sprite inteiro semitransparente".
        channel = context.array[:, :, 3]
        counts = {
            int(value): int(np.count_nonzero(channel == value)) for value in forbidden
        }
        occurrences = [
            {"value": value, "pixels": counts[value]}
            for value in forbidden[:_MAX_LISTED]
        ]
        total_pixels = sum(counts.values())

        return self.failed(
            f"alpha não binário — valores fora de {expected}: {len(forbidden)}, "
            f"pixels afetados: {total_pixels}",
            expected=expected,
            actual=actual,
            alpha_value_count=len(present),
            forbidden_value_count=len(forbidden),
            forbidden_pixels=total_pixels,
            forbidden_values=occurrences,
        )
