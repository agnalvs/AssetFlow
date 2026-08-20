"""Job Manager — dono do ciclo de vida de um job (planos §32, §45, §46, §53).

Fluxo:

    submit -> QUEUED -> RUNNING -> GENERATING -> POSTPROCESSING -> COMPLETED
                              \\-> CANCEL_REQUESTED -> CANCELLED
                              \\-> FAILED (com retry opcional)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..generation.kernel.contracts import CancellationToken, ProgressReporter
from ..generation.kernel.exceptions import GenerationError, JobNotFound
from ..generation.schemas import (
    GeneratedAsset,
    Job,
    JobErrorInfo,
    JobEvent,
    JobStatus,
    SemanticPrompt,
    StageTimings,
    utcnow,
)
from .queue import DEFAULT_QUEUE, JobQueue, QueueRouter
from .retry import RetryPolicy
from .store import JobStore

__all__ = ["JobManager"]

_LOG = logging.getLogger("assetflow.jobs.manager")

#: Limite do log de eventos por job, para não crescer indefinidamente.
_MAX_EVENTS = 200


class JobManager:
    """Coordena store, fila, cancelamento e retry."""

    def __init__(
        self,
        store: JobStore,
        queue: JobQueue,
        *,
        router: QueueRouter | None = None,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._store = store
        self._queue = queue
        self._router = router or QueueRouter()
        self._retry = retry_policy or RetryPolicy()
        self._tokens: dict[str, CancellationToken] = {}

    @property
    def store(self) -> JobStore:
        return self._store

    @property
    def queue(self) -> JobQueue:
        return self._queue

    @property
    def router(self) -> QueueRouter:
        return self._router

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry

    # ------------------------------------------------------------------
    # Submissão
    # ------------------------------------------------------------------
    async def submit(self, job: Job) -> Job:
        """Cria o job e o enfileira. Retorna imediatamente (plano §53)."""
        job.queue = job.queue or self._router.route(job.capability)
        job.status = JobStatus.QUEUED
        job.queued_at = utcnow()
        self._append_event(job, JobStatus.QUEUED, "job enfileirado")

        await self._store.create(job)
        await self._queue.enqueue(job.id, queue=job.queue, priority=job.priority)
        _LOG.info(
            "job %s enfileirado (capability=%s, pipeline=%s, fila=%s)",
            job.id,
            job.capability,
            job.pipeline_id,
            job.queue,
        )
        return job

    async def get(self, job_id: str) -> Job:
        return await self._store.get(job_id)

    async def list(self, **kwargs: Any) -> list[Job]:
        return await self._store.list(**kwargs)

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def start(self, job_id: str) -> Job | None:
        """Marca o início de uma tentativa.

        Devolve ``None`` se o job já foi cancelado enquanto esperava na fila
        — o worker então simplesmente descarta o item.
        """
        job = await self._store.find(job_id)
        if job is None:
            raise JobNotFound(f"job '{job_id}' não encontrado")

        if job.status in {JobStatus.CANCELLED, JobStatus.CANCEL_REQUESTED}:
            await self.mark_cancelled(job_id, "cancelado antes de iniciar")
            return None
        if job.status.is_terminal:
            return None

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = job.started_at or utcnow()
        job.progress = 0.0
        job.stage = "starting"
        self._append_event(job, JobStatus.RUNNING, f"tentativa {job.attempts}")
        self._tokens[job_id] = CancellationToken()
        await self._store.update(job)
        return job

    def cancellation_token(self, job_id: str) -> CancellationToken:
        """Token cooperativo da tentativa atual."""
        return self._tokens.setdefault(job_id, CancellationToken())

    def progress_reporter(self, job_id: str) -> ProgressReporter:
        """Callback síncrono para o kernel/pipeline reportarem progresso.

        A atualização é feita na instância viva do job (ver
        :class:`~assetflow.jobs.store.InMemoryJobStore`). Com um store
        remoto, esta é a função a ser trocada por um envio assíncrono.
        """

        def report(progress: float, stage: str = "", **extra: Any) -> None:
            job = self._peek(job_id)
            if job is None or job.status.is_terminal:
                return
            job.progress = max(0.0, min(1.0, float(progress)))
            if stage:
                job.stage = stage
                if stage == "generating" and job.status is JobStatus.RUNNING:
                    job.status = JobStatus.GENERATING
                elif stage.startswith("postprocess") and job.status in {
                    JobStatus.RUNNING,
                    JobStatus.GENERATING,
                }:
                    job.status = JobStatus.POSTPROCESSING
            if extra.get("engine_id") and job.engine is None:
                job.metadata.setdefault("engine_id", extra["engine_id"])

        return report

    def _peek(self, job_id: str) -> Job | None:
        """Acesso síncrono ao job vivo (apenas para progresso)."""
        return self._store.peek(job_id)

    # ------------------------------------------------------------------
    # Conclusão
    # ------------------------------------------------------------------
    async def complete(
        self,
        job_id: str,
        *,
        asset: GeneratedAsset | None,
        timings: StageTimings | None = None,
        engine=None,
        fallback_used: bool = False,
        warnings: tuple[str, ...] = (),
        semantic_prompt: SemanticPrompt | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Job:
        job = await self._store.get(job_id)
        job.status = JobStatus.COMPLETED
        job.progress = 1.0
        job.stage = "completed"
        job.finished_at = utcnow()
        job.asset = asset
        job.semantic_prompt = semantic_prompt or job.semantic_prompt
        job.engine = engine or job.engine
        job.fallback_used = fallback_used
        job.warnings = tuple(dict.fromkeys((*job.warnings, *warnings)))
        if timings is not None:
            job.timings = timings
        if metadata:
            job.metadata.update(metadata)
        self._append_event(job, JobStatus.COMPLETED, "geração concluída", progress=1.0)
        self._tokens.pop(job_id, None)
        return await self._store.update(job)

    async def fail(self, job_id: str, error: GenerationError) -> Job:
        job = await self._store.get(job_id)
        job.status = JobStatus.FAILED
        job.finished_at = utcnow()
        job.stage = "failed"
        job.error = JobErrorInfo(
            code=error.code.value,
            message=error.message,
            retryable=error.retryable,
            engine_id=error.engine_id,
            detail=error.detail,
        )
        self._append_event(job, JobStatus.FAILED, error.message)
        self._tokens.pop(job_id, None)
        _LOG.error("job %s falhou: %s", job_id, error)
        return await self._store.update(job)

    async def request_cancel(self, job_id: str) -> Job:
        """Pedido de cancelamento vindo do usuário (plano §46)."""
        job = await self._store.get(job_id)
        if job.status.is_terminal:
            return job

        if job.status is JobStatus.QUEUED:
            # Ainda não começou: cancelamento é imediato.
            job.status = JobStatus.CANCELLED
            job.finished_at = utcnow()
            job.stage = "cancelled"
            self._append_event(job, JobStatus.CANCELLED, "cancelado antes de iniciar")
            return await self._store.update(job)

        job.status = JobStatus.CANCEL_REQUESTED
        self._append_event(job, JobStatus.CANCEL_REQUESTED, "cancelamento solicitado")
        token = self._tokens.get(job_id)
        if token is not None:
            token.cancel("cancelamento solicitado pelo usuário")
        return await self._store.update(job)

    async def mark_cancelled(self, job_id: str, message: str = "cancelado") -> Job:
        job = await self._store.get(job_id)
        job.status = JobStatus.CANCELLED
        job.finished_at = utcnow()
        job.stage = "cancelled"
        self._append_event(job, JobStatus.CANCELLED, message)
        self._tokens.pop(job_id, None)
        return await self._store.update(job)

    # ------------------------------------------------------------------
    # Retry
    # ------------------------------------------------------------------
    async def requeue(self, job_id: str, *, delay_s: float, reason: str) -> Job:
        """Reenfileira o job depois de uma falha transitória."""
        job = await self._store.get(job_id)
        job.status = JobStatus.QUEUED
        job.progress = 0.0
        job.stage = "requeued"
        job.queued_at = utcnow()
        self._append_event(job, JobStatus.QUEUED, f"retry: {reason}")
        self._tokens.pop(job_id, None)
        await self._store.update(job)

        if delay_s > 0:
            await asyncio.sleep(delay_s)
        await self._queue.enqueue(
            job.id, queue=job.queue or DEFAULT_QUEUE, priority=job.priority
        )
        return job

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _append_event(
        self,
        job: Job,
        status: JobStatus,
        message: str,
        *,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        event = JobEvent(
            status=status,
            message=message,
            progress=progress if progress is not None else job.progress,
            data=data or {},
        )
        events = (*job.events, event)
        job.events = events[-_MAX_EVENTS:]
