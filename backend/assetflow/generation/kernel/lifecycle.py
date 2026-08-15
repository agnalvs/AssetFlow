"""Engine Lifecycle (plano §35 e §36).

Uma gaveta não é um objeto qualquer: ela pode segurar 12 GB de VRAM. O
:class:`EngineHandle` é quem controla esse ciclo — criação preguiçosa,
inicialização única, ocupação, degradação, descarga.

Lazy loading é o padrão: registrar um motor **não** carrega modelo nenhum.
O primeiro job é que dispara a inicialização.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ..schemas import (
    EngineHealth,
    EngineHealthStatus,
    EngineManifest,
    EngineRuntimeConfig,
    EngineState,
    utcnow,
)
from .contracts import EngineFactory, ImageGenerationEngine
from .exceptions import (
    EngineDisabled,
    EngineInitializationError,
    EngineUnavailable,
)

__all__ = ["EngineHandle"]

_LOG = logging.getLogger("assetflow.generation.lifecycle")


class EngineHandle:
    """Envelope de ciclo de vida em torno de uma instância de gaveta.

    Thread-safety: o handle é seguro para uso concorrente dentro de um mesmo
    event loop. Um motor com ``supports.batch=False`` continua podendo
    receber jobs paralelos — quem serializa isso é o worker, não o handle.
    """

    def __init__(
        self,
        manifest: EngineManifest,
        factory: EngineFactory,
        config: EngineRuntimeConfig,
        *,
        health_cache_ttl_s: float = 15.0,
        load_timeout_s: float | None = None,
    ) -> None:
        self._manifest = manifest
        self._factory = factory
        self._config = config
        self._health_cache_ttl_s = health_cache_ttl_s
        self._load_timeout_s = load_timeout_s or manifest.timeouts.load_timeout_s

        self._instance: ImageGenerationEngine | None = None
        self._state: EngineState = EngineState.REGISTERED
        self._enabled = config.enabled
        self._lock = asyncio.Lock()
        self._active = 0
        self._last_error: str | None = None
        self._health: EngineHealth | None = None
        self._health_at: float = 0.0
        self._load_ms: float | None = None
        self._history: list[tuple[float, EngineState]] = [(time.time(), EngineState.REGISTERED)]

    # ------------------------------------------------------------------
    # Propriedades
    # ------------------------------------------------------------------
    @property
    def manifest(self) -> EngineManifest:
        return self._manifest

    @property
    def engine_id(self) -> str:
        return self._manifest.id

    @property
    def config(self) -> EngineRuntimeConfig:
        return self._config

    @property
    def state(self) -> EngineState:
        if not self._enabled:
            return EngineState.DISABLED
        return self._state

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def load_ms(self) -> float | None:
        """Tempo da última inicialização — alimenta ``timings.model_load_ms``."""
        return self._load_ms

    @property
    def is_loaded(self) -> bool:
        return self._instance is not None and self._state in {
            EngineState.READY,
            EngineState.BUSY,
            EngineState.DEGRADED,
        }

    @property
    def history(self) -> tuple[tuple[float, EngineState], ...]:
        return tuple(self._history)

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def _transition(self, state: EngineState, *, error: str | None = None) -> None:
        if state is not self._state:
            _LOG.debug("engine %s: %s -> %s", self.engine_id, self._state.value, state.value)
            self._state = state
            self._history.append((time.time(), state))
            if len(self._history) > 100:
                del self._history[:-100]
        if error is not None:
            self._last_error = error

    def enable(self) -> None:
        self._enabled = True
        if self._state is EngineState.DISABLED:
            self._transition(EngineState.REGISTERED)

    def disable(self) -> None:
        self._enabled = False
        self._invalidate_health()

    def update_config(self, config: EngineRuntimeConfig) -> None:
        """Aplica nova configuração. Exige reload para ter efeito no modelo."""
        self._config = config
        self._enabled = config.enabled

    def mark_degraded(self, reason: str) -> None:
        """Marca o motor como degradado — o resolver passa a evitá-lo (§43)."""
        self._transition(EngineState.DEGRADED, error=reason)
        self._invalidate_health()

    def mark_failed(self, reason: str) -> None:
        self._transition(EngineState.FAILED, error=reason)
        self._invalidate_health()

    def _invalidate_health(self) -> None:
        self._health = None
        self._health_at = 0.0

    # ------------------------------------------------------------------
    # Instância
    # ------------------------------------------------------------------
    def instance_unsafe(self) -> ImageGenerationEngine:
        """Cria (sem inicializar) a instância da gaveta.

        Construtores de engine **não podem** carregar modelo — é aqui que a
        promessa de lazy loading se sustenta.
        """
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    async def ensure_ready(self) -> ImageGenerationEngine:
        """Garante que a gaveta está inicializada e pronta.

        Raises:
            EngineDisabled: se o motor foi desligado por configuração.
            EngineInitializationError: se ``initialize()`` falhar.
        """
        if not self._enabled:
            raise EngineDisabled(
                f"motor '{self.engine_id}' está desabilitado", engine_id=self.engine_id
            )

        if self._state in {EngineState.READY, EngineState.BUSY, EngineState.DEGRADED}:
            return self.instance_unsafe()

        async with self._lock:
            # Outra corrotina pode ter inicializado enquanto esperávamos.
            if self._state in {EngineState.READY, EngineState.BUSY, EngineState.DEGRADED}:
                return self.instance_unsafe()

            engine = self.instance_unsafe()
            self._transition(EngineState.INITIALIZING)
            started = time.perf_counter()
            try:
                await asyncio.wait_for(
                    engine.initialize(self._config), timeout=self._load_timeout_s
                )
            except asyncio.TimeoutError as exc:
                self._load_ms = (time.perf_counter() - started) * 1000.0
                message = (
                    f"inicialização do motor '{self.engine_id}' excedeu "
                    f"{self._load_timeout_s}s"
                )
                self.mark_failed(message)
                raise EngineInitializationError(
                    message, engine_id=self.engine_id
                ) from exc
            except Exception as exc:
                self._load_ms = (time.perf_counter() - started) * 1000.0
                message = f"falha ao inicializar '{self.engine_id}': {exc}"
                self.mark_failed(message)
                raise EngineInitializationError(
                    message, engine_id=self.engine_id, detail={"cause": repr(exc)}
                ) from exc

            self._load_ms = (time.perf_counter() - started) * 1000.0
            self._last_error = None
            self._transition(EngineState.READY)
            self._invalidate_health()
            return engine

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[ImageGenerationEngine]:
        """Reserva a gaveta para uma execução, cuidando de READY/BUSY."""
        engine = await self.ensure_ready()
        self._active += 1
        if self._state is EngineState.READY:
            self._transition(EngineState.BUSY)
        try:
            yield engine
        finally:
            self._active -= 1
            if self._active <= 0:
                self._active = 0
                if self._state is EngineState.BUSY:
                    self._transition(EngineState.READY)

    # ------------------------------------------------------------------
    # Saúde
    # ------------------------------------------------------------------
    async def health(self, *, force: bool = False) -> EngineHealth:
        """Health check com cache curto (plano §43).

        Nunca levanta exceção: um motor quebrado devolve ``unavailable``.
        """
        if not self._enabled:
            return EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                detail="motor desabilitado por configuração",
                checked_at=utcnow(),
            )

        now = time.monotonic()
        if not force and self._health is not None:
            if now - self._health_at < self._health_cache_ttl_s:
                return self._health

        try:
            engine = self.instance_unsafe()
            health = await engine.health_check()
        except Exception as exc:  # pragma: no cover - defensivo
            health = EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                detail=f"health_check falhou: {exc}",
            )

        if health.status is EngineHealthStatus.UNAVAILABLE and self._state not in {
            EngineState.FAILED,
            EngineState.DISABLED,
        }:
            self._transition(EngineState.FAILED, error=health.detail)
        elif health.status is EngineHealthStatus.DEGRADED and self._state is EngineState.READY:
            self._transition(EngineState.DEGRADED, error=health.detail)
        elif health.status is EngineHealthStatus.HEALTHY and self._state in {
            EngineState.FAILED,
            EngineState.DEGRADED,
        }:
            # Recuperação: o motor voltou a responder.
            self._transition(
                EngineState.READY if self._instance is not None else EngineState.REGISTERED
            )

        self._health = health
        self._health_at = now
        return health

    async def ensure_usable(self) -> None:
        """Valida saúde antes de despachar, convertendo em erro normalizado."""
        health = await self.health()
        if not health.is_usable:
            raise EngineUnavailable(
                f"motor '{self.engine_id}' indisponível: {health.detail or 'sem detalhe'}",
                engine_id=self.engine_id,
            )

    # ------------------------------------------------------------------
    # Descarga
    # ------------------------------------------------------------------
    async def unload(self) -> None:
        """Descarrega o modelo, mantendo o motor registrado (plano §37)."""
        async with self._lock:
            if self._instance is None:
                self._transition(EngineState.REGISTERED)
                return
            self._transition(EngineState.UNLOADING)
            try:
                await self._instance.unload()
            except Exception as exc:  # pragma: no cover - defensivo
                _LOG.warning("falha ao descarregar '%s': %s", self.engine_id, exc)
                self._last_error = f"falha no unload: {exc}"
            finally:
                self._instance = None
                self._load_ms = None
                self._invalidate_health()
                self._transition(EngineState.REGISTERED)
