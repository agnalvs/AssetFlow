"""Configuração do backend (plano §65).

Nada de motor, modelo, device ou precisão fica hardcoded. Tudo vem de:

1. arquivos YAML em ``config/`` (``engines``, ``capabilities``, ``profiles``);
2. variáveis de ambiente com prefixo ``ASSETFLOW_`` (que têm precedência).

O objetivo prático: habilitar/desabilitar uma gaveta, trocar o modelo ou
mudar a ordem de preferência sem tocar em código nem reconstruir imagem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from .generation.schemas import (
    AssetFlowModel,
    EngineDeviceConfig,
    EngineModelConfig,
    EnginePrecisionConfig,
    EngineRuntimeConfig,
)

__all__ = [
    "StorageSettings",
    "WorkerSettings",
    "ApiSettings",
    "Settings",
    "load_settings",
    "engine_runtime_configs",
]

_ENV_PREFIX = "ASSETFLOW_"
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class StorageSettings(AssetFlowModel):
    """Onde os assets e o histórico são gravados."""

    backend: str = Field(default="local", pattern=r"^(local)$")
    root: str = "data/assets"
    history_file: str = "data/history/generations.jsonl"


class WorkerSettings(AssetFlowModel):
    """Execução dos jobs."""

    #: Sobe o worker dentro do processo da API (bom para dev, ruim para GPU).
    embedded: bool = True
    concurrency: int = Field(default=1, ge=1, le=32)
    job_timeout_s: float = Field(default=900.0, gt=0)
    poll_timeout_s: float = Field(default=0.5, gt=0)
    max_attempts: int = Field(default=2, ge=1, le=10)
    retry_base_delay_s: float = Field(default=1.0, ge=0)
    #: Filas por capacidade (plano §33), ex.: {"text_to_image.pixel": "generation.pixel"}.
    queue_routes: dict[str, str] = Field(default_factory=dict)


class ApiSettings(AssetFlowModel):
    title: str = "AssetFlow Generation API"
    root_path: str = ""
    cors_origins: tuple[str, ...] = ("*",)
    serve_local_assets: bool = True
    #: Endpoints de diagnóstico (`/api/dev/...`). Desligados por padrão: eles
    #: aceitam imagem arbitrária e existem para pesquisa, não para produção
    #: (plano Pixel §78). Ligue com `ASSETFLOW_DEV_ENDPOINTS=1`.
    dev_endpoints: bool = False


class Settings(AssetFlowModel):
    """Configuração completa do backend."""

    base_dir: Path = _BACKEND_ROOT
    config_dir: Path = _BACKEND_ROOT / "config"
    data_dir: Path = _BACKEND_ROOT / "data"

    storage: StorageSettings = Field(default_factory=StorageSettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    #: Conteúdo bruto dos YAMLs (interpretado pelos respectivos registries).
    engines_config: dict[str, Any] = Field(default_factory=dict)
    capabilities_config: dict[str, Any] = Field(default_factory=dict)
    profiles_config: dict[str, Any] = Field(default_factory=dict)
    #: `pixel_profiles.yaml` — o contrato Pixel Exact de cada profile
    #: (resolução lógica, paleta, alpha, canvas, preview). Plano Pixel §64.
    pixel_profiles_config: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    @property
    def asset_taxonomy_dir(self) -> Path:
        """``config/asset_taxonomy/`` — o vocabulário semântico (plano T→J §5).

        É um diretório, e não um arquivo, porque cada tipo de asset tem o seu
        (``prop.yaml``, ``character.yaml``...). Acrescentar um tipo é
        acrescentar um arquivo — sem tocar em código nem nos outros.

        Ausente, o classificador fica mudo e o tipo do profile prevalece: o
        AssetFlow perde a classificação semântica, não a capacidade de gerar.
        """
        return self._resolve(self.config_dir / "asset_taxonomy")

    @property
    def engine_discovery_paths(self) -> tuple[Path, ...]:
        discovery = self.engines_config.get("discovery") or {}
        paths = discovery.get("paths") or ["assetflow/generation/engines"]
        return tuple(self._resolve(Path(path)) for path in paths)

    @property
    def engine_allowlist(self) -> tuple[str, ...] | None:
        discovery = self.engines_config.get("discovery") or {}
        allowlist = discovery.get("allowlist")
        if allowlist is None:
            return None
        return tuple(str(item) for item in allowlist)

    @property
    def engine_defaults(self) -> dict[str, Any]:
        return dict(self.engines_config.get("defaults") or {})

    @property
    def storage_root(self) -> Path:
        return self._resolve(Path(self.storage.root))

    @property
    def history_path(self) -> Path:
        return self._resolve(Path(self.storage.history_file))

    def engine_workspace(self, engine_id: str) -> Path:
        return self._resolve(self.data_dir / "engines" / engine_id)

    def _resolve(self, path: Path) -> Path:
        return path if path.is_absolute() else (self.base_dir / path).resolve()


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuração inválida em {path}: raiz deve ser um mapeamento")
    return data


def _env(name: str) -> str | None:
    return os.environ.get(f"{_ENV_PREFIX}{name}")


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    *,
    config_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
    base_dir: Path | str | None = None,
) -> Settings:
    """Carrega a configuração de YAML + ambiente.

    Precedência: argumento explícito > variável de ambiente > YAML > padrão.
    """
    base = Path(base_dir or _env("BASE_DIR") or _BACKEND_ROOT).resolve()
    configs = Path(config_dir or _env("CONFIG_DIR") or (base / "config"))
    data = Path(data_dir or _env("DATA_DIR") or (base / "data"))

    engines_config = _read_yaml(configs / "engines.yaml")
    capabilities_config = _read_yaml(configs / "capabilities.yaml")
    profiles_config = _read_yaml(configs / "profiles.yaml")
    pixel_profiles_config = _read_yaml(configs / "pixel_profiles.yaml")

    storage = StorageSettings(
        root=_env("STORAGE_ROOT") or str(data / "assets"),
        history_file=_env("HISTORY_FILE") or str(data / "history" / "generations.jsonl"),
    )

    worker = WorkerSettings(
        embedded=_env_bool("WORKER_EMBEDDED", True),
        concurrency=int(_env("WORKER_CONCURRENCY") or 1),
        job_timeout_s=float(_env("JOB_TIMEOUT_S") or 900.0),
        max_attempts=int(_env("JOB_MAX_ATTEMPTS") or 2),
        queue_routes=_parse_queue_routes(_env("QUEUE_ROUTES")),
    )

    api = ApiSettings(
        title=_env("API_TITLE") or "AssetFlow Generation API",
        root_path=_env("API_ROOT_PATH") or "",
        cors_origins=tuple((_env("CORS_ORIGINS") or "*").split(",")),
        dev_endpoints=_env_bool("DEV_ENDPOINTS", False),
    )

    return Settings(
        base_dir=base,
        config_dir=configs,
        data_dir=data,
        storage=storage,
        worker=worker,
        api=api,
        engines_config=engines_config,
        capabilities_config=capabilities_config,
        profiles_config=profiles_config,
        pixel_profiles_config=pixel_profiles_config,
    )


def _parse_queue_routes(raw: str | None) -> dict[str, str]:
    """``"text_to_image.pixel=generation.pixel,..."`` -> dict."""
    if not raw:
        return {}
    routes: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        routes[key.strip()] = value.strip()
    return routes


def engine_runtime_configs(settings: Settings) -> dict[str, EngineRuntimeConfig]:
    """Constrói a configuração de runtime de cada gaveta.

    A habilitação também pode vir do ambiente::

        ASSETFLOW_ENGINES_ENABLED="mock-image-v1,diffusers-sdxl-v1"
        ASSETFLOW_ENGINES_DISABLED="mock-pixel-alt-v1"
    """
    forced_enabled = {
        item.strip() for item in (_env("ENGINES_ENABLED") or "").split(",") if item.strip()
    }
    forced_disabled = {
        item.strip() for item in (_env("ENGINES_DISABLED") or "").split(",") if item.strip()
    }

    configs: dict[str, EngineRuntimeConfig] = {}
    for engine_id, raw in (settings.engines_config.get("engines") or {}).items():
        raw = raw or {}
        enabled = bool(raw.get("enabled", False))
        if engine_id in forced_enabled:
            enabled = True
        if engine_id in forced_disabled:
            enabled = False

        timeouts = raw.get("timeouts") or {}
        configs[engine_id] = EngineRuntimeConfig(
            engine_id=engine_id,
            enabled=enabled,
            model=EngineModelConfig.model_validate(raw.get("model") or {}),
            device=EngineDeviceConfig.model_validate(raw.get("device") or {}),
            precision=EnginePrecisionConfig.model_validate(raw.get("precision") or {}),
            runtime=dict(raw.get("runtime") or {}),
            options=dict(raw.get("options") or {}),
            workspace_dir=str(settings.engine_workspace(engine_id)),
            timeout_s=_optional_float(timeouts.get("timeout_s")),
            load_timeout_s=_optional_float(timeouts.get("load_timeout_s")),
        )
    return configs


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
