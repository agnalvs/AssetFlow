"""Cadeia de Pixel Art do pipeline de geração (plano §59, plano Pixel §67).

Até a versão anterior esta cadeia tinha cinco etapas próprias (resize, paleta,
alpha e dois validadores). Elas foram promovidas: a lógica inteira virou o
pacote ``assetflow.pixel``, com estágios substituíveis, hard checks separados
dos indicadores de qualidade, política de aceitação e relatórios versionados
(plano Pixel §63).

O que sobrou aqui é o encaixe: uma cadeia de um elo só, o
:class:`~assetflow.generation.postprocessing.pixel.exact.PixelExactProcessor`.
Trocar o motor de geração continua não alterando nada disto — que é
exatamente o diferencial que o plano §24 manda proteger.
"""

from __future__ import annotations

from ....pixel import PixelAssetProcessor, PixelProfileRegistry
from ....pixel.optimizer import AssetFlowPixelOptimizer
from ..base import PostProcessingChain
from .exact import PixelExactProcessor

__all__ = ["build_pixel_chain"]


def build_pixel_chain(
    registry: PixelProfileRegistry | None = None,
    optimizer: AssetFlowPixelOptimizer | None = None,
) -> PostProcessingChain:
    """Monta a cadeia padrão de Pixel Art.

    Args:
        registry: profiles Pixel carregados de ``config/pixel_profiles.yaml``.
            Sem ele, o spec é derivado do próprio Generation Profile — é o que
            mantém profiles antigos funcionando (ver ``spec.py``).
        optimizer: o Pixel Optimizer configurado em ``config/optimizer.yaml``.
            ``None`` **não** desliga a otimização: ela é parte do pipeline
            (plano Optimizer §46), e sem instância configurada o
            :class:`PixelAssetProcessor` monta a padrão. Para desligá-la de
            verdade é preciso passar um ``AssetFlowPixelOptimizer(enabled=False)``,
            e aí o job registra o status ``disabled``.
    """
    if optimizer is None:
        return PostProcessingChain((PixelExactProcessor(registry),))
    return PostProcessingChain(
        (
            PixelExactProcessor(
                registry, processor=PixelAssetProcessor(optimizer=optimizer)
            ),
        )
    )
