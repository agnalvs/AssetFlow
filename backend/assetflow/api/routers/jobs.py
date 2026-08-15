"""Endpoints de jobs de geração (planos §51 a §55).

O POST **não** espera a geração terminar: cria o job, devolve ``queued`` e o
cliente acompanha por polling. A arquitetura já está pronta para publicar os
mesmos eventos por WebSocket/SSE quando isso for priorizado (plano §55) — o
log de eventos do job existe exatamente para isso.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from ...generation.schemas import AssetGenerationRequest, JobStatus
from ..deps import ServiceDep
from ..schemas import JobListResponse, JobResponse, JobSubmissionResponse

router = APIRouter(prefix="/api/generation/jobs", tags=["jobs"])


@router.post(
    "",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cria um job de geração",
)
async def create_job(
    request: AssetGenerationRequest, service: ServiceDep
) -> JobSubmissionResponse:
    job = await service.submit(request)
    return JobSubmissionResponse.from_job(job)


@router.get("", response_model=JobListResponse, summary="Lista jobs")
async def list_jobs(
    service: ServiceDep,
    project_id: str | None = Query(default=None),
    job_status: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListResponse:
    jobs = await service.list_jobs(
        project_id=project_id, status=job_status, limit=limit, offset=offset
    )
    return JobListResponse(
        items=tuple(JobResponse.from_job(job) for job in jobs), total=len(jobs)
    )


@router.get("/{job_id}", response_model=JobResponse, summary="Consulta um job")
async def get_job(
    job_id: str,
    service: ServiceDep,
    include_events: bool = Query(default=False, description="Inclui o log de eventos."),
) -> JobResponse:
    job = await service.get_job(job_id)
    return JobResponse.from_job(job, include_events=include_events)


@router.post(
    "/{job_id}/cancel", response_model=JobResponse, summary="Cancela um job"
)
async def cancel_job(job_id: str, service: ServiceDep) -> JobResponse:
    job = await service.cancel_job(job_id)
    return JobResponse.from_job(job)
