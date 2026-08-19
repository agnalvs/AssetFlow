"""Pós-processamento do AssetFlow.

O motor entrega pixels. O AssetFlow entrega **assets**. A diferença entre as
duas coisas está inteiramente neste pacote.
"""

from .base import ImageBuffer, PostProcessContext, PostProcessingChain, PostProcessor
from .image_ops import build_thumbnail, decode_image, encode_png, to_hex, unique_colors
from .pixel import PixelExactProcessor, build_pixel_chain, spec_from_profile
from .studio import build_studio_chain

__all__ = [
    "ImageBuffer",
    "PixelExactProcessor",
    "PostProcessContext",
    "PostProcessingChain",
    "PostProcessor",
    "build_pixel_chain",
    "spec_from_profile",
    "build_studio_chain",
    "build_thumbnail",
    "decode_image",
    "encode_png",
    "to_hex",
    "unique_colors",
]
