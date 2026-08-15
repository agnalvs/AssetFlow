"""PixelCharacterPipeline — o primeiro pipeline de produto (planos §56 e §57).

Ele sabe que está criando **personagem em Pixel Art**. Não sabe — e não pode
saber — qual tecnologia está produzindo os pixels.

    capability: text_to_image.pixel

Se amanhã o `text_to_image.pixel` for atendido por um modelo especializado
novo, este arquivo continua idêntico.
"""

from __future__ import annotations

from ...postprocessing import PostProcessingChain, build_pixel_chain
from ..base import ImageAssetPipeline, PipelineContext

__all__ = ["PixelCharacterPipeline"]


class PixelCharacterPipeline(ImageAssetPipeline):
    """Personagens (e props) em Pixel Art."""

    id = "pixel.character"
    display_name = "Pixel Character Pipeline"

    def build_postprocessing_chain(self, context: PipelineContext) -> PostProcessingChain:
        # Toda a inteligência de Pixel Art do AssetFlow vive nesta cadeia,
        # e não dentro de um checkpoint (plano §24 e §58).
        return build_pixel_chain()
