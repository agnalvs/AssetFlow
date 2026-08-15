"""Registro persistido de cada geração (planos §41 e §42).

Nunca depender apenas do nome do modelo: guardamos motor, versão do motor,
modelo, revisão, prompt humano, prompt semântico, seed, parâmetros, saídas e
tempos. É esse registro que permite, meses depois, reproduzir um asset ou
comparar motores.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ..generation.schemas import (
    AssetFlowModel,
    Capability,
    EngineRef,
    SemanticPrompt,
    StageTimings,
    new_id,
    utcnow,
)

__all__ = ["GenerationRecordOutput", "GenerationRecord"]


class GenerationRecordOutput(AssetFlowModel):
    """Uma saída persistida."""

    index: int
    uri: str
    thumbnail_uri: str | None = None
    width: int
    height: int
    logical_width: int | None = None
    logical_height: int | None = None
    seed: int | None = None
    color_count: int | None = None
    palette: tuple[str, ...] = ()


class GenerationRecord(AssetFlowModel):
    """Linha do histórico de gerações."""

    id: str = Field(default_factory=lambda: new_id("rec"))
    created_at: datetime = Field(default_factory=utcnow)

    # -- Contexto de produto -------------------------------------------
    job_id: str
    project_id: str
    user_id: str | None = None
    asset_id: str | None = None
    profile_id: str | None = None
    pipeline_id: str | None = None
    capability: Capability

    # -- Rastreabilidade do motor (plano §42) --------------------------
    engine_id: str
    engine_version: str
    model_id: str | None = None
    model_revision: str | None = None
    engine_provider: str | None = None
    fallback_used: bool = False
    attempted_engines: tuple[str, ...] = ()

    # -- Entrada --------------------------------------------------------
    user_prompt: str = ""
    positive_prompt: str = ""
    negative_prompt: str | None = None
    semantic_prompt: SemanticPrompt | None = None
    seed: int | None = None
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    engine_options: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # -- Saída ----------------------------------------------------------
    outputs: tuple[GenerationRecordOutput, ...] = ()
    timings: StageTimings = Field(default_factory=StageTimings)
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def engine_fields(cls, engine: EngineRef) -> dict[str, Any]:
        """Extrai os campos de rastreabilidade de um :class:`EngineRef`."""
        return {
            "engine_id": engine.id,
            "engine_version": engine.version,
            "model_id": engine.model_id,
            "model_revision": engine.model_revision,
            "engine_provider": engine.provider,
        }
