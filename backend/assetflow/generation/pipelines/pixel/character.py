"""PixelCharacterPipeline — o primeiro pipeline de produto (planos §56 e §57).

Ele sabe que está criando **personagem em Pixel Art**. Não sabe — e não pode
saber — qual tecnologia está produzindo os pixels.

    capability: text_to_image.pixel

Fluxo completo depois do Pixel Exact (plano Pixel §67)::

    PixelAssetRequest -> PromptBuilder -> Kernel -> Engine -> Raw Image
        -> PixelPostProcessor -> PixelValidator -> PixelAcceptancePolicy
        -> AssetStorage

Repare no que continua ausente: o contrato do motor não mudou nada para isso
acontecer (plano Pixel §68). O motor continua sabendo apenas ``generate()``;
o conhecimento Pixel Exact é do AssetFlow.
"""

from __future__ import annotations

from ....pixel import PixelProfileRegistry
from ....pixel.optimizer import AssetFlowPixelOptimizer
from ...postprocessing import PostProcessingChain, build_pixel_chain
from ..base import ImageAssetPipeline, PipelineContext

__all__ = ["PixelCharacterPipeline"]


class PixelCharacterPipeline(ImageAssetPipeline):
    """Personagens (e props) em Pixel Art."""

    id = "pixel.character"
    display_name = "Pixel Character Pipeline"

    def __init__(
        self,
        pixel_profiles: PixelProfileRegistry | None = None,
        optimizer: "AssetFlowPixelOptimizer | None" = None,
    ) -> None:
        # Os profiles Pixel entram por injeção porque são configuração
        # (`config/pixel_profiles.yaml`), não código: nenhum 64, 16 ou 128
        # pode ficar escrito aqui dentro (plano Pixel §64).
        self._pixel_profiles = pixel_profiles
        # O Pixel Optimizer, idem: teto de iterações e revisor moram em
        # `config/optimizer.yaml` (plano Optimizer §42). Sem instância, a
        # cadeia monta a padrão — a otimização não é opcional (§46).
        self._optimizer = optimizer

    @property
    def pixel_profiles(self) -> PixelProfileRegistry | None:
        return self._pixel_profiles

    def build_postprocessing_chain(self, context: PipelineContext) -> PostProcessingChain:
        # Toda a inteligência de Pixel Art do AssetFlow vive nesta cadeia,
        # e não dentro de um checkpoint (plano §24 e §58).
        return build_pixel_chain(self._pixel_profiles, self._optimizer)
