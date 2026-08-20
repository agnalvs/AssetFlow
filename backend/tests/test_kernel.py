"""Testes do Generation Kernel: normalização, fallback, lotes e cancelamento."""

from __future__ import annotations

import pytest

from assetflow.generation.kernel.exceptions import EngineTimeoutError
from assetflow.generation.kernel import (
    CancellationToken,
    EngineRegistry,
    EngineResolver,
    GenerationCancelled,
    GenerationKernel,
    NoEngineAvailable,
    RoutingPolicy,
    discover_manifests,
)
from assetflow.generation.schemas import (
    Capability,
    EngineRuntimeConfig,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)

from tests.conftest import BACKEND_ROOT, run

ENGINES_ROOT = BACKEND_ROOT / "assetflow" / "generation" / "engines"
PIXEL = Capability.parse("text_to_image.pixel")


def _kernel(*enabled: str) -> GenerationKernel:
    registry = EngineRegistry()
    for entry in discover_manifests([ENGINES_ROOT]):
        registry.register_discovered(
            entry,
            EngineRuntimeConfig(
                engine_id=entry.manifest.id, enabled=entry.manifest.id in enabled
            ),
        )
    policy = RoutingPolicy(
        routing={PIXEL: ("mock-image-v1", "mock-pixel-alt-v1")},
        fallback_enabled=True,
        max_engine_attempts=3,
    )
    return GenerationKernel(registry, EngineResolver(registry, policy))


def _request(**overrides) -> ImageGenerationRequest:
    payload = {
        "capability": PIXEL,
        "prompt": PromptSpec(positive="a knight"),
        "output": OutputSpec(width=128, height=128, variations=1),
        "generation": {"seed": 99},
    }
    payload.update(overrides)
    return ImageGenerationRequest(**payload)


def test_result_shape_is_identical_across_engines():
    """O frontend nunca precisa interpretar respostas diferentes (§21)."""
    results = []
    for engine_id in ("mock-image-v1", "mock-pixel-alt-v1"):
        kernel = _kernel(engine_id)
        results.append(run(kernel.execute(_request(), job_id=f"job_{engine_id}")))

    first, second = results
    assert first.model_fields_set >= {"outputs", "engine", "capability", "timings"}
    assert set(first.model_dump()) == set(second.model_dump())
    assert first.engine.id != second.engine.id
    assert len(first.outputs) == len(second.outputs) == 1
    for result in results:
        output = result.outputs[0]
        assert output.width == 128 and output.height == 128
        assert output.data and output.seed is not None


def test_fallback_when_preferred_engine_fails():
    """Plano §44: o motor preferido falha e a geração continua."""
    kernel = _kernel("mock-image-v1", "mock-pixel-alt-v1")
    request = _request(engine_options={"mock-image-v1": {"fail_always": True}})

    result = run(kernel.execute(request, job_id="job_fallback"))

    assert result.engine.id == "mock-pixel-alt-v1"
    assert result.fallback_used is True
    assert result.attempted_engines == ("mock-image-v1", "mock-pixel-alt-v1")
    assert any("fallback" in warning for warning in result.warnings)


def _make_it_time_out(kernel: GenerationKernel, engine_id: str) -> None:
    """Deixa o deadline da gaveta menor que a latência que ela vai simular."""
    record = kernel.registry.find(engine_id)
    assert record is not None
    record.handle.config.timeout_s = 0.05


def test_timeout_in_one_engine_still_falls_back():
    """Plano §44: estourar o tempo é uma falha como outra qualquer.

    Regressão de um bug real: ao expirar o deadline, o Kernel cancelava
    ``execution.cancellation`` para interromper a inferência. Só que aquele é o
    token do **job**, consultado pelo laço de fallback antes de cada candidato
    — então o fallback anunciado no log (``tentando fallback``) morria na linha
    seguinte, e o job terminava como `cancelled`, sem asset e sem erro
    registrado. Quem para a inferência é o `cancel()` da própria gaveta.
    """
    kernel = _kernel("mock-image-v1", "mock-pixel-alt-v1")
    _make_it_time_out(kernel, "mock-image-v1")
    request = _request(engine_options={"mock-image-v1": {"simulated_latency_ms": 3000}})

    result = run(kernel.execute(request, job_id="job_timeout_fallback"))

    assert result.engine.id == "mock-pixel-alt-v1"
    assert result.fallback_used is True
    assert result.attempted_engines == ("mock-image-v1", "mock-pixel-alt-v1")


def test_timeout_leaves_the_job_token_untouched():
    """O invariante por trás do teste acima, verificado direto no token.

    Sem alternativa na cadeia, o erro certo é ``engine_timeout`` — nunca
    ``GenerationCancelled``. E o token do job precisa continuar limpo: ele
    significa "alguém pediu para parar", e ninguém pediu.
    """
    kernel = _kernel("mock-image-v1")
    _make_it_time_out(kernel, "mock-image-v1")
    request = _request(engine_options={"mock-image-v1": {"simulated_latency_ms": 3000}})
    token = CancellationToken()

    with pytest.raises(EngineTimeoutError) as excinfo:
        run(kernel.execute(request, job_id="job_timeout_solo", cancellation=token))

    assert excinfo.value.engine_id == "mock-image-v1"
    assert token.is_cancelled is False


def test_all_engines_failing_raises_normalized_error():
    kernel = _kernel("mock-image-v1")
    request = _request(engine_options={"mock-image-v1": {"fail_always": True}})
    with pytest.raises(Exception) as excinfo:
        run(kernel.execute(request, job_id="job_dead"))
    assert "mock-image-v1" in str(excinfo.value)


def test_capability_without_any_engine():
    kernel = _kernel("mock-image-v1")
    with pytest.raises(NoEngineAvailable):
        run(
            kernel.execute(
                _request(capability=Capability.parse("inpainting.general")),
                job_id="job_none",
            )
        )


def test_batching_respects_engine_limits():
    """mock-pixel-alt-v1 declara max_variations=4; pedimos 6."""
    kernel = _kernel("mock-pixel-alt-v1")
    result = run(
        kernel.execute(
            _request(output=OutputSpec(width=128, height=128, variations=6)),
            job_id="job_batch",
        )
    )
    assert len(result.outputs) == 6
    assert [output.index for output in result.outputs] == [0, 1, 2, 3, 4, 5]
    assert len({output.seed for output in result.outputs}) == 6


def test_progress_and_cancellation_are_wired():
    kernel = _kernel("mock-image-v1")
    seen: list[tuple[float, str]] = []

    def progress(value: float, stage: str = "", **_extra) -> None:
        seen.append((value, stage))

    result = run(
        kernel.execute(
            _request(output=OutputSpec(width=64, height=64, variations=2)),
            job_id="job_progress",
            progress=progress,
        )
    )
    assert result.outputs
    assert any(stage == "generating" for _value, stage in seen)


def test_cancellation_before_dispatch():
    kernel = _kernel("mock-image-v1")
    token = CancellationToken()
    token.cancel("usuário desistiu")
    with pytest.raises(GenerationCancelled):
        run(kernel.execute(_request(), job_id="job_cancel", cancellation=token))


def test_engine_metadata_is_recorded_for_observability():
    kernel = _kernel("mock-image-v1")
    result = run(kernel.execute(_request(), job_id="job_meta"))

    assert result.metadata["resolution_chain"]
    assert result.metadata["engine_metadata"]["device"] == "cpu"
    assert result.timings.inference_ms is not None
    assert result.timings.total_ms is not None
    # Rastreabilidade completa do motor (plano §42).
    assert result.engine.model_id
    assert result.engine.version
