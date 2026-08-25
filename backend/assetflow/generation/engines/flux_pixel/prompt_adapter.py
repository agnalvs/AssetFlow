"""Engine-specific Prompt Adapter do FLUX Pixel (plano §27; plano de motores §8.1).

O AssetFlow entrega um :class:`SemanticPrompt`. Este adapter o traduz para o
que **este** modelo entende melhor — e o FLUX quer coisa diferente do SDXL:

* ele responde bem a frases descritivas, não a listas de tags soltas;
* ele **não usa negative prompt** (guidance destilado), então a negação
  precisa virar afirmação: em vez de "sem folha de sprite", "um único
  personagem isolado";
* a LoRA de Pixel Art tem uma palavra de ativação, e ela vai na frente.

Se a gaveta for trocada, este arquivo desaparece junto — e o SemanticPrompt,
que é quem realmente atravessa a troca de motores, continua intacto.
"""

from __future__ import annotations

from ....generation.prompting import render_semantic_prompt
from ....generation.schemas import ImageGenerationRequest, SemanticPrompt

__all__ = ["FluxPixelPromptAdapter"]

#: Reforços por meio visual. Frases, não tags: é o dialeto do FLUX.
_MEDIUM_HINTS: dict[str, tuple[str, ...]] = {
    "pixel_art": (
        "pixel art",
        "crisp square pixels",
        "flat color blocks",
        "hard edges with no anti-aliasing",
    ),
    "cartoon_2d": ("2d game art", "clean shading", "bold outlines"),
}

#: O que no SDXL seria negative prompt. Aqui vira afirmação, porque o FLUX
#: destilado ignora a negação — pedir "sem grade de personagens" a um modelo
#: que não lê negativa é, na prática, pedir uma grade de personagens.
_POSITIVE_CONSTRAINTS: tuple[str, ...] = (
    "a single isolated subject",
    "centered in frame",
    "plain uncluttered background",
)


class FluxPixelPromptAdapter:
    """Adapta a semântica para o dialeto do FLUX."""

    id = "flux-pixel-v1"

    def __init__(self, lora_trigger: str | None = None) -> None:
        self._lora_trigger = lora_trigger

    def adapt(self, request: ImageGenerationRequest) -> tuple[str, str | None]:
        semantic = request.prompt.semantic
        if semantic is None:
            # Sem semântica: respeita o texto neutro, apenas garantindo o
            # gatilho da LoRA. Reescrever um texto que não veio do builder
            # seria inventar intenção que ninguém expressou.
            return self._with_trigger(request.prompt.positive), None

        positive, _negative = render_semantic_prompt(semantic)
        positive = self._reinforce(semantic, positive)
        # O segundo elemento é `None` de propósito: o manifesto declara
        # `negative_prompt: false`, e o Kernel avisa o usuário de que o campo
        # foi ignorado (plano §44). Melhor um aviso honesto do que um campo
        # aceito e descartado em silêncio.
        return positive, None

    # ------------------------------------------------------------------
    def _reinforce(self, semantic: SemanticPrompt, positive: str) -> str:
        terms = [term for term in positive.split(", ") if term]
        terms.extend(_MEDIUM_HINTS.get(semantic.medium, ()))
        if semantic.composition.single_subject:
            terms.extend(_POSITIVE_CONSTRAINTS)
        if semantic.technical.limited_palette:
            terms.append(
                f"limited palette of about {semantic.technical.limited_palette} colors"
            )
        return self._with_trigger(", ".join(dict.fromkeys(terms)))

    def _with_trigger(self, positive: str) -> str:
        """Põe a palavra de ativação da LoRA na frente, sem duplicá-la."""
        trigger = (self._lora_trigger or "").strip()
        if not trigger:
            return positive
        if trigger.lower() in positive.lower():
            return positive
        return f"{trigger}, {positive}" if positive else trigger
