"""Palette Manager (planos §24 e §59).

A paleta é um ativo do AssetFlow, não do modelo. Duas estratégias:

``adaptive``
    Deriva a melhor paleta de N cores da própria imagem (median cut).

``fixed``
    Impõe uma paleta do projeto — é o que permite manter coerência entre
    assets de uma mesma família visual.
"""

from __future__ import annotations

from PIL import Image

from ..base import ImageBuffer, PostProcessContext, PostProcessor
from ..image_ops import from_hex, to_hex, unique_colors

__all__ = ["PaletteQuantizer"]


class PaletteQuantizer(PostProcessor):
    """Reduz a imagem à paleta definida pelo profile."""

    name = "pixel.palette_quantize"

    def applies_to(self, context: PostProcessContext) -> bool:
        palette = context.profile.palette
        return bool(palette.size) or palette.strategy == "fixed"

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        palette_config = context.profile.palette
        image = buffer.image.convert("RGBA")
        alpha = image.getchannel("A")

        if palette_config.strategy == "fixed" and palette_config.fixed_colors:
            quantized = _quantize_fixed(image, palette_config.fixed_colors)
        else:
            colors = int(palette_config.size or 16)
            quantized = _quantize_adaptive(image, colors)

        quantized.putalpha(alpha)
        buffer.replace(quantized)
        buffer.palette = tuple(
            dict.fromkeys(to_hex(color) for color in unique_colors(quantized))
        )
        buffer.metadata["palette_size"] = len(buffer.palette)
        buffer.metadata["palette_strategy"] = palette_config.strategy
        return buffer


def _quantize_adaptive(image: Image.Image, colors: int) -> Image.Image:
    """Median cut sem dithering — dithering é uma escolha artística opcional."""
    rgb = image.convert("RGB")
    quantized = rgb.quantize(colors=max(2, colors), method=Image.MEDIANCUT, dither=Image.NONE)
    return quantized.convert("RGBA")


def _quantize_fixed(image: Image.Image, hex_colors: tuple[str, ...]) -> Image.Image:
    """Mapeia cada pixel para a cor mais próxima da paleta do projeto."""
    colors = [from_hex(value) for value in hex_colors][:256]
    if not colors:
        return image.convert("RGBA")

    flat: list[int] = []
    for color in colors:
        flat.extend(color)
    flat.extend([0, 0, 0] * (256 - len(colors)))

    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(flat)

    rgb = image.convert("RGB")
    quantized = rgb.quantize(palette=palette_image, dither=Image.NONE)
    return quantized.convert("RGBA")
