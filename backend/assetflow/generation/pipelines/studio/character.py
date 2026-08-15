"""StudioCharacterPipeline — arte 2D convencional (plano §60).

Existe desde já para provar a afirmação do plano: acrescentar o modo Studio
**não muda o Kernel**. É o mesmo contrato, o mesmo resolver, o mesmo job
system — apenas outra capacidade (``text_to_image.general``) e outra cadeia
de pós-processamento.
"""

from __future__ import annotations

from ...postprocessing import PostProcessingChain, build_studio_chain
from ..base import ImageAssetPipeline, PipelineContext

__all__ = ["StudioCharacterPipeline"]


class StudioCharacterPipeline(ImageAssetPipeline):
    """Personagens, props e backgrounds em arte 2D convencional."""

    id = "studio.character"
    display_name = "Studio 2D Pipeline"

    def build_postprocessing_chain(self, context: PipelineContext) -> PostProcessingChain:
        return build_studio_chain()
