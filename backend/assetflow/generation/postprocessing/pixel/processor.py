"""Pixel Post Processor — a cadeia completa de Pixel Art (plano §59).

Ordem das etapas (importa muito):

1. **logical resize** — leva 512×512 ao grid lógico (64×64);
2. **palette quantization** — impõe a paleta do profile;
3. **alpha cleanup** — binariza transparência;
4. **color count validation** — anota excesso de cores;
5. **grid validation** — confere integridade do grid.

Trocar o motor de geração não altera nada desta lista. É exatamente esse o
diferencial que o plano §24 manda proteger.
"""

from __future__ import annotations

from ..base import PostProcessingChain
from .alpha import AlphaCleanup
from .palette import PaletteQuantizer
from .resize import LogicalResize
from .validators import ColorCountValidator, GridValidator

__all__ = ["build_pixel_chain"]


def build_pixel_chain() -> PostProcessingChain:
    """Monta a cadeia padrão de Pixel Art.

    Cada etapa consulta o profile em ``applies_to`` — o mesmo encadeamento
    serve a profiles com e sem limpeza, com paleta fixa ou adaptativa.
    """
    return PostProcessingChain(
        (
            LogicalResize(),
            PaletteQuantizer(),
            AlphaCleanup(),
            ColorCountValidator(),
            GridValidator(),
        )
    )
