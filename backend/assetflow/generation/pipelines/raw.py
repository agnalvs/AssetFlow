"""RawImagePipeline — geração sem regras de produto.

Útil para diagnosticar uma gaveta nova: mostra exatamente o que o motor
entregou, sem paleta, sem grid, sem limpeza. Serve também de contraprova de
que o pós-processamento é do AssetFlow e não do modelo.
"""

from __future__ import annotations

from ..postprocessing import PostProcessingChain
from .base import ImageAssetPipeline, PipelineContext

__all__ = ["RawImagePipeline"]


class RawImagePipeline(ImageAssetPipeline):
    """Persiste a imagem bruta do motor, sem transformação."""

    id = "raw.image"
    display_name = "Raw Image Pipeline"

    def build_postprocessing_chain(self, context: PipelineContext) -> PostProcessingChain:
        return PostProcessingChain(())
