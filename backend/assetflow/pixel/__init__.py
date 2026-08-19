"""AssetFlow Pixel — a tecnologia Pixel Exact do produto (plano Pixel §69).

Este pacote é a resposta a uma regra nova do AssetFlow: no modo Pixel Art,
**"parecer Pixel Art" não é suficiente**. Um asset só é entregue como Pixel
Art quando tem resolução lógica real, 1 pixel lógico = 1 pixel do PNG, paleta
controlada, alpha binário, PNG lossless e validação técnica aprovada.

Duas responsabilidades, deliberadamente separadas (plano Pixel §6 e §104):

    PixelPostProcessor   pode alterar pixels
    PixelValidator       nunca altera pixels

E uma proibição que vale para o pacote inteiro (plano Pixel §5 e §105):
nenhum módulo daqui conhece SDXL, FLUX, diffusers, ``engine_id`` ou
checkpoint. Ele recebe ``(imagem, PixelOutputSpec)`` e devolve
``(imagem, relatórios)``. Por isso ele pertence à estante do AssetFlow, nunca
a uma gaveta.
"""

from .acceptance import PixelAcceptancePolicy
from .contracts import (
    AcceptanceDecision,
    PixelAssetStatus,
    PixelOutputSpec,
    PixelValidationReport,
    ProcessingReport,
)
from .preview import PreviewGenerator
from .processing import PixelPostProcessor
from .profiles import PixelProfileRegistry
from .service import PixelAssetOutcome, PixelAssetProcessor
from .validation import PixelValidator
from .version import (
    ACCEPTANCE_POLICY_VERSION,
    PIXEL_PIPELINE_VERSION,
    POSTPROCESSOR_VERSION,
    PREVIEW_GENERATOR_VERSION,
    VALIDATOR_VERSION,
)

__all__ = [
    "ACCEPTANCE_POLICY_VERSION",
    "PIXEL_PIPELINE_VERSION",
    "POSTPROCESSOR_VERSION",
    "PREVIEW_GENERATOR_VERSION",
    "VALIDATOR_VERSION",
    "AcceptanceDecision",
    "PixelAcceptancePolicy",
    "PixelAssetOutcome",
    "PixelAssetProcessor",
    "PixelAssetStatus",
    "PixelOutputSpec",
    "PixelPostProcessor",
    "PixelProfileRegistry",
    "PixelValidationReport",
    "PixelValidator",
    "PreviewGenerator",
    "ProcessingReport",
]
