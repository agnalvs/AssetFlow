"""PixelPostProcessor — quem pode alterar pixels (plano Pixel §6)."""

from .service import PixelPostProcessor, ProcessingOutcome, default_transforms
from .stages import PixelContext, PixelExporter, PixelTransform

__all__ = [
    "PixelContext",
    "PixelExporter",
    "PixelPostProcessor",
    "PixelTransform",
    "ProcessingOutcome",
    "default_transforms",
]
