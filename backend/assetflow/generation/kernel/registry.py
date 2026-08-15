"""Engine Registry — a estante propriamente dita (plano §11).

Mantém todas as gavetas instaladas, seu estado e sua configuração. Só devolve
motores válidos e compatíveis com a Engine API suportada.

Operações: register, unregister, enable, disable, get, list, health, reload.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ..schemas import (
    SUPPORTED_ENGINE_API_VERSIONS,
    Capability,
    EngineDescriptor,
    EngineHealth,
    EngineManifest,
    EngineRuntimeConfig,
    EngineState,
    utcnow,
)
from .contracts import EngineFactory
from .discovery import DiscoveredEngine, build_factory
from .exceptions import EngineIncompatible, EngineNotFound
from .lifecycle import EngineHandle

__all__ = ["EngineRecord", "EngineRegistry"]

_LOG = logging.getLogger("assetflow.generation.registry")


@dataclass(slots=True)
class EngineRecord:
    """Uma gaveta registrada na estante."""

    manifest: EngineManifest
    handle: EngineHandle
    source: str = "programmatic"
    registered_at: datetime = field(default_factory=utcnow)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def enabled(self) -> bool:
        return self.handle.enabled

    @property
    def state(self) -> EngineState:
        return self.handle.state

    def declares(self, capability: Capability | str) -> bool:
        return self.manifest.declares(capability)


class EngineRegistry:
    """Registro central de motores.

    O registry não sabe gerar imagem, não sabe escolher motor e não conhece
    job algum. Ele apenas mantém a estante organizada.
    """

    def __init__(
        self,
        *,
        supported_api_versions: frozenset[str] = SUPPORTED_ENGINE_API_VERSIONS,
        health_cache_ttl_s: float = 15.0,
    ) -> None:
        self._records: dict[str, EngineRecord] = {}
        self._supported = supported_api_versions
        self._health_cache_ttl_s = health_cache_ttl_s

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def register(
        self,
        manifest: EngineManifest,
        factory: EngineFactory,
        config: EngineRuntimeConfig | None = None,
        *,
        source: str = "programmatic",
        replace: bool = False,
    ) -> EngineRecord:
        """Registra uma gaveta.

        Raises:
            EngineIncompatible: se a Engine API declarada não for suportada
                (plano §10) ou se o id já existir sem ``replace=True``.
        """
        if manifest.engine_api_version not in self._supported:
            raise EngineIncompatible(
                f"motor '{manifest.id}' declara engine_api_version="
                f"'{manifest.engine_api_version}'; este backend suporta "
                f"{sorted(self._supported)}",
                engine_id=manifest.id,
            )

        if manifest.id in self._records and not replace:
            raise EngineIncompatible(
                f"motor '{manifest.id}' já registrado", engine_id=manifest.id
            )

        runtime_config = config or EngineRuntimeConfig(
            engine_id=manifest.id, enabled=manifest.status == "enabled"
        )
        handle = EngineHandle(
            manifest,
            factory,
            runtime_config,
            health_cache_ttl_s=self._health_cache_ttl_s,
        )
        record = EngineRecord(manifest=manifest, handle=handle, source=source)
        self._records[manifest.id] = record
        _LOG.info(
            "gaveta registrada: %s v%s (%s) enabled=%s",
            manifest.id,
            manifest.version,
            manifest.provider,
            runtime_config.enabled,
        )
        return record

    def register_discovered(
        self,
        discovered: DiscoveredEngine,
        config: EngineRuntimeConfig | None = None,
        *,
        replace: bool = False,
    ) -> EngineRecord:
        """Registra a partir de um manifesto encontrado no disco."""
        return self.register(
            discovered.manifest,
            build_factory(discovered.manifest),
            config,
            source=str(discovered.source),
            replace=replace,
        )

    async def unregister(self, engine_id: str) -> None:
        """Remove a gaveta da estante, descarregando o modelo antes."""
        record = self._records.pop(engine_id, None)
        if record is None:
            raise EngineNotFound(f"motor '{engine_id}' não registrado", engine_id=engine_id)
        await record.handle.unload()
        _LOG.info("gaveta removida: %s", engine_id)

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------
    def get(self, engine_id: str) -> EngineRecord:
        record = self._records.get(engine_id)
        if record is None:
            raise EngineNotFound(f"motor '{engine_id}' não registrado", engine_id=engine_id)
        return record

    def find(self, engine_id: str) -> EngineRecord | None:
        return self._records.get(engine_id)

    def has(self, engine_id: str) -> bool:
        return engine_id in self._records

    def list(
        self,
        *,
        capability: Capability | str | None = None,
        enabled_only: bool = False,
        usable_only: bool = False,
    ) -> list[EngineRecord]:
        """Lista gavetas, opcionalmente filtrando por capacidade e estado."""
        records = list(self._records.values())
        if capability is not None:
            records = [record for record in records if record.declares(capability)]
        if enabled_only:
            records = [record for record in records if record.enabled]
        if usable_only:
            records = [record for record in records if record.state.is_usable]
        return sorted(records, key=lambda record: record.id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._records))

    def capabilities(self) -> dict[Capability, tuple[str, ...]]:
        """Mapa capacidade -> motores habilitados que a declaram."""
        mapping: dict[Capability, list[str]] = {}
        for record in self._records.values():
            if not record.enabled:
                continue
            for capability in record.manifest.capabilities:
                mapping.setdefault(capability, []).append(record.id)
        return {key: tuple(sorted(value)) for key, value in sorted(mapping.items(), key=str)}

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def enable(self, engine_id: str) -> EngineRecord:
        record = self.get(engine_id)
        record.handle.enable()
        _LOG.info("gaveta habilitada: %s", engine_id)
        return record

    def disable(self, engine_id: str) -> EngineRecord:
        record = self.get(engine_id)
        record.handle.disable()
        _LOG.info("gaveta desabilitada: %s", engine_id)
        return record

    async def health(self, *, force: bool = False) -> dict[str, EngineHealth]:
        """Health check de todas as gavetas, em paralelo."""
        records = self.list()
        results = await asyncio.gather(
            *(record.handle.health(force=force) for record in records),
            return_exceptions=True,
        )
        health: dict[str, EngineHealth] = {}
        for record, result in zip(records, results):
            if isinstance(result, BaseException):  # pragma: no cover - defensivo
                _LOG.warning("health check falhou para %s: %s", record.id, result)
                continue
            health[record.id] = result
        return health

    async def describe(self, engine_id: str, *, include_health: bool = True) -> EngineDescriptor:
        record = self.get(engine_id)
        health = await record.handle.health() if include_health else None
        return EngineDescriptor(
            manifest=record.manifest,
            state=record.state,
            enabled=record.enabled,
            api_compatible=record.manifest.engine_api_version in self._supported,
            health=health,
            last_error=record.handle.last_error,
            registered_at=record.registered_at,
            source=record.source,
        )

    async def describe_all(self, *, include_health: bool = True) -> list[EngineDescriptor]:
        return [
            await self.describe(record.id, include_health=include_health)
            for record in self.list()
        ]

    # ------------------------------------------------------------------
    # Manutenção
    # ------------------------------------------------------------------
    async def reload(self, engine_id: str) -> EngineRecord:
        """Descarrega o motor; a próxima geração o inicializa de novo.

        Se o registro veio de um manifesto em disco, o manifesto é relido —
        assim, editar um manifesto não exige reiniciar o backend.
        """
        record = self.get(engine_id)
        await record.handle.unload()

        source = Path(record.source) if record.source != "programmatic" else None
        if source is not None and source.exists():
            import json

            try:
                with source.open("r", encoding="utf-8") as handle:
                    manifest = EngineManifest.model_validate(json.load(handle))
            except Exception as exc:
                _LOG.error("falha ao reler manifesto de %s: %s", engine_id, exc)
                return record
            if manifest.id != engine_id:
                _LOG.error(
                    "manifesto em %s mudou de id (%s -> %s); reload abortado",
                    source,
                    engine_id,
                    manifest.id,
                )
                return record
            return self.register(
                manifest,
                build_factory(manifest),
                record.handle.config,
                source=record.source,
                replace=True,
            )
        return record

    async def unload_all(self) -> None:
        """Descarrega todos os modelos (shutdown do worker/API)."""
        await asyncio.gather(
            *(record.handle.unload() for record in self.list()), return_exceptions=True
        )

    def __contains__(self, engine_id: object) -> bool:  # pragma: no cover - trivial
        return isinstance(engine_id, str) and engine_id in self._records

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._records)

    def __iter__(self) -> Iterable[EngineRecord]:  # pragma: no cover - trivial
        return iter(self.list())
