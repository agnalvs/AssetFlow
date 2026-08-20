"""Prompt Builders (plano §26).

Prompt engineering **não** mora dentro do motor. Ele mora aqui, no AssetFlow,
em objetos que conhecem o produto: personagem em Pixel Art, prop, background
2D. Trocar de motor não destrói essa inteligência.

Fluxo::

    Pedido humano -> ConstraintResolver -> FinalResolvedSpec
                  -> PromptBuilder      -> SemanticPrompt -> Generation Request

O que mudou com o Final Resolved Spec (plano T→J §37): o builder deixou de
consultar o Generation Profile. Ele lê o spec já resolvido — tipo, sujeito,
paleta, fundo — e é por isso que "tree" agora usa o vocabulário de **prop**,
com a lista de `avoid` de prop, em vez de ser tratado como personagem só
porque o profile pedido se chamava `pixel_character_64`.

O builder continua decidindo o que ninguém disse: vista, pose, o que evitar.
Essas decisões são *inferência*, e é assim que aparecem — no SemanticPrompt,
que a interface mostra por inteiro, e não como se a pessoa as tivesse pedido
(plano T→J §23).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from ..schemas import (
    AssetGenerationRequest,
    AssetMode,
    FinalResolvedSpec,
    SemanticComposition,
    SemanticPrompt,
    SemanticTechnical,
)

__all__ = [
    "PixelBackgroundPromptBuilder",
    "PixelCharacterPromptBuilder",
    "PixelPropPromptBuilder",
    "PromptBuilder",
    "PromptBuilderRegistry",
    "StudioBackgroundPromptBuilder",
    "StudioCharacterPromptBuilder",
    "StudioPropPromptBuilder",
    "resolve_semantic_prompt",
]


def resolve_semantic_prompt(
    request: AssetGenerationRequest,
    spec: FinalResolvedSpec,
    builders: PromptBuilderRegistry,
    *,
    prompt_builder: str | None = None,
) -> SemanticPrompt:
    """A semântica que vale para este pedido — vinda do pedido ou do builder.

    Existe uma função só para que o pipeline e o endpoint de pré-visualização
    não possam divergir. Se a precedência morasse nos dois lugares, a tela
    mostraria uma coisa e a geração faria outra, que é exatamente o problema
    que a pré-visualização existe para resolver.
    """
    if request.semantic_prompt is not None:
        return request.semantic_prompt
    return builders.resolve(spec, prompt_builder=prompt_builder).build(request, spec)


class PromptBuilder(ABC):
    """Converte o pedido do usuário em uma representação semântica."""

    id: str = "base"
    #: Termos que o produto sempre quer evitar para este tipo de asset.
    default_avoid: tuple[str, ...] = ()

    @abstractmethod
    def build(
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
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

    @staticmethod
    def _subject(request: AssetGenerationRequest, spec: FinalResolvedSpec) -> str:
        """O sujeito do spec, com a descrição bruta como último recurso.

        O spec ganha porque ele já teve as restrições numéricas removidas:
        mandar "tree 32x32, 8 colors" ao motor faria o modelo desenhar o
        texto (plano T→J §26).
        """
        return spec.asset.subject.strip() or request.prompt.strip()

    @staticmethod
    def _view(request: AssetGenerationRequest, spec: FinalResolvedSpec, default: str | None):
        """Vista resolvida > atributo do pedido > padrão do builder.

        Uma vista escrita na descrição ("vista lateral") já chegou aqui dentro
        do spec e ganha do padrão — que continua sendo inferência.
        """
        if spec.composition.view:
            return spec.composition.view
        return request.attributes.get("view", default)

    @staticmethod
    def _palette(spec: FinalResolvedSpec) -> int | None:
        palette = spec.palette
        if palette is None:
            return None
        if palette.mode == "locked":
            return len(palette.colors) or None
        return palette.max_colors

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
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        return SemanticPrompt(
            subject=self._subject(request, spec),
            medium="pixel_art",
            style=self._attr(request, "style"),
            view=self._view(request, spec, "side"),
            pose=self._attr(request, "pose", "idle"),
            appearance=self._appearance(request),
            details=self._details(request),
            avoid=self._avoid(request),
            composition=SemanticComposition(
                single_subject=True,
                centered=spec.composition.centered,
                full_body=bool(self._attr(request, "full_body", True)),
                isolated_background=spec.background.transparent,
                margin_ratio=spec.composition.margin_ratio or 0.08,
            ),
            technical=SemanticTechnical(
                clean_silhouette=True,
                sharp_edges=True,
                limited_palette=self._palette(spec),
                transparent_background=spec.background.transparent,
            ),
        )


class PixelPropPromptBuilder(PixelCharacterPromptBuilder):
    """Props e objetos em Pixel Art.

    É o builder que o bug da árvore nunca alcançava. Repare no ``avoid``: um
    prop não deve trazer personagem nem mão junto, e é justamente essa
    diferença que "tree" não recebia enquanto era classificado como
    personagem.
    """

    id = "pixel.prop"
    default_avoid = (
        "blur",
        "antialiasing",
        "photorealism",
        "text",
        "watermark",
        "characters",
        "people",
        "hands",
        "sprite sheet",
        "multiple objects",
        "grid layout",
    )

    def build(
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        prompt = super().build(request, spec)
        return prompt.model_copy(
            update={
                # Prop não tem pose nem "corpo inteiro": os dois campos
                # descrevem personagem, e mandá-los assim mesmo faz o motor
                # tentar dar postura a um barril.
                "pose": None,
                "view": self._view(request, spec, "front"),
                "composition": prompt.composition.model_copy(update={"full_body": None}),
            }
        )


class PixelBackgroundPromptBuilder(PixelCharacterPromptBuilder):
    """Cenários em Pixel Art."""

    id = "pixel.background"
    default_avoid = (
        "blur",
        "antialiasing",
        "photorealism",
        "text",
        "watermark",
        "characters in foreground",
        "sprite sheet",
        "grid layout",
    )

    def build(
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        prompt = super().build(request, spec)
        return prompt.model_copy(
            update={
                "pose": None,
                # Um cenário preenche o quadro: nada de sujeito único,
                # centralizado e recortado do fundo.
                "composition": SemanticComposition(
                    single_subject=False,
                    centered=False,
                    full_body=None,
                    isolated_background=False,
                ),
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
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        return SemanticPrompt(
            subject=self._subject(request, spec),
            medium=str(self._attr(request, "medium", "cartoon_2d")),
            style=self._attr(request, "style", "clean game art"),
            view=self._view(request, spec, "front"),
            pose=self._attr(request, "pose"),
            appearance=self._appearance(request),
            details=self._details(request),
            avoid=self._avoid(request),
            composition=SemanticComposition(
                single_subject=True,
                centered=spec.composition.centered,
                full_body=bool(self._attr(request, "full_body", True)),
                isolated_background=spec.background.transparent,
            ),
            technical=SemanticTechnical(
                clean_silhouette=True,
                sharp_edges=False,
                limited_palette=self._palette(spec),
                transparent_background=spec.background.transparent,
            ),
        )


class StudioPropPromptBuilder(StudioCharacterPromptBuilder):
    """Props e objetos em arte 2D convencional."""

    id = "studio.prop"
    default_avoid = (
        "pixel art",
        "low resolution",
        "text",
        "watermark",
        "characters",
        "people",
        "hands",
    )

    def build(
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        prompt = super().build(request, spec)
        return prompt.model_copy(
            update={
                "pose": None,
                "composition": prompt.composition.model_copy(update={"full_body": None}),
            }
        )


class StudioBackgroundPromptBuilder(StudioCharacterPromptBuilder):
    """Cenários e fundos em arte 2D convencional."""

    id = "studio.background"
    default_avoid = ("pixel art", "text", "watermark", "characters in foreground")

    def build(
        self, request: AssetGenerationRequest, spec: FinalResolvedSpec
    ) -> SemanticPrompt:
        prompt = super().build(request, spec)
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
    """Resolve o builder a partir do spec resolvido."""

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
                PixelBackgroundPromptBuilder(),
                StudioCharacterPromptBuilder(),
                StudioPropPromptBuilder(),
                StudioBackgroundPromptBuilder(),
            )
        )

    def register(self, builder: PromptBuilder) -> None:
        self._builders[builder.id] = builder

    def get(self, builder_id: str) -> PromptBuilder | None:
        return self._builders.get(builder_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))

    def resolve(
        self, spec: FinalResolvedSpec, *, prompt_builder: str | None = None
    ) -> PromptBuilder:
        """Escolhe o builder mais específico disponível para o spec.

        A chave do meio — ``"{modo}.{tipo}"`` — é onde a classificação
        semântica encosta no prompt: um pedido resolvido como
        ``pixel``/``prop`` cai em ``pixel.prop`` mesmo tendo sido pedido pelo
        profile `pixel_character_64`, porque quem manda no tipo é o spec
        (plano T→J §22 e §37).

        ``prompt_builder`` continua ganhando de tudo: é a fixação explícita
        que um Generation Profile pode declarar, e configuração explícita não
        é sobreposta por inferência.
        """
        candidates = [
            prompt_builder,
            f"{spec.asset.mode.value}.{spec.asset.type.value}",
            spec.pipeline_id,
        ]
        for candidate in candidates:
            if candidate and (builder := self._builders.get(candidate)):
                return builder

        fallback = (
            "pixel.character"
            if spec.asset.mode is AssetMode.PIXEL
            else "studio.character"
        )
        builder = self._builders.get(fallback)
        if builder is None:  # pragma: no cover - registro vazio
            raise KeyError(f"nenhum prompt builder disponível para '{spec.spec_id}'")
        return builder
