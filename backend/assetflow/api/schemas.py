"""DTOs da API pública de geração (planos §51 a §54).

O que o frontend vê nunca menciona tecnologia de IA. Ele vê capacidade,
profile, job, progresso e asset. Se o motor por trás mudar, estes contratos
permanecem idênticos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from pydantic import Field

from ..generation.prompting import render_semantic_prompt
from ..generation.schemas import (
    AssetFlowModel,
    AssetMode,
    AssetType,
    Capability,
    EngineRef,
    GeneratedAsset,
    Job,
    JobErrorInfo,
    JobEvent,
    JobStatus,
    PromptPreview,
    StageTimings,
    ValidationReport,
)

#: Converte a URI interna de um asset em caminho HTTP servível.
UrlResolver = Callable[[str], "str | None"]

__all__ = [
    "AssetVariantView",
    "AssetView",
    "JobSubmissionResponse",
    "JobResponse",
    "PromptPreview",
    "JobListResponse",
    "EngineSummary",
    "EngineListResponse",
    "CapabilityResponse",
    "ProfileSummary",
    "ErrorResponse",
    "HealthResponse",
]


class AssetVariantView(AssetFlowModel):
    """Uma variação, já com URL pronta para o ``<img src>``.

    A URI interna (``assetflow-local://...``) continua exposta para
    rastreabilidade, mas o cliente não precisa saber resolvê-la — nem
    depender do backend de storage em uso.
    """

    id: str
    index: int
    uri: str
    url: str | None = None
    thumbnail_uri: str | None = None
    thumbnail_url: str | None = None
    width: int
    height: int
    logical_width: int | None = None
    logical_height: int | None = None
    seed: int | None = None
    color_count: int | None = None
    palette: tuple[str, ...] = ()
    validation: ValidationReport = Field(default_factory=ValidationReport)

    # -- Selo Pixel Exact (plano Pixel §79) ------------------------------
    # É com estes campos que a interface consegue afirmar "64 × 64, 16 cores,
    # PIXEL EXACT ✓" em vez de perguntar se a imagem parece Pixel Art.
    # `None` em arte 2D convencional, onde a pergunta não faz sentido.
    pixel_exact: bool | None = None
    quality_score: int | None = None
    status: str | None = None
    preview_uri: str | None = None
    preview_url: str | None = None
    #: Arquivos auxiliares já resolvidos para URL (plano Pixel §70).
    artifacts: dict[str, str] = Field(default_factory=dict)


class AssetView(AssetFlowModel):
    """Asset como o cliente enxerga."""

    id: str
    project_id: str
    job_id: str
    type: AssetType
    mode: AssetMode
    name: str = ""
    profile_id: str | None = None
    pipeline_id: str | None = None
    engine: EngineRef
    variants: tuple[AssetVariantView, ...] = ()
    created_at: datetime

    @classmethod
    def from_asset(
        cls, asset: GeneratedAsset, url_for: UrlResolver | None = None
    ) -> "AssetView":
        resolve: UrlResolver = url_for or (lambda _uri: None)
        return cls(
            id=asset.id,
            project_id=asset.project_id,
            job_id=asset.job_id,
            type=asset.type,
            mode=asset.mode,
            name=asset.name,
            profile_id=asset.profile_id,
            pipeline_id=asset.pipeline_id,
            engine=asset.engine,
            created_at=asset.created_at,
            variants=tuple(
                AssetVariantView(
                    id=variant.id,
                    index=variant.index,
                    uri=variant.uri,
                    url=resolve(variant.uri),
                    thumbnail_uri=variant.thumbnail_uri,
                    thumbnail_url=(
                        resolve(variant.thumbnail_uri) if variant.thumbnail_uri else None
                    ),
                    width=variant.width,
                    height=variant.height,
                    logical_width=variant.logical_width,
                    logical_height=variant.logical_height,
                    seed=variant.seed,
                    color_count=variant.color_count,
                    palette=variant.palette,
                    validation=variant.validation,
                    pixel_exact=variant.pixel_exact,
                    quality_score=variant.quality_score,
                    status=variant.status,
                    preview_uri=variant.preview_uri,
                    preview_url=(
                        resolve(variant.preview_uri) if variant.preview_uri else None
                    ),
                    artifacts={
                        name: resolve(uri) or uri
                        for name, uri in sorted(variant.artifacts.items())
                    },
                )
                for variant in asset.variants
            ),
        )


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

    asset: AssetView | None = None
    #: A leitura que o AssetFlow fez do pedido — o mesmo objeto devolvido por
    #: `POST /api/generation/prompt/preview`, para que a tela possa comparar
    #: o que pré-visualizou com o que foi de fato gerado.
    prompt: PromptPreview | None = None
    error: JobErrorInfo | None = None
    timings: StageTimings = Field(default_factory=StageTimings)
    warnings: tuple[str, ...] = ()
    attempts: int = 0

    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    events: tuple[JobEvent, ...] = ()

    @classmethod
    def from_job(
        cls,
        job: Job,
        *,
        include_events: bool = False,
        url_for: UrlResolver | None = None,
    ) -> "JobResponse":
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
            asset=AssetView.from_asset(job.asset, url_for) if job.asset else None,
            prompt=_prompt_view(job),
            error=job.error,
            timings=job.timings,
            warnings=job.warnings,
            attempts=job.attempts,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            events=job.events if include_events else (),
        )


def _prompt_view(job: Job) -> PromptPreview | None:
    """A semântica do job no formato da pré-visualização, ou nada.

    ``None`` enquanto o job não chegou ao fim: a semântica é resolvida no
    início do pipeline e só sobe para o job quando ele completa. Inventar uma
    aqui — reexecutando o builder na hora de responder — daria uma resposta
    plausível e possivelmente diferente da que gerou o asset.

    ``positive``/``negative`` são a renderização neutra do AssetFlow. Um motor
    com adapter próprio recebe outro texto (plano §27), e é justamente por
    isso que o campo que manda é o ``semantic``: ele é o mesmo para todos.
    """
    semantic = job.semantic_prompt
    if semantic is None:
        return None
    positive, negative = render_semantic_prompt(semantic)
    return PromptPreview(
        profile=job.profile_id or "",
        capability=str(job.capability),
        semantic=semantic,
        positive=positive,
        negative=negative,
        source="request" if job.request.semantic_prompt is not None else "builder",
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
