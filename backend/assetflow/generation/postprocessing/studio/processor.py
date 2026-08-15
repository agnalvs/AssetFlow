"""Pós-processamento de arte 2D convencional.

Muito mais leve que o de Pixel Art — arte 2D não tem grid nem paleta
limitada. Existe desde já para provar que o Kernel não muda quando o modo
Studio entra (plano §60).

Evoluções previstas: recorte de fundo, normalização de margem, extração de
camadas e variações por região.
"""

from __future__ import annotations

from ..base import ImageBuffer, PostProcessContext, PostProcessingChain, PostProcessor

__all__ = ["EnsureRGBA", "build_studio_chain"]


class EnsureRGBA(PostProcessor):
    """Normaliza o modo de cor e registra métricas básicas."""

    name = "studio.ensure_rgba"

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        image = buffer.image.convert("RGBA")
        buffer.metadata["mode"] = "RGBA"
        buffer.metadata["source_size"] = list(image.size)
        return buffer.replace(image)


def build_studio_chain() -> PostProcessingChain:
    """Cadeia padrão do modo Studio."""
    return PostProcessingChain((EnsureRGBA(),))
