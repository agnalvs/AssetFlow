"""Redução para a resolução lógica (plano §59 — "logical resize").

O motor gera, por exemplo, 512×512. O asset é 64×64. Esta etapa faz a ponte.

Escolha técnica: a redução usa média de área (``BOX``) e **não**
nearest-neighbor. Nearest em downscale descarta 63 de cada 64 pixels e
destrói a silhueta; a média preserva a forma, e a nitidez característica da
Pixel Art é recuperada logo em seguida pela quantização de paleta e pelo
corte de alpha. Nearest-neighbor é usado para *ampliar* (thumbnail/preview),
onde ele é obrigatório.
"""

from __future__ import annotations

from PIL import Image

from ..base import ImageBuffer, PostProcessContext, PostProcessor

__all__ = ["LogicalResize"]


class LogicalResize(PostProcessor):
    """Leva a imagem bruta para o grid lógico do profile."""

    name = "pixel.logical_resize"

    def applies_to(self, context: PostProcessContext) -> bool:
        return context.profile.output.is_logical

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        output = context.profile.output
        target = (int(output.logical_width or 0), int(output.logical_height or 0))
        if target[0] <= 0 or target[1] <= 0:
            return buffer

        source = buffer.image.convert("RGBA")
        if source.size != target:
            resample = Image.BOX if source.width >= target[0] else Image.NEAREST
            source = source.resize(target, resample)

        buffer.logical_size = target
        buffer.metadata["logical_size"] = list(target)
        buffer.metadata["source_size"] = list(buffer.size)
        return buffer.replace(source)
