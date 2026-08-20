"""GPU Worker — executa jobs fora do processo web (plano §34).

O processo web nunca deve segurar modelos gigantes em memória. Este worker é
projetado para rodar embutido (desenvolvimento) **ou** como processo
separado, consumindo do mesmo broker:

    Browser -> API -> Broker -> GenerationWorker -> Engine

Ele não conhece motor algum: pede um pipeline ao registro e o pipeline pede
uma capacidade ao Kernel.
"""

from __future__ import annotations

import asyncio
import logging

from ..generation.kernel.exceptions import (
    EngineTimeoutError,
    ErrorCode,
    GenerationCancelled,
    GenerationError,
)
from ..generation.kernel.service import GenerationKernel
from ..generation.pipelines import PipelineContext, PipelineRegistry
from ..generation.profiles import ProfileRegistry
from ..generation.prompting import PromptBuilderRegistry
from ..generation.schemas import Job
from ..storage import AssetStorageService
from .manager import JobManager
from .queue import DEFAULT_QUEUE

__all__ = ["GenerationWorker"]

_LOG = logging.getLogger("assetflow.jobs.worker")


class GenerationWorker:
    """Consome jobs das filas e executa o pipeline correspondente."""

    def __init__(
        self,
        *,
        manager: JobManager,
        kernel: GenerationKernel,
        pipelines: PipelineRegistry,
        profiles: ProfileRegistry,
        storage: AssetStorageService,
        prompt_builders: PromptBuilderRegistry | None = None,
        queues: tuple[str, ...] = (DEFAULT_QUEUE,),
        concurrency: int = 1,
        job_timeout_s: float = 900.0,
        poll_timeout_s: float = 0.5,
    ) -> None:
        self._manager = manager
        self._kernel = kernel
        self._pipelines = pipelines
        self._profiles = profiles
        self._storage = storage
        self._prompt_builders = prompt_builders or PromptBuilderRegistry.with_defaults()
        self._queues = queues or (DEFAULT_QUEUE,)
        self._concurrency = max(1, concurrency)
        self._job_timeout_s = job_timeout_s
        self._poll_timeout_s = poll_timeout_s

        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def queues(self) -> tuple[str, ...]:
        return self._queues

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Sobe os consumidores em background."""
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._consume(index), name=f"assetflow-worker-{index}")
            for index in range(self._concurrency)
        ]
        _LOG.info(
            "worker iniciado (filas=%s, concorrência=%s)", self._queues, self._concurrency
        )

    async def stop(self) -> None:
        """Encerra os consumidores; jobs em andamento são cancelados."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        _LOG.info("worker encerrado")

    async def _consume(self, index: int) -> None:
        while self._running:
            try:
                processed = await self.run_once(timeout=self._poll_timeout_s)
                if not processed:
                    await asyncio.sleep(0)
            except asyncio.CancelledError:  # pragma: no cover - shutdown
                raise
            except Exception:  # pragma: no cover - o loop nunca pode morrer
                _LOG.exception("erro inesperado no consumidor %s", index)
                await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def run_once(self, *, timeout: float | None = None) -> bool:
        """Processa no máximo um job. Devolve ``False`` se a fila esvaziou.

        Exposto publicamente porque torna os testes determinísticos: não é
        preciso subir um loop de background para exercitar o sistema inteiro.
        """
        item = await self._manager.queue.dequeue(self._queues, timeout=timeout)
        if item is None:
            return False
        await self._execute(item.job_id)
        return True

    async def _execute(self, job_id: str) -> None:
        job = await self._manager.start(job_id)
        if job is None:
            return

        cancellation = self._manager.cancellation_token(job.id)
        progress = self._manager.progress_reporter(job.id)

        try:
            profile = self._profiles.get(job.profile_id or "")
            pipeline = self._pipelines.get(job.pipeline_id)

            context = PipelineContext(
                job_id=job.id,
                request=job.request,
                profile=profile,
                kernel=self._kernel,
                storage=self._storage,
                prompt_builders=self._prompt_builders,
                cancellation=cancellation,
                progress=progress,
                logger=logging.getLogger(f"assetflow.pipeline.{pipeline.id}"),
            )

            outcome = await asyncio.wait_for(
                pipeline.run(context), timeout=self._job_timeout_s
            )
        except GenerationCancelled as exc:
            await self._manager.mark_cancelled(job.id, exc.message)
            return
        except asyncio.TimeoutError:
            await self._handle_failure(
                job,
                EngineTimeoutError(
                    f"job excedeu o tempo máximo de {self._job_timeout_s:.0f}s",
                    engine_id=job.engine.id if job.engine else None,
                ),
            )
            return
        except GenerationError as exc:
            await self._handle_failure(job, exc)
            return
        except asyncio.CancelledError:  # pragma: no cover - shutdown
            await self._manager.mark_cancelled(job.id, "worker encerrado")
            raise
        except Exception as exc:  # erro não previsto vira erro normalizado
            await self._handle_failure(
                job,
                GenerationError(
                    f"falha inesperada no pipeline: {exc}",
                    code=ErrorCode.INTERNAL,
                    retryable=False,
                    detail={"cause": repr(exc)},
                ),
            )
            return

        if cancellation.is_cancelled:
            await self._manager.mark_cancelled(job.id, "cancelado durante a execução")
            return

        await self._manager.complete(
            job.id,
            asset=outcome.asset,
            timings=outcome.timings,
            engine=outcome.result.engine,
            fallback_used=outcome.result.fallback_used,
            warnings=outcome.warnings,
            semantic_prompt=outcome.semantic,
            metadata={
                "record_id": outcome.record.id if outcome.record else None,
                "attempted_engines": list(outcome.result.attempted_engines),
            },
        )

    async def _handle_failure(self, job: Job, error: GenerationError) -> None:
        """Aplica a política de retry (plano §45)."""
        decision = self._manager.retry_policy.decide(error, job.attempts)

        if decision.unload_engine and error.engine_id:
            record = self._kernel.registry.find(error.engine_id)
            if record is not None:
                _LOG.info("descarregando '%s' após OOM antes do retry", error.engine_id)
                await record.handle.unload()

        if not decision.retry:
            await self._manager.fail(job.id, error)
            return

        adjusted = self._manager.retry_policy.adjust_request(job.request, error)
        if adjusted is not job.request:
            job.request = adjusted
            _LOG.info(
                "job %s: nova tentativa com lote reduzido (%s variações)",
                job.id,
                adjusted.output.variations,
            )

        await self._manager.requeue(job.id, delay_s=decision.delay_s, reason=decision.reason)
