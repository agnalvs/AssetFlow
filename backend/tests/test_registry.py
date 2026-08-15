"""Testes do EngineRegistry (plano §11) e da descoberta por manifesto."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assetflow.generation.kernel import (
    EngineIncompatible,
    EngineNotFound,
    EngineRegistry,
    discover_manifests,
    load_engine_class,
)
from assetflow.generation.kernel.discovery import build_factory
from assetflow.generation.schemas import EngineManifest, EngineRuntimeConfig, EngineState

from tests.conftest import BACKEND_ROOT, run

ENGINES_ROOT = BACKEND_ROOT / "assetflow" / "generation" / "engines"


def _manifest(engine_id: str) -> EngineManifest:
    for entry in discover_manifests([ENGINES_ROOT]):
        if entry.manifest.id == engine_id:
            return entry.manifest
    raise AssertionError(f"manifesto '{engine_id}' não encontrado")


def test_discovery_finds_engines_by_manifest():
    ids = {entry.manifest.id for entry in discover_manifests([ENGINES_ROOT])}
    assert {"mock-image-v1", "mock-pixel-alt-v1", "diffusers-sdxl-v1"} <= ids


def test_discovery_allowlist_blocks_unlisted_engines():
    entries = discover_manifests([ENGINES_ROOT], allowlist=["mock-image-v1"])
    assert [entry.manifest.id for entry in entries] == ["mock-image-v1"]


def test_registering_incompatible_api_version_is_refused():
    manifest = _manifest("mock-image-v1").model_copy(update={"engine_api_version": "99"})
    registry = EngineRegistry()
    with pytest.raises(EngineIncompatible):
        registry.register(manifest, build_factory(manifest))


def test_duplicate_registration_requires_replace():
    manifest = _manifest("mock-image-v1")
    registry = EngineRegistry()
    registry.register(manifest, build_factory(manifest))
    with pytest.raises(EngineIncompatible):
        registry.register(manifest, build_factory(manifest))
    registry.register(manifest, build_factory(manifest), replace=True)
    assert len(registry) == 1


def test_enable_disable_and_state():
    manifest = _manifest("mock-image-v1")
    registry = EngineRegistry()
    record = registry.register(
        manifest,
        build_factory(manifest),
        EngineRuntimeConfig(engine_id=manifest.id, enabled=True),
    )

    assert record.state is EngineState.REGISTERED
    registry.disable(manifest.id)
    assert registry.get(manifest.id).state is EngineState.DISABLED
    registry.enable(manifest.id)
    assert registry.get(manifest.id).state is EngineState.REGISTERED


def test_registration_does_not_load_the_model():
    """Lazy loading (plano §36): registrar não pode inicializar nada."""
    manifest = _manifest("mock-image-v1")
    registry = EngineRegistry()
    record = registry.register(manifest, build_factory(manifest))
    assert record.handle.is_loaded is False
    assert record.handle.state is EngineState.REGISTERED


def test_lifecycle_transitions_on_first_use():
    manifest = _manifest("mock-image-v1")
    registry = EngineRegistry()
    record = registry.register(
        manifest, build_factory(manifest), EngineRuntimeConfig(engine_id=manifest.id)
    )

    async def scenario():
        assert record.handle.state is EngineState.REGISTERED
        async with record.handle.acquire():
            assert record.handle.state is EngineState.BUSY
        assert record.handle.state is EngineState.READY
        assert record.handle.is_loaded
        await record.handle.unload()
        assert record.handle.state is EngineState.REGISTERED

    run(scenario())


def test_unregister_removes_engine():
    manifest = _manifest("mock-image-v1")
    registry = EngineRegistry()
    registry.register(manifest, build_factory(manifest))
    run(registry.unregister(manifest.id))
    assert not registry.has(manifest.id)
    with pytest.raises(EngineNotFound):
        registry.get(manifest.id)


def test_capabilities_index_only_lists_enabled_engines():
    registry = EngineRegistry()
    for engine_id in ("mock-image-v1", "mock-pixel-alt-v1"):
        manifest = _manifest(engine_id)
        registry.register(
            manifest,
            build_factory(manifest),
            EngineRuntimeConfig(engine_id=engine_id, enabled=True),
        )

    index = registry.capabilities()
    pixel = next(key for key in index if str(key) == "text_to_image.pixel")
    assert set(index[pixel]) == {"mock-image-v1", "mock-pixel-alt-v1"}

    registry.disable("mock-pixel-alt-v1")
    index = registry.capabilities()
    pixel = next(key for key in index if str(key) == "text_to_image.pixel")
    assert set(index[pixel]) == {"mock-image-v1"}


def test_entrypoint_outside_allowed_prefix_is_refused(tmp_path: Path):
    """Segurança de plugins (plano §64)."""
    manifest = _manifest("mock-image-v1").model_copy(
        update={"entrypoint": "os.path:join"}
    )
    with pytest.raises(Exception):
        load_engine_class(manifest.entrypoint)


def test_invalid_manifest_is_ignored_not_fatal(tmp_path: Path):
    broken = tmp_path / "broken_engine"
    broken.mkdir()
    (broken / "manifest.json").write_text(json.dumps({"id": "sem-campos"}), encoding="utf-8")

    entries = discover_manifests([tmp_path])
    assert entries == []
