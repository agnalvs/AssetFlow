"""PixelValidator — quem mede e nunca altera (plano Pixel §37)."""

from .calibration import QualityCalibration
from .checks import HardCheck, ValidationContext
from .scoring import QualityScorer
from .service import PixelValidator, default_analyzers, default_checks

__all__ = [
    "HardCheck",
    "PixelValidator",
    "QualityCalibration",
    "QualityScorer",
    "ValidationContext",
    "default_analyzers",
    "default_checks",
]
