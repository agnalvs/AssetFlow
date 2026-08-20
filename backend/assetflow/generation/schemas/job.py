"""Job — a unidade de trabalho assíncrona do AssetFlow (plano §32 e §45-47).

Geração nunca acontece dentro do request HTTP. A API cria um job, devolve
``queued`` imediatamente e o worker executa fora do ciclo web.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from .asset import GeneratedAsset
from .asset_request import AssetGenerationRequest
from .capability import Capability
from .common import AssetFlowModel, StageTimings, new_id, utcnow
from .engine import EngineRef
from .semantic_prompt import SemanticPrompt

__all__ = [
    "JobStatus",
    "JobErrorInfo",
    "JobEvent",
    "Job",
    "TERMINAL_JOB_STATUSES",
]


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    #: Estado informativo: o motor já está produzindo pixels.
    GENERATING = "generating"
    POSTPROCESSING = "postprocessing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in TERMINAL_JOB_STATUSES

    @property
    def is_active(self) -> bool:
        return self in {
            JobStatus.RUNNING,
            JobStatus.GENERATING,
            JobStatus.POSTPROCESSING,
            JobStatus.CANCEL_REQUESTED,
        }


TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
)


class JobErrorInfo(AssetFlowModel):
    """Erro normalizado — o formato é igual para qualquer motor (plano §66)."""

    code: str
    message: str
    retryable: bool = False
    engine_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class JobEvent(AssetFlowModel):
    """Entrada do log de eventos do job (base para WebSocket/SSE — plano §55)."""

    at: datetime = Field(default_factory=utcnow)
    status: JobStatus
    message: str = ""
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)


class Job(AssetFlowModel):
    """Estado completo de um job de geração."""

    id: str = Field(default_factory=lambda: new_id("job"))
    status: JobStatus = JobStatus.QUEUED
    project_id: str
    user_id: str | None = None

    pipeline_id: str
    profile_id: str | None = None
    capability: Capability
    queue: str = "generation.default"
    priority: int = 0

    request: AssetGenerationRequest

    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stage: str = ""

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=2, ge=1)

    created_at: datetime = Field(default_factory=utcnow)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    engine: EngineRef | None = None
    fallback_used: bool = False

    asset: GeneratedAsset | None = None
    #: O que o AssetFlow entendeu do pedido (plano §26 e §28). Guardado no
    #: job, e não só no GenerationRecord, porque a interface precisa dele
    #: enquanto o asset está na tela — sem abrir o histórico.
    semantic_prompt: SemanticPrompt | None = None
    error: JobErrorInfo | None = None
    timings: StageTimings = Field(default_factory=StageTimings)
    warnings: tuple[str, ...] = ()
    events: tuple[JobEvent, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def cancel_requested(self) -> bool:
        return self.status is JobStatus.CANCEL_REQUESTED

    @property
    def can_retry(self) -> bool:
        return self.attempts < self.max_attempts
