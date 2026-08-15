"""Pipelines de asset — a lógica de produto sobre o Kernel."""

from .base import AssetPipeline, ImageAssetPipeline, PipelineContext, PipelineOutcome
from .pixel import PixelCharacterPipeline
from .raw import RawImagePipeline
from .registry import PipelineRegistry
from .studio import StudioCharacterPipeline

__all__ = [
    "AssetPipeline",
    "ImageAssetPipeline",
    "PipelineContext",
    "PipelineOutcome",
    "PipelineRegistry",
    "PixelCharacterPipeline",
    "RawImagePipeline",
    "StudioCharacterPipeline",
]
