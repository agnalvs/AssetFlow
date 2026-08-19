"""HARD CHECKS — requisitos objetivos do Pixel Exact (plano Pixel §39 a §45).

Os códigos são contrato público: aparecem nos relatórios, no frontend e no
benchmark. Não renomeie um código — crie outro.
"""

from .alpha import AlphaCheck
from .base import HardCheck, ValidationContext
from .bounds import BoundaryCheck
from .colors import ColorCountCheck
from .dimensions import DimensionsCheck
from .empty import EmptyImageCheck
from .palette import LockedPaletteCheck

__all__ = [
    "AlphaCheck",
    "BoundaryCheck",
    "ColorCountCheck",
    "DimensionsCheck",
    "EmptyImageCheck",
    "HardCheck",
    "LockedPaletteCheck",
    "ValidationContext",
]
