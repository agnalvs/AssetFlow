"""Generation Profiles (plano §25).

Um profile descreve **o que** deve ser produzido: resolução lógica, paleta,
pós-processamento, quantas variações. Ele nunca cita um motor.

    pixel_character_64  ->  capability: text_to_image.pixel
                            logical: 64x64, paleta 16 cores

Quando o motor de Pixel Art for substituído, nenhum profile muda.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from ..schemas import AssetFlowModel, AssetSpec, Capability

__all__ = [
    "ProfileOutput",
    "ProfilePalette",
    "ProfilePostProcessing",
    "GenerationProfile",
]


class ProfileOutput(AssetFlowModel):
    """Resoluções do profile.

    A distinção lógico × render é central para Pixel Art: o motor gera em
    alta resolução e o AssetFlow reduz para o grid lógico com suas próprias
    regras (plano §59). Nenhum motor decide isso.
    """

    #: Resolução final do asset em Pixel Art (None para arte 2D convencional).
    logical_width: int | None = Field(default=None, ge=8, le=1024)
    logical_height: int | None = Field(default=None, ge=8, le=1024)
    #: Resolução pedida ao motor.
    render_width: int = Field(default=512, ge=64, le=4096)
    render_height: int = Field(default=512, ge=64, le=4096)
    variations: int = Field(default=1, ge=1, le=32)
    transparent: bool = False

    @property
    def is_logical(self) -> bool:
        return self.logical_width is not None and self.logical_height is not None


class ProfilePalette(AssetFlowModel):
    """Regras de paleta do AssetFlow (propriedade do produto, não do modelo)."""

    size: int | None = Field(default=None, ge=2, le=256)
    strategy: str = Field(default="adaptive", pattern=r"^(adaptive|fixed)$")
    fixed_colors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> "ProfilePalette":
        if self.strategy == "fixed" and not self.fixed_colors:
            raise ValueError("paleta 'fixed' exige 'fixed_colors'")
        return self


class ProfilePostProcessing(AssetFlowModel):
    """O que o pós-processamento deve aplicar (plano §59)."""

    pixel_cleanup: bool = False
    antialiasing: bool = False
    alpha_threshold: int = Field(default=128, ge=0, le=255)
    validate_color_count: bool = False
    validate_grid: bool = False
    #: >1 amplia (Pixel Art), <1 reduz (arte 2D). 0 desativa o thumbnail.
    thumbnail_scale: float = Field(default=1.0, ge=0.0, le=32.0)


class GenerationProfile(AssetFlowModel):
    """Perfil de geração, carregado de ``config/profiles.yaml``."""

    id: str
    display_name: str = ""
    capability: Capability
    pipeline: str
    asset: AssetSpec = Field(default_factory=AssetSpec)
    output: ProfileOutput = Field(default_factory=ProfileOutput)
    palette: ProfilePalette = Field(default_factory=ProfilePalette)
    postprocessing: ProfilePostProcessing = Field(default_factory=ProfilePostProcessing)

    #: Prompt builder a usar; `None` deixa o pipeline escolher o seu padrão.
    prompt_builder: str | None = None

    #: Profile Pixel Exact de `config/pixel_profiles.yaml` (plano Pixel §64).
    #:
    #: Quando presente, ele é a fonte única da verdade técnica do arquivo
    #: final — resolução lógica real, paleta, alpha binário, canvas, preview e
    #: quais requisitos são obrigatórios. Sem ele, o pós-processamento deriva
    #: um spec dos campos abaixo, e profiles antigos continuam funcionando.
    pixel_profile: str | None = None

    #: Opções por motor associadas ao profile (plano §20). Continuam sendo
    #: ignoradas por qualquer motor que não se reconheça na chave.
    engine_options: dict[str, dict[str, Any]] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)
