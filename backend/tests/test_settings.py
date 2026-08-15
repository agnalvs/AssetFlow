"""Testes da configuração externa (plano §65).

O que se protege aqui: nenhuma decisão de motor, modelo, device, precisão ou
tempo limite pode estar hardcoded — tudo tem de vir de YAML/ambiente.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from assetflow.settings import engine_runtime_configs, load_settings

from tests.conftest import BACKEND_ROOT


def _write_config(tmp_path: Path, engines: dict) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "engines.yaml").write_text(
        yaml.safe_dump({"engine_api_version": "1", "engines": engines}),
        encoding="utf-8",
    )
    return config_dir


def test_engine_config_is_read_from_yaml(tmp_path: Path):
    config_dir = _write_config(
        tmp_path,
        {
            "motor-x": {
                "enabled": True,
                "model": {"id": "org/modelo", "revision": "rev1"},
                "device": {"type": "cuda"},
                "precision": {"type": "bf16"},
                "runtime": {"enable_sequential_cpu_offload": True},
                "options": {"guidance_scale": 3.5},
            }
        },
    )
    settings = load_settings(base_dir=tmp_path, config_dir=config_dir, data_dir=tmp_path / "data")
    configs = engine_runtime_configs(settings)

    config = configs["motor-x"]
    assert config.enabled is True
    assert config.model.id == "org/modelo"
    assert config.model.revision == "rev1"
    assert config.device.type == "cuda"
    assert config.precision.type == "bf16"
    assert config.runtime["enable_sequential_cpu_offload"] is True
    assert config.options["guidance_scale"] == 3.5
    # Cada gaveta ganha um workspace isolado (cache de modelo, etc.).
    assert config.workspace_dir and "motor-x" in config.workspace_dir


def test_timeouts_can_be_overridden_per_environment(tmp_path: Path):
    """Hardware lento pode alargar o tempo declarado no manifesto."""
    config_dir = _write_config(
        tmp_path,
        {"motor-x": {"enabled": True, "timeouts": {"timeout_s": 1800, "load_timeout_s": 3600}}},
    )
    settings = load_settings(base_dir=tmp_path, config_dir=config_dir, data_dir=tmp_path / "data")
    config = engine_runtime_configs(settings)["motor-x"]

    assert config.timeout_s == 1800.0
    assert config.load_timeout_s == 3600.0


def test_timeouts_default_to_the_manifest(tmp_path: Path):
    config_dir = _write_config(tmp_path, {"motor-x": {"enabled": True}})
    settings = load_settings(base_dir=tmp_path, config_dir=config_dir, data_dir=tmp_path / "data")
    config = engine_runtime_configs(settings)["motor-x"]

    assert config.timeout_s is None
    assert config.load_timeout_s is None


def test_environment_variables_win_over_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config_dir = _write_config(
        tmp_path,
        {"motor-a": {"enabled": False}, "motor-b": {"enabled": True}},
    )
    monkeypatch.setenv("ASSETFLOW_ENGINES_ENABLED", "motor-a")
    monkeypatch.setenv("ASSETFLOW_ENGINES_DISABLED", "motor-b")

    settings = load_settings(base_dir=tmp_path, config_dir=config_dir, data_dir=tmp_path / "data")
    configs = engine_runtime_configs(settings)

    assert configs["motor-a"].enabled is True
    assert configs["motor-b"].enabled is False


def test_handle_uses_configured_load_timeout():
    """A precedência chega até o EngineHandle."""
    from assetflow.generation.kernel.discovery import build_factory, discover_manifests
    from assetflow.generation.kernel.lifecycle import EngineHandle
    from assetflow.generation.schemas import EngineRuntimeConfig

    entry = next(
        item
        for item in discover_manifests(
            [BACKEND_ROOT / "assetflow" / "generation" / "engines"]
        )
        if item.manifest.id == "mock-image-v1"
    )

    default = EngineHandle(
        entry.manifest,
        build_factory(entry.manifest),
        EngineRuntimeConfig(engine_id="mock-image-v1"),
    )
    assert default._load_timeout_s == entry.manifest.timeouts.load_timeout_s

    configured = EngineHandle(
        entry.manifest,
        build_factory(entry.manifest),
        EngineRuntimeConfig(engine_id="mock-image-v1", load_timeout_s=1234),
    )
    assert configured._load_timeout_s == 1234


def test_real_project_config_is_valid():
    """O YAML versionado no repositório precisa carregar sem erro."""
    settings = load_settings(base_dir=BACKEND_ROOT)
    configs = engine_runtime_configs(settings)

    assert "diffusers-sdxl-v1" in configs
    assert configs["diffusers-sdxl-v1"].model.id.startswith("stabilityai/")
    assert configs["mock-image-v1"].enabled is True
