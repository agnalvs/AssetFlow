"""Estágios do PixelPostProcessor (plano Pixel §8).

Cada módulo aqui tem responsabilidade única e pode ser substituído sem tocar
no pipeline: é esse o ponto do contrato :class:`PixelTransform` (plano §9).
"""

from .alpha_normalizer import AlphaNormalizer
from .base import PixelContext, PixelTransform
from .canvas_normalizer import CanvasNormalizer
from .conservative_cleaner import ConservativeCleaner
from .exporter import PixelExporter
from .input_normalizer import InputNormalizer
from .logical_reducer import LogicalPixelReducer
from .palette_quantizer import PaletteQuantizer

__all__ = [
    "AlphaNormalizer",
    "CanvasNormalizer",
    "ConservativeCleaner",
    "InputNormalizer",
    "LogicalPixelReducer",
    "PaletteQuantizer",
    "PixelContext",
    "PixelExporter",
    "PixelTransform",
]
