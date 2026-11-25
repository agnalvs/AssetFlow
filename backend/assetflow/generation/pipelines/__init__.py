"""Pipelines de asset — a lógica de produto sobre o Kernel."""

from .base import AssetPipeline, ImageAssetPipeline, PipelineContext, PipelineOutcome
from .pixel import PixelCharacterPipeline
from .registry import PipelineRegistry

__all__ = [
    "AssetPipeline",
    "ImageAssetPipeline",
    "PipelineContext",
    "PipelineOutcome",
    "PipelineRegistry",
    "PixelCharacterPipeline",
]
