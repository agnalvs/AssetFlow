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

    # -- Benchmark de Pixel Art (plano Pixel §93 e §94) ------------------
    # Guardados no histórico porque é com eles que se compara motor A × motor
    # B: não pela imagem bonita, mas pela quantidade de correção que a saída
    # exigiu para virar um asset tecnicamente válido.
    pixel_exact: bool | None = None
    quality_score: int | None = None
    status: str | None = None
    preview_uri: str | None = None


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

    # -- Rastreabilidade do produtor (plano §42) ------------------------
    #
    # `engine_id` é opcional só para um registro montado fora do Kernel — em
    # geração normal ele vem sempre preenchido, porque existe um caminho e ele
    # começa em um motor (plano Optimizer §25).
    #
    # O que o Pixel Optimizer fez com o asset não tem campo próprio aqui: ele
    # viaja em `metadata["pixel"]`, junto das demais métricas do módulo Pixel,
    # porque é medida de resultado e não identidade de produtor.
    engine_id: str | None = None
    engine_version: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    engine_provider: str | None = None
    #: Versão do adapter e LoRA aplicada (plano de motores §18). Sem estes dois, duas
    #: gerações do mesmo modelo podem ser diferentes sem que o histórico
    #: consiga dizer por quê.
    adapter_version: str | None = None
    lora_id: str | None = None
    fallback_used: bool = False
    attempted_engines: tuple[str, ...] = ()

    #: O motor **pedido**, e como ele foi pedido (plano de motores §25, regra 3). Quando
    #: difere de ``engine_id``, houve fallback — e é essa diferença que o
    #: benchmark procura.
    requested_engine_id: str | None = None
    engine_selection_mode: str = "auto"

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
    def engine_fields(cls, engine: EngineRef | None) -> dict[str, Any]:
        """Extrai os campos de rastreabilidade de um :class:`EngineRef`."""
        if engine is None:
            return {}
        return {
            "engine_id": engine.id,
            "engine_version": engine.version,
            "model_id": engine.model_id,
            "model_revision": engine.model_revision,
            "engine_provider": engine.provider,
            "adapter_version": engine.adapter_version,
            "lora_id": engine.lora_id,
        }

