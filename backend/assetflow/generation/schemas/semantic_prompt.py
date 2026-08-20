"""Semantic Prompt (plano §28).

A inteligência do AssetFlow sobre assets vive aqui — em uma representação
**semântica e independente de motor**. Cada engine recebe este objeto e o
traduz para o formato de prompt que a sua tecnologia entende melhor
(plano §27), sem que o conhecimento do produto seja perdido na troca.

Trocar SDXL por FLUX descarta o adapter, nunca o SemanticPrompt.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import AssetFlowModel

__all__ = [
    "PromptPreview",
    "SemanticComposition",
    "SemanticPrompt",
    "SemanticTechnical",
]


class SemanticComposition(AssetFlowModel):
    """Como o sujeito deve ocupar o quadro."""

    single_subject: bool = True
    centered: bool = True
    full_body: bool | None = None
    isolated_background: bool = True
    margin_ratio: float | None = Field(
        default=None,
        ge=0.0,
        le=0.4,
        description="Margem livre desejada ao redor do sujeito, como fração do lado.",
    )


class SemanticTechnical(AssetFlowModel):
    """Requisitos técnicos independentes de tecnologia de geração."""

    clean_silhouette: bool = True
    sharp_edges: bool | None = None
    limited_palette: int | None = Field(
        default=None, ge=2, le=256, description="Quantidade alvo de cores, quando aplicável."
    )
    no_text: bool = True
    no_watermark: bool = True
    transparent_background: bool = False


class SemanticPrompt(AssetFlowModel):
    """Descrição estruturada do asset desejado.

    Nenhum campo aqui é específico de um motor. ``subject``/``medium`` são
    obrigatórios; o resto é opcional e cresce conforme o produto evolui.
    """

    subject: str = Field(description="Sujeito principal, ex.: 'young warrior'.")
    medium: str = Field(
        default="pixel_art",
        description="Meio visual pretendido, ex.: 'pixel_art', 'cartoon_2d'.",
    )
    style: str | None = Field(default=None, description="Estilo, ex.: 'dark fantasy'.")
    view: str | None = Field(default=None, description="Vista, ex.: 'side', 'top_down'.")
    pose: str | None = Field(default=None, description="Pose/estado, ex.: 'idle'.")

    appearance: dict[str, str] = Field(
        default_factory=dict,
        description="Atributos visuais livres, ex.: {'armor': 'blue', 'hair': 'brown'}.",
    )
    details: list[str] = Field(
        default_factory=list, description="Detalhes adicionais em texto livre."
    )
    avoid: list[str] = Field(
        default_factory=list, description="O que não deve aparecer (base do negative prompt)."
    )

    composition: SemanticComposition = Field(default_factory=SemanticComposition)
    technical: SemanticTechnical = Field(default_factory=SemanticTechnical)

    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Espaço de expansão para futuros conceitos de produto.",
    )

    def descriptors(self) -> list[str]:
        """Lista plana de descritores, útil para adapters simples."""
        parts: list[str] = [self.subject]
        if self.style:
            parts.append(self.style)
        if self.view:
            parts.append(f"{self.view} view")
        if self.pose:
            parts.append(f"{self.pose} pose")
        parts.extend(f"{key} {value}" for key, value in sorted(self.appearance.items()))
        parts.extend(self.details)
        return [part for part in parts if part]


class PromptPreview(AssetFlowModel):
    """O que o AssetFlow entendeu de um pedido, sem gerar nada (plano §26).

    Serve para fechar o laço entre a frase que a pessoa escreveu e o que o
    sistema fará com ela: dá para olhar a leitura, discordar dela e mandar
    outra de volta em ``AssetGenerationRequest.semantic_prompt``.

    Sobre ``positive``/``negative``: é a renderização **neutra**, a do
    adapter genérico do AssetFlow. Um motor que tenha adapter próprio relê o
    ``semantic`` no dialeto dele e recebe outro texto (plano §27) — por isso
    quem manda aqui é o ``semantic``, e o texto é material de conferência
    humana, não a string que chega no modelo.
    """

    #: Profile resolvido para o pedido — inclusive o ad hoc, quando é o caso.
    profile: str
    capability: str
    semantic: SemanticPrompt
    positive: str
    negative: str | None = None
    #: ``builder`` = o AssetFlow interpretou a descrição; ``request`` = a
    #: semântica veio pronta no pedido e o builder não opinou.
    source: Literal["builder", "request"] = "builder"
