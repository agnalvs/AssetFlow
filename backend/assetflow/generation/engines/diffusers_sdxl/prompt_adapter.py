"""Engine-specific Prompt Adapter do SDXL (plano §27).

O AssetFlow entrega um :class:`SemanticPrompt`. Este adapter o traduz para o
formato que **este** modelo entende melhor. Se a gaveta for trocada, este
arquivo desaparece junto — e o SemanticPrompt continua intacto.
"""

from __future__ import annotations

from ....generation.prompting import render_semantic_prompt
from ....generation.schemas import ImageGenerationRequest, SemanticPrompt

__all__ = ["SDXLPromptAdapter"]

#: Reforços que funcionam bem com SDXL, por meio visual.
_MEDIUM_HINTS: dict[str, tuple[str, ...]] = {
    "pixel_art": (
        "pixel art sprite",
        "16-bit game asset",
        "crisp pixel grid",
        "flat colors",
        "no anti-aliasing",
    ),
    "cartoon_2d": ("2d game art", "clean vector-like shading", "bold outlines"),
}

_BASE_NEGATIVE = (
    "blurry",
    "jpeg artifacts",
    "low quality",
    "deformed",
    "extra limbs",
    "signature",
)


class SDXLPromptAdapter:
    """Adapta a semântica para o dialeto do SDXL."""

    id = "diffusers-sdxl-v1"

    def adapt(self, request: ImageGenerationRequest) -> tuple[str, str | None]:
        semantic = request.prompt.semantic
        if semantic is None:
            # Sem semântica disponível: respeita o texto neutro recebido.
            return request.prompt.positive, request.prompt.negative

        positive, negative = render_semantic_prompt(semantic)
        positive = self._reinforce(semantic, positive)
        negative_terms = [term for term in (negative or "").split(", ") if term]
        negative_terms.extend(_BASE_NEGATIVE)
        return positive, ", ".join(dict.fromkeys(negative_terms)) or None

    @staticmethod
    def _reinforce(semantic: SemanticPrompt, positive: str) -> str:
        hints = _MEDIUM_HINTS.get(semantic.medium, ())
        if not hints:
            return positive
        terms = [term for term in positive.split(", ") if term]
        terms.extend(hints)
        return ", ".join(dict.fromkeys(terms))
