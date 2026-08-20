"""Prompt Builders (plano §26).

Prompt engineering **não** mora dentro do motor. Ele mora aqui, no AssetFlow,
em objetos que conhecem o produto: personagem em Pixel Art, prop, background
2D. Trocar de motor não destrói essa inteligência.

Fluxo::

    Pedido humano -> PromptBuilder -> SemanticPrompt -> Generation Request
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from ..profiles import GenerationProfile
from ..schemas import (
    AssetGenerationRequest,
    AssetMode,
    SemanticComposition,
    SemanticPrompt,
    SemanticTechnical,
)

__all__ = [
    "PixelCharacterPromptBuilder",
    "PixelPropPromptBuilder",
    "PromptBuilder",
    "PromptBuilderRegistry",
    "StudioBackgroundPromptBuilder",
    "StudioCharacterPromptBuilder",
    "resolve_semantic_prompt",
]


def resolve_semantic_prompt(
    request: AssetGenerationRequest,
    profile: GenerationProfile,
    builders: PromptBuilderRegistry,
) -> SemanticPrompt:
    """A semântica que vale para este pedido — vinda do pedido ou do builder.

    Existe uma função só para que o pipeline e o endpoint de pré-visualização
    não possam divergir. Se a precedência morasse nos dois lugares, a tela
    mostraria uma coisa e a geração faria outra, que é exatamente o problema
    que a pré-visualização existe para resolver.
    """
    if request.semantic_prompt is not None:
        return request.semantic_prompt
    return builders.resolve(profile).build(request, profile)


class PromptBuilder(ABC):
    """Converte o pedido do usuário em uma representação semântica."""

    id: str = "base"
    #: Termos que o produto sempre quer evitar para este tipo de asset.
    default_avoid: tuple[str, ...] = ()

    @abstractmethod
    def build(
        self, request: AssetGenerationRequest, profile: GenerationProfile
    ) -> SemanticPrompt:
        ...

    # -- utilidades compartilhadas --------------------------------------
    @staticmethod
    def _attr(request: AssetGenerationRequest, key: str, default: Any = None) -> Any:
        return request.attributes.get(key, default)

    @staticmethod
    def _appearance(request: AssetGenerationRequest) -> dict[str, str]:
        raw = request.attributes.get("appearance") or {}
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    @staticmethod
    def _details(request: AssetGenerationRequest) -> list[str]:
        raw = request.attributes.get("details") or []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, Iterable):
            return [str(item) for item in raw]
        return []

    def _avoid(self, request: AssetGenerationRequest) -> list[str]:
        avoid = list(self.default_avoid)
        extra = request.attributes.get("avoid") or []
        if isinstance(extra, str):
            avoid.append(extra)
        elif isinstance(extra, Iterable):
            avoid.extend(str(item) for item in extra)
        if request.negative_prompt:
            avoid.append(request.negative_prompt)
        return list(dict.fromkeys(avoid))


class PixelCharacterPromptBuilder(PromptBuilder):
    """Personagens em Pixel Art."""

    id = "pixel.character"
    #: Um asset de personagem é **um** personagem. Modelos treinados em
    #: acervos de Pixel Art tendem fortemente a devolver folhas de sprite
    #: (várias poses em grade), porque é assim que esse material circula na
    #: internet. Barrar isso é regra de produto do AssetFlow, não peculiaridade
    #: de um motor — por isso mora aqui, e não dentro de uma gaveta.
    default_avoid = (
        "blur",
        "antialiasing",
        "gradient noise",
        "photorealism",
        "3d render",
        "text",
        "watermark",
        "multiple characters",
        "sprite sheet",
        "character sheet",
        "multiple poses",
        "grid layout",
        "collage",
        "tiled panels",
        "frame borders",
    )

    def build(
        self, request: AssetGenerationRequest, profile: GenerationProfile
    ) -> SemanticPrompt:
        return SemanticPrompt(
            subject=request.prompt.strip(),
            medium="pixel_art",
            style=self._attr(request, "style"),
            view=self._attr(request, "view", "side"),
            pose=self._attr(request, "pose", "idle"),
            appearance=self._appearance(request),
            details=self._details(request),
            avoid=self._avoid(request),
            composition=SemanticComposition(
                single_subject=True,
                centered=True,
                full_body=bool(self._attr(request, "full_body", True)),
                isolated_background=True,
                margin_ratio=0.08,
            ),
            technical=SemanticTechnical(
                clean_silhouette=True,
                sharp_edges=True,
                limited_palette=profile.palette.size,
                transparent_background=profile.output.transparent,
            ),
            extra={
                "logical_size": [profile.output.logical_width, profile.output.logical_height],
                "asset_type": profile.asset.type.value,
            },
        )


class PixelPropPromptBuilder(PixelCharacterPromptBuilder):
    """Props e objetos em Pixel Art."""

    id = "pixel.prop"
    default_avoid = (
        "blur",
        "antialiasing",
        "photorealism",
        "text",
        "watermark",
        "characters",
        "hands",
    )

    def build(
        self, request: AssetGenerationRequest, profile: GenerationProfile
    ) -> SemanticPrompt:
        prompt = super().build(request, profile)
        return prompt.model_copy(
            update={
                "pose": None,
                "composition": prompt.composition.model_copy(update={"full_body": None}),
            }
        )


class StudioCharacterPromptBuilder(PromptBuilder):
    """Personagens em arte 2D convencional."""

    id = "studio.character"
    default_avoid = (
        "pixel art",
        "low resolution",
        "text",
        "watermark",
        "extra limbs",
        "cropped",
    )

    def build(
        self, request: AssetGenerationRequest, profile: GenerationProfile
    ) -> SemanticPrompt:
        return SemanticPrompt(
            subject=request.prompt.strip(),
            medium=str(self._attr(request, "medium", "cartoon_2d")),
            style=self._attr(request, "style", "clean game art"),
            view=self._attr(request, "view", "front"),
            pose=self._attr(request, "pose"),
            appearance=self._appearance(request),
            details=self._details(request),
            avoid=self._avoid(request),
            composition=SemanticComposition(
                single_subject=True,
                centered=True,
                full_body=bool(self._attr(request, "full_body", True)),
                isolated_background=profile.output.transparent,
            ),
            technical=SemanticTechnical(
                clean_silhouette=True,
                sharp_edges=False,
                transparent_background=profile.output.transparent,
            ),
            extra={"asset_type": profile.asset.type.value},
        )


class StudioBackgroundPromptBuilder(StudioCharacterPromptBuilder):
    """Cenários e fundos em arte 2D convencional."""

    id = "studio.background"
    default_avoid = ("pixel art", "text", "watermark", "characters in foreground")

    def build(
        self, request: AssetGenerationRequest, profile: GenerationProfile
    ) -> SemanticPrompt:
        prompt = super().build(request, profile)
        return prompt.model_copy(
            update={
                "composition": SemanticComposition(
                    single_subject=False,
                    centered=False,
                    full_body=None,
                    isolated_background=False,
                )
            }
        )


class PromptBuilderRegistry:
    """Resolve o builder a partir do id do profile/pipeline ou do modo."""

    def __init__(self, builders: Iterable[PromptBuilder] = ()) -> None:
        self._builders: dict[str, PromptBuilder] = {
            builder.id: builder for builder in builders
        }

    @classmethod
    def with_defaults(cls) -> "PromptBuilderRegistry":
        return cls(
            (
                PixelCharacterPromptBuilder(),
                PixelPropPromptBuilder(),
                StudioCharacterPromptBuilder(),
                StudioBackgroundPromptBuilder(),
            )
        )

    def register(self, builder: PromptBuilder) -> None:
        self._builders[builder.id] = builder

    def get(self, builder_id: str) -> PromptBuilder | None:
        return self._builders.get(builder_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))

    def resolve(self, profile: GenerationProfile) -> PromptBuilder:
        """Escolhe o builder mais específico disponível para o profile."""
        candidates = [
            profile.prompt_builder,
            f"{profile.asset.mode.value}.{profile.asset.type.value}",
            profile.pipeline,
        ]
        for candidate in candidates:
            if candidate and (builder := self._builders.get(candidate)):
                return builder

        fallback = (
            "pixel.character"
            if profile.asset.mode is AssetMode.PIXEL
            else "studio.character"
        )
        builder = self._builders.get(fallback)
        if builder is None:  # pragma: no cover - registro vazio
            raise KeyError(f"nenhum prompt builder disponível para '{profile.id}'")
        return builder
