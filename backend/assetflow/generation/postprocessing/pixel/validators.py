"""Pixel Validator (plano §59).

Validação **não reprova** o asset por padrão: ela anota. O usuário decide o
que fazer com um aviso de "27 cores em um profile de 16". Erros de verdade
(grid quebrado) ficam registrados no relatório e acompanham o asset.

Evoluções previstas (fase seguinte): detecção de pixels órfãos, validação de
outline, checagem de clusters e agrupamento de paleta.
"""

from __future__ import annotations

from ..base import ImageBuffer, PostProcessContext, PostProcessor
from ..image_ops import unique_colors

__all__ = ["ColorCountValidator", "GridValidator"]


class ColorCountValidator(PostProcessor):
    """Confere a contagem de cores contra o limite do profile."""

    name = "pixel.validate_color_count"

    def applies_to(self, context: PostProcessContext) -> bool:
        return context.profile.postprocessing.validate_color_count

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        limit = context.profile.palette.size
        colors = unique_colors(buffer.image)
        count = len({color[:3] for color in colors})
        buffer.metadata["color_count"] = count

        if limit and count > limit:
            buffer.add_issue(
                "color_count_exceeded",
                f"asset possui {count} cores, acima do limite de {limit} do profile",
                severity="warning",
                count=count,
                limit=limit,
            )
        return buffer


class GridValidator(PostProcessor):
    """Garante integridade do grid lógico.

    Checa duas coisas que quebram um asset dentro de uma engine de jogo:

    1. a resolução final é exatamente a resolução lógica do profile;
    2. não sobrou alpha parcial (borda "molhada") depois da limpeza.
    """

    name = "pixel.validate_grid"

    def applies_to(self, context: PostProcessContext) -> bool:
        return context.profile.postprocessing.validate_grid

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        output = context.profile.output
        if output.is_logical:
            expected = (int(output.logical_width or 0), int(output.logical_height or 0))
            if buffer.image.size != expected:
                buffer.add_issue(
                    "grid_size_mismatch",
                    f"resolução {buffer.image.size} difere do grid lógico {expected}",
                    severity="error",
                    expected=list(expected),
                    actual=list(buffer.image.size),
                )

        alpha = buffer.image.convert("RGBA").getchannel("A")
        partial = sum(count for value, count in enumerate(alpha.histogram()) if 0 < value < 255)
        if partial:
            buffer.add_issue(
                "partial_alpha",
                f"{partial} pixels com transparência parcial permaneceram no asset",
                severity="warning",
                pixels=partial,
            )

        buffer.metadata["grid_validated"] = True
        return buffer
