"""SpriteOccupancyAnalyzer — quanto do canvas o sprite ocupa (plano Pixel §53).

Dois defeitos silenciosos aparecem aqui, e nenhum deles quebra um hard check:

``ocupação baixa demais``
    O personagem saiu minúsculo no meio de um canvas 64×64. O arquivo é
    tecnicamente perfeito e artisticamente inútil — em um tile de 64 pixels
    cada pixel desperdiçado é caro.
``ocupação alta demais``
    O sprite provavelmente foi cortado: o enquadramento estourou o canvas e o
    que ficou de fora não volta mais.

A borda entra junto porque é o sinal mais barato de clipping (plano Pixel
§45). Aqui ela é sempre aviso; quem pode **reprovar** por encostar na borda é
o BoundaryCheck, e só quando o profile pediu ``boundary_touch: fail``.
"""

from __future__ import annotations

from ...imaging import bounding_box, touches_border
from .base import AnalysisResult, QualityAnalyzer, ValidationContext

__all__ = ["SpriteOccupancyAnalyzer"]


class SpriteOccupancyAnalyzer(QualityAnalyzer):
    """Mede foreground, caixa do conteúdo e contato com a borda."""

    name = "occupancy"

    def analyze(self, context: ValidationContext) -> AnalysisResult:
        mask = context.mask
        canvas = context.canvas_pixels
        foreground = int(mask.sum())
        occupancy = round(foreground / canvas, 6) if canvas else 0.0
        box = bounding_box(mask)
        on_border = touches_border(mask)

        limits = context.spec.validation
        result = AnalysisResult(
            metrics={
                "foreground_pixels": foreground,
                "foreground_occupancy": occupancy,
                "bounding_box": box,
                "touches_border": on_border,
            }
        )

        if occupancy < limits.min_occupancy:
            result = result.with_warning(
                "PX-WARN-OCCUPANCY-LOW",
                f"o sprite ocupa {occupancy:.2%} do canvas, abaixo do mínimo "
                f"de {limits.min_occupancy:.2%} — personagem pequeno demais "
                "para o tamanho lógico escolhido",
                count=foreground,
                occupancy=occupancy,
                threshold=limits.min_occupancy,
            )
        elif occupancy > limits.max_occupancy:
            result = result.with_warning(
                "PX-WARN-OCCUPANCY-HIGH",
                f"o sprite ocupa {occupancy:.2%} do canvas, acima do máximo "
                f"de {limits.max_occupancy:.2%} — possível corte do "
                "enquadramento",
                count=foreground,
                occupancy=occupancy,
                threshold=limits.max_occupancy,
            )

        if on_border and limits.boundary_touch != "ignore":
            result = result.with_warning(
                "PX-WARN-BORDER",
                "o conteúdo encosta na borda do canvas — parte do sprite pode "
                "ter ficado de fora",
                count=1,
                policy=limits.boundary_touch,
                bounding_box=list(box) if box else None,
            )
        return result
