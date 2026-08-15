"""Generation Request universal (plano §19 e §20).

Este é o contrato que atravessa todo o sistema. Ele descreve **o que gerar**,
jamais **como** nem **com qual tecnologia**.

Parâmetros específicos de um motor (``steps``, ``guidance``, refiners, etc.)
não entram aqui: vão em ``engine_options[<engine_id>]`` e são simplesmente
ignorados por qualquer outro motor (plano §20).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from .capability import Capability
from .common import AssetFlowModel, AssetMode, AssetType, QualityLevel, new_id
from .semantic_prompt import SemanticPrompt

__all__ = [
    "AssetSpec",
    "PromptSpec",
    "OutputSpec",
    "GenerationParams",
    "EngineSelector",
    "ReferenceImage",
    "StructuralControl",
    "ImageGenerationRequest",
]


class AssetSpec(AssetFlowModel):
    """O que o pedido representa em termos de produto."""

    type: AssetType = AssetType.RAW
    mode: AssetMode = AssetMode.PIXEL


class PromptSpec(AssetFlowModel):
    """Prompt em duas camadas.

    - ``semantic``: representação independente de motor (fonte da verdade);
    - ``positive``/``negative``: renderização textual neutra, produzida pelo
      adapter genérico, para motores que não queiram interpretar a semântica.

    Um motor pode ignorar o texto e traduzir o ``semantic`` do seu jeito.
    """

    positive: str = ""
    negative: str | None = None
    semantic: SemanticPrompt | None = None

    @model_validator(mode="after")
    def _require_something(self) -> "PromptSpec":
        if not self.positive.strip() and self.semantic is None:
            raise ValueError("o request precisa de 'prompt.positive' ou 'prompt.semantic'")
        return self


class OutputSpec(AssetFlowModel):
    """Saída pedida ao motor.

    Atenção: para Pixel Art estas dimensões são a **resolução de render**, não
    a resolução lógica do asset. A redução para o grid lógico é feita pelo
    pós-processamento do AssetFlow (plano §23), nunca pelo motor.
    """

    width: int = Field(default=512, ge=8, le=8192)
    height: int = Field(default=512, ge=8, le=8192)
    variations: int = Field(default=1, ge=1, le=32)
    transparent: bool = False
    format: str = Field(default="png", pattern=r"^(png|webp)$")


class GenerationParams(AssetFlowModel):
    """Parâmetros universais de geração.

    Deliberadamente enxuto. ``quality`` é um knob abstrato que cada motor
    traduz para o que fizer sentido na sua tecnologia.
    """

    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    quality: QualityLevel = QualityLevel.STANDARD
    #: Quando `True`, o motor deve derivar seeds determinísticas por variação.
    deterministic_variations: bool = True


class EngineSelector(AssetFlowModel):
    """Seleção de motor (plano §14).

    Por padrão ``auto``: o EngineResolver decide. Usuários avançados podem
    fixar um motor específico — e, nesse caso, podem também desligar o
    fallback para garantir reprodutibilidade.
    """

    mode: str = Field(default="auto", pattern=r"^(auto|manual)$")
    engine_id: str | None = None
    allow_fallback: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "EngineSelector":
        if self.mode == "manual" and not self.engine_id:
            raise ValueError("engine.mode='manual' exige 'engine.engine_id'")
        return self


class ReferenceImage(AssetFlowModel):
    """Imagem de referência (plano §30 — IP-Adapter, consistência visual).

    Já faz parte do contrato para que a arquitetura não precise mudar quando
    o recurso for implementado. Motores declaram ``supports.image_reference``.
    """

    uri: str
    role: str = Field(
        default="style",
        description="style | identity | pose | composition | palette",
    )
    weight: float = Field(default=1.0, ge=0.0, le=2.0)


class StructuralControl(AssetFlowModel):
    """Condicionamento estrutural (plano §31 — ControlNet).

    Igualmente previsto, não implementado nesta fase.
    """

    uri: str
    kind: str = Field(default="pose", description="pose | edges | depth | segmentation")
    weight: float = Field(default=1.0, ge=0.0, le=2.0)


class ImageGenerationRequest(AssetFlowModel):
    """Pedido universal de geração de imagem.

    É o único objeto que o Generation Kernel entrega a uma gaveta.
    """

    request_id: str = Field(default_factory=lambda: new_id("req"))
    capability: Capability
    asset: AssetSpec = Field(default_factory=AssetSpec)
    prompt: PromptSpec
    output: OutputSpec = Field(default_factory=OutputSpec)
    generation: GenerationParams = Field(default_factory=GenerationParams)
    engine: EngineSelector = Field(default_factory=EngineSelector)

    reference_images: tuple[ReferenceImage, ...] = ()
    structural_controls: tuple[StructuralControl, ...] = ()

    engine_options: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Opções específicas por motor, chaveadas por engine_id. "
            "Motores que não se reconhecem na chave simplesmente ignoram."
        ),
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Rastro livre do chamador (projeto, pipeline, profile...).",
    )

    def options_for(self, engine_id: str) -> dict[str, Any]:
        """Opções destinadas a um motor específico (vazio se não houver)."""
        return dict(self.engine_options.get(engine_id, {}))

    def with_seed(self, seed: int) -> "ImageGenerationRequest":
        """Cópia com seed fixa — usado pelo retry e pelas variações."""
        return self.model_copy(
            update={"generation": self.generation.model_copy(update={"seed": seed})},
            deep=True,
        )
