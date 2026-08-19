"""QUALITY ANALYZERS — indicadores, nunca vereditos (plano Pixel §47 a §55)."""

from .base import AnalysisResult, QualityAnalyzer, ValidationContext
from .clusters import ClusterAnalyzer
from .color_redundancy import ColorRedundancyAnalyzer
from .occupancy import SpriteOccupancyAnalyzer
from .orphan_pixels import OrphanPixelAnalyzer
from .outline import OutlineAnalyzer
from .palette_usage import PaletteUsageAnalyzer

__all__ = [
    "AnalysisResult",
    "ClusterAnalyzer",
    "ColorRedundancyAnalyzer",
    "OrphanPixelAnalyzer",
    "OutlineAnalyzer",
    "PaletteUsageAnalyzer",
    "QualityAnalyzer",
    "SpriteOccupancyAnalyzer",
    "ValidationContext",
]
