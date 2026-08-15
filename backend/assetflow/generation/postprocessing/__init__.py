"""Pós-processamento do AssetFlow.

O motor entrega pixels. O AssetFlow entrega **assets**. A diferença entre as
duas coisas está inteiramente neste pacote.
"""

from .base import ImageBuffer, PostProcessContext, PostProcessingChain, PostProcessor
from .image_ops import build_thumbnail, decode_image, encode_png, to_hex, unique_colors
from .pixel import build_pixel_chain
from .studio import build_studio_chain

__all__ = [
    "ImageBuffer",
    "PostProcessContext",
    "PostProcessingChain",
    "PostProcessor",
    "build_pixel_chain",
    "build_studio_chain",
    "build_thumbnail",
    "decode_image",
    "encode_png",
    "to_hex",
    "unique_colors",
]
