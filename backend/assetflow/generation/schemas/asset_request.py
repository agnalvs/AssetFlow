"""Pedido no nível do produto (plano §52).

Este é o objeto que a API recebe do frontend. Ele fala a língua do AssetFlow
— projeto, tipo de asset, profile — e **não** a língua da IA. É o pipeline
que o traduz para um :class:`ImageGenerationRequest`.

Repare que não existe aqui nenhum campo de motor obrigatório: o padrão é
``auto`` e o EngineResolver decide.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .capability import Capability
from .common import AssetFlowModel, AssetMode, AssetType, QualityLevel, new_id
from .request import EngineSelector, ReferenceImage, StructuralControl
from .semantic_prompt import SemanticPrompt

__all__ = ["AssetOutputOverrides", "AssetGenerationRequest"]


class AssetOutputOverrides(AssetFlowModel):
    """Ajustes pontuais sobre o que o profile já define."""

    variations: int | None = Field(default=None, ge=1, le=32)
    logical_width: int | None = Field(default=None, ge=8, le=1024)
    logical_height: int | None = Field(default=None, ge=8, le=1024)
    render_width: int | None = Field(default=None, ge=64, le=4096)
    render_height: int | None = Field(default=None, ge=64, le=4096)
    palette_size: int | None = Field(default=None, ge=2, le=256)
    transparent: bool | None = None


class AssetGenerationRequest(AssetFlowModel):
    """Pedido de criação de asset feito por um usuário do AssetFlow."""

    request_id: str = Field(default_factory=lambda: new_id("areq"))
    project_id: str
    user_id: str | None = None

    #: Profile é o caminho recomendado: ele carrega capability + pipeline.
    profile: str | None = None

    #: Alternativa de baixo nível, para diagnóstico ou fluxos avançados.
    capability: Capability | None = None
    pipeline: str | None = None

    asset_type: AssetType | None = None
    mode: AssetMode | None = None

    prompt: str = Field(description="Descrição em linguagem natural feita pelo usuário.")
    negative_prompt: str | None = None

    #: Atributos estruturados que o PromptBuilder converte em SemanticPrompt,
    #: ex.: {"view": "side", "pose": "idle", "appearance": {"armor": "blue"}}.
    attributes: dict[str, Any] = Field(default_factory=dict)

    #: Semântica pronta, escrita por quem pede (plano §26 e §28).
    #:
    #: Quando presente, ela **substitui** o PromptBuilder: o pedido deixa de
    #: dizer "interprete esta frase" e passa a dizer "gere exatamente isto".
    #: É o que permite corrigir uma leitura errada da descrição — trocar
    #: `view` de "side" para "front", tirar um termo do `avoid` — sem
    #: reescrever a frase até o builder concordar.
    #:
    #: O preço é explícito: os padrões de produto do builder (a lista de
    #: `avoid` que barra folha de sprite, a composição centralizada) não são
    #: reaplicados por cima. Quem manda a semântica manda inteira, e o que
    #: não estiver nela não vale. Por isso a interface mostra o JSON completo
    #: antes de deixar editar — o que ela exibe é literalmente o que vai.
    semantic_prompt: SemanticPrompt | None = None

    output: AssetOutputOverrides = Field(default_factory=AssetOutputOverrides)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    quality: QualityLevel = QualityLevel.STANDARD

    engine: EngineSelector = Field(default_factory=EngineSelector)
    engine_options: dict[str, dict[str, Any]] = Field(default_factory=dict)

    reference_images: tuple[ReferenceImage, ...] = ()
    structural_controls: tuple[StructuralControl, ...] = ()

    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
