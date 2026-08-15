"""Testes do Job System: fila, estados, retry, cancelamento e filas por capacidade."""

from __future__ import annotations

import asyncio

import pytest

from assetflow.bootstrap import AppContainer
from assetflow.generation.kernel.exceptions import (
    EngineOutOfMemoryError,
    InvalidGenerationRequest,
    JobNotFound,
)
from assetflow.generation.schemas import AssetGenerationRequest, AssetOutputOverrides, JobStatus
from assetflow.jobs import QueueRouter, RetryPolicy

from tests.conftest import process_next_job, run


def test_submit_returns_immediately_with_queued_status(
    container: AppContainer, make_request
):
    """Plano §53: a resposta não espera a geração."""
    job = run(container.service.submit(make_request()))
    assert job.status is JobStatus.QUEUED
    assert job.queued_at is not None
    assert job.asset is None
    assert run(container.job_queue.size(job.queue)) == 1


def test_full_job_lifecycle(container: AppContainer, make_request):
    async def scenario():
        job = await container.service.submit(make_request())
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.COMPLETED
    assert job.progress == 1.0
    assert job.attempts == 1
    assert job.started_at and job.finished_at
    assert job.asset is not None
    assert job.engine is not None
    assert job.timings.total_ms is not None

    statuses = [event.status for event in job.events]
    assert JobStatus.QUEUED in statuses and JobStatus.COMPLETED in statuses


def test_cancel_before_start(container: AppContainer, make_request):
    async def scenario():
        job = await container.service.submit(make_request())
        cancelled = await container.service.cancel_job(job.id)
        assert cancelled.status is JobStatus.CANCELLED

        # O worker consome o item da fila e não executa nada.
        await process_next_job(container, timeout=1.0)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.CANCELLED
    assert job.asset is None


def test_cancel_during_execution(container: AppContainer, make_request):
    """Plano §46: o worker encerra assim que for seguro."""

    async def scenario():
        request = make_request(
            output=AssetOutputOverrides(variations=4),
            engine_options={"mock-image-v1": {"simulated_latency_ms": 120}},
        )
        job = await container.service.submit(request)

        worker = asyncio.create_task(process_next_job(container))
        await asyncio.sleep(0.2)  # deixa a geração começar
        await container.service.cancel_job(job.id)
        await worker
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.CANCELLED
    assert job.asset is None


def test_retry_on_transient_failure_then_gives_up(container: AppContainer, make_request):
    """Erro transitório é repetido até esgotar as tentativas (plano §45)."""
    container.service.disable_engine("mock-pixel-alt-v1")

    async def scenario():
        request = make_request(engine_options={"mock-image-v1": {"fail_always": True}})
        job = await container.service.submit(request)

        # 1ª tentativa falha e reenfileira; 2ª falha e encerra.
        assert await process_next_job(container)
        assert await process_next_job(container)
        return await container.service.get_job(job.id)

    job = run(scenario())
    assert job.status is JobStatus.FAILED
    assert job.attempts == 2
    assert job.error is not None
    assert job.error.retryable is True


def test_deterministic_errors_are_not_retried(container: AppContainer):
    """Pedido inválido não vira retry — repetir não mudaria o resultado."""
    with pytest.raises(InvalidGenerationRequest):
        run(
            container.service.submit(
                AssetGenerationRequest(
                    project_id="p1", profile="pixel_character_64", prompt="   "
                )
            )
        )


def test_retry_policy_reduces_batch_after_oom():
    """Plano §45: attempt 2 usa lote reduzido."""
    policy = RetryPolicy(max_attempts=3, base_delay_s=0)
    error = EngineOutOfMemoryError("sem VRAM", engine_id="x")

    decision = policy.decide(error, attempts=1)
    assert decision.retry is True
    assert decision.unload_engine is True

    request = AssetGenerationRequest(
        project_id="p1",
        profile="pixel_character_64",
        prompt="knight",
        output=AssetOutputOverrides(variations=8),
    )
    adjusted = policy.adjust_request(request, error)
    assert adjusted.output.variations == 4
    assert request.output.variations == 8  # o original não é mutado


def test_unknown_job_raises_normalized_error(container: AppContainer):
    with pytest.raises(JobNotFound):
        run(container.service.get_job("job_inexistente"))


def test_queue_router_supports_capability_queues():
    """Plano §33: filas por capacidade já são suportadas."""
    router = QueueRouter(
        {"text_to_image.pixel": "generation.pixel"}, default="generation.default"
    )
    assert router.route("text_to_image.pixel") == "generation.pixel"
    assert router.route("text_to_image.general") == "generation.default"
    assert router.queues() == ("generation.default", "generation.pixel")


def test_priority_ordering_in_queue(container: AppContainer):
    async def scenario():
        await container.job_queue.enqueue("job_low", priority=0)
        await container.job_queue.enqueue("job_high", priority=10)
        first = await container.job_queue.dequeue(("generation.default",), timeout=0.1)
        second = await container.job_queue.dequeue(("generation.default",), timeout=0.1)
        return first.job_id, second.job_id

    assert run(scenario()) == ("job_high", "job_low")


def test_worker_returns_false_on_empty_queue(container: AppContainer):
    assert run(container.worker.run_once(timeout=0.05)) is False
