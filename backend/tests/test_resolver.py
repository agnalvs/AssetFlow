"""Testes do EngineResolver: prioridade, seleção manual e fallback."""

from __future__ import annotations

import pytest

from assetflow.generation.kernel import (
    EngineDisabled,
    EngineNotFound,
    EngineRegistry,
    EngineResolver,
    NoEngineAvailable,
    RoutingPolicy,
    discover_manifests,
)
from assetflow.generation.schemas import (
    Capability,
    EngineRuntimeConfig,
    EngineSelector,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
    ReferenceImage,
)

from tests.conftest import BACKEND_ROOT, run

ENGINES_ROOT = BACKEND_ROOT / "assetflow" / "generation" / "engines"
PIXEL = Capability.parse("text_to_image.pixel")


def _registry(*enabled: str) -> EngineRegistry:
    registry = EngineRegistry()
    for entry in discover_manifests([ENGINES_ROOT]):
        registry.register_discovered(
            entry,
            EngineRuntimeConfig(
                engine_id=entry.manifest.id, enabled=entry.manifest.id in enabled
            ),
        )
    return registry


def _policy(**overrides) -> RoutingPolicy:
    base = {
        "routing": {PIXEL: ("mock-pixel-alt-v1", "mock-image-v1")},
        "fallback_enabled": True,
        "max_engine_attempts": 3,
    }
    base.update(overrides)
    return RoutingPolicy(**base)


def _request(**overrides) -> ImageGenerationRequest:
    payload = {
        "capability": PIXEL,
        "prompt": PromptSpec(positive="a knight"),
        "output": OutputSpec(width=256, height=256, variations=1),
    }
    payload.update(overrides)
    return ImageGenerationRequest(**payload)


def test_priority_order_comes_from_configuration():
    resolver = EngineResolver(_registry("mock-image-v1", "mock-pixel-alt-v1"), _policy())
    resolution = run(resolver.resolve(PIXEL))
    assert resolution.engine_ids[0] == "mock-pixel-alt-v1"
    assert "mock-image-v1" in resolution.engine_ids


def test_changing_only_configuration_changes_the_engine():
    """Trocar o motor de produção é reordenar a lista — plano §13."""
    registry = _registry("mock-image-v1", "mock-pixel-alt-v1")

    resolver = EngineResolver(
        registry, _policy(routing={PIXEL: ("mock-image-v1", "mock-pixel-alt-v1")})
    )
    assert run(resolver.resolve(PIXEL)).primary.engine_id == "mock-image-v1"

    resolver.set_policy(_policy(routing={PIXEL: ("mock-pixel-alt-v1", "mock-image-v1")}))
    assert run(resolver.resolve(PIXEL)).primary.engine_id == "mock-pixel-alt-v1"


def test_disabled_engine_is_skipped_and_reported():
    resolver = EngineResolver(_registry("mock-image-v1"), _policy())
    resolution = run(resolver.resolve(PIXEL))
    assert resolution.primary.engine_id == "mock-image-v1"
    assert dict(resolution.rejected)["mock-pixel-alt-v1"] == "desabilitado"


def test_no_engine_available_raises_normalized_error():
    resolver = EngineResolver(_registry(), _policy())
    with pytest.raises(NoEngineAvailable):
        run(resolver.resolve(PIXEL))


def test_manual_selection_is_respected():
    resolver = EngineResolver(_registry("mock-image-v1", "mock-pixel-alt-v1"), _policy())
    selector = EngineSelector(mode="manual", engine_id="mock-image-v1")
    resolution = run(resolver.resolve(PIXEL, selector=selector))
    assert resolution.primary.engine_id == "mock-image-v1"
    assert resolution.requested_engine_id == "mock-image-v1"


def test_manual_selection_without_fallback_returns_single_candidate():
    resolver = EngineResolver(_registry("mock-image-v1", "mock-pixel-alt-v1"), _policy())
    selector = EngineSelector(
        mode="manual", engine_id="mock-image-v1", allow_fallback=False
    )
    resolution = run(resolver.resolve(PIXEL, selector=selector))
    assert resolution.chain() == resolution.candidates[:1]


def test_manual_selection_of_unknown_or_disabled_engine():
    resolver = EngineResolver(_registry("mock-image-v1"), _policy())

    with pytest.raises(EngineNotFound):
        run(resolver.resolve(PIXEL, selector=EngineSelector(mode="manual", engine_id="x")))

    with pytest.raises(EngineDisabled):
        run(
            resolver.resolve(
                PIXEL, selector=EngineSelector(mode="manual", engine_id="mock-pixel-alt-v1")
            )
        )


def test_engine_limits_are_enforced_from_the_manifest():
    """O resolver descarta quem não cabe no pedido — sem `if engine_id ==`."""
    resolver = EngineResolver(_registry("mock-image-v1", "mock-pixel-alt-v1"), _policy())

    # mock-pixel-alt-v1 declara max_width=1024; mock-image-v1 declara 2048.
    resolution = run(
        resolver.resolve(
            PIXEL, request=_request(output=OutputSpec(width=2048, height=2048))
        )
    )
    assert resolution.engine_ids == ("mock-image-v1",)
    assert "mock-pixel-alt-v1" in dict(resolution.rejected)


def test_unsupported_feature_removes_candidate():
    """Nenhuma gaveta atual suporta imagem de referência (plano §30)."""
    resolver = EngineResolver(_registry("mock-image-v1", "mock-pixel-alt-v1"), _policy())
    request = _request(reference_images=(ReferenceImage(uri="assetflow-local://x.png"),))
    with pytest.raises(NoEngineAvailable):
        run(resolver.resolve(PIXEL, request=request))


def test_unlisted_engine_still_resolvable_when_allowed():
    """Uma gaveta nova funciona antes mesmo de entrar em capabilities.yaml."""
    registry = _registry("mock-image-v1")
    resolver = EngineResolver(registry, RoutingPolicy(routing={}, allow_unlisted_engines=True))
    resolution = run(resolver.resolve(PIXEL))
    assert resolution.primary.engine_id == "mock-image-v1"
