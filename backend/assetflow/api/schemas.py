"""DTOs da API pública de geração (planos §51 a §54).

O que o frontend vê nunca menciona tecnologia de IA. Ele vê capacidade,
profile, job, progresso e asset. Se o motor por trás mudar, estes contratos
permanecem idênticos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from ..generation.schemas import (
    AssetFlowModel,
    Capability,
    EngineRef,
    GeneratedAsset,
    Job,
    JobErrorInfo,
    JobEvent,
    JobStatus,
    StageTimings,
)

__all__ = [
    "JobSubmissionResponse",
    "JobResponse",
    "JobListResponse",
    "EngineSummary",
    "EngineListResponse",
    "CapabilityResponse",
    "ProfileSummary",
    "ErrorResponse",
    "HealthResponse",
]


class JobSubmissionResponse(AssetFlowModel):
    """Resposta imediata do POST de job (plano §53)."""

    job_id: str
    status: JobStatus
    project_id: str
    capability: Capability
    profile: str | None = None
    pipeline: str
    queue: str
    created_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobSubmissionResponse":
        return cls(
            job_id=job.id,
            status=job.status,
            project_id=job.project_id,
            capability=job.capability,
            profile=job.profile_id,
            pipeline=job.pipeline_id,
            queue=job.queue,
            created_at=job.created_at,
        )


class JobResponse(AssetFlowModel):
    """Estado de um job (plano §54)."""

    job_id: str
    status: JobStatus
    progress: float
    stage: str = ""
    project_id: str
    capability: Capability
    profile: str | None = None
    pipeline: str

    engine: EngineRef | None = None
    fallback_used: bool = False

    asset: GeneratedAsset | None = None
    error: JobErrorInfo | None = None
    timings: StageTimings = Field(default_factory=StageTimings)
    warnings: tuple[str, ...] = ()
    attempts: int = 0

    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    events: tuple[JobEvent, ...] = ()

    @classmethod
    def from_job(cls, job: Job, *, include_events: bool = False) -> "JobResponse":
        return cls(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            project_id=job.project_id,
            capability=job.capability,
            profile=job.profile_id,
            pipeline=job.pipeline_id,
            engine=job.engine,
            fallback_used=job.fallback_used,
            asset=job.asset,
            error=job.error,
            timings=job.timings,
            warnings=job.warnings,
            attempts=job.attempts,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            events=job.events if include_events else (),
        )


class JobListResponse(AssetFlowModel):
    items: tuple[JobResponse, ...] = ()
    total: int = 0


class EngineSummary(AssetFlowModel):
    """Visão de uma gaveta para a API."""

    id: str
    name: str
    version: str
    engine_api_version: str
    provider: str
    description: str = ""
    state: str
    enabled: bool
    api_compatible: bool
    capabilities: tuple[str, ...] = ()
    supports: dict[str, bool] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] | None = None
    last_error: str | None = None
    source: str | None = None


class EngineListResponse(AssetFlowModel):
    items: tuple[EngineSummary, ...] = ()
    engine_api_version: str


class CapabilityResponse(AssetFlowModel):
    capability: str
    family: str
    variant: str
    description: str
    mode: str | None = None
    experimental: bool = False
    available: bool = False
    engines: tuple[str, ...] = ()
    preferred_order: tuple[str, ...] = ()


class ProfileSummary(AssetFlowModel):
    id: str
    display_name: str
    capability: str
    pipeline: str
    asset_type: str
    mode: str
    logical_size: tuple[int, int] | None = None
    render_size: tuple[int, int]
    variations: int
    palette_size: int | None = None


class ErrorResponse(AssetFlowModel):
    """Erro normalizado exposto ao cliente."""

    code: str
    message: str
    retryable: bool = False
    engine_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(AssetFlowModel):
    status: str
    version: str
    engines: dict[str, str] = Field(default_factory=dict)
    queued_jobs: int = 0
