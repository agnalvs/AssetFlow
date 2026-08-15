"""Limpeza de alpha (plano §59 — "alpha cleanup").

Pixel Art em engine de jogo não convive bem com transparência parcial: ela
produz bordas sujas ao ampliar e quebra colisão por máscara. Esta etapa
binariza o alpha e remove a franja semitransparente deixada pelo gerador.
"""

from __future__ import annotations

from PIL import Image

from ..base import ImageBuffer, PostProcessContext, PostProcessor

__all__ = ["AlphaCleanup"]


class AlphaCleanup(PostProcessor):
    """Transforma alpha contínuo em alpha binário (0 ou 255)."""

    name = "pixel.alpha_cleanup"

    def applies_to(self, context: PostProcessContext) -> bool:
        return context.profile.postprocessing.pixel_cleanup

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        threshold = context.profile.postprocessing.alpha_threshold
        image = buffer.image.convert("RGBA")
        alpha = image.getchannel("A")

        binary = alpha.point(lambda value: 255 if value >= threshold else 0)
        semi = sum(
            count
            for count, value in _histogram_pairs(alpha)
            if 0 < value < 255
        )

        image.putalpha(binary)
        buffer.metadata["alpha_threshold"] = threshold
        buffer.metadata["semitransparent_pixels_removed"] = semi
        return buffer.replace(image)


def _histogram_pairs(channel: Image.Image) -> list[tuple[int, int]]:
    """Pares ``(quantidade, valor)`` do histograma de um canal."""
    return [(count, value) for value, count in enumerate(channel.histogram())]
