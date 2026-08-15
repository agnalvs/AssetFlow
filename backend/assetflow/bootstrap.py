"""Composition root — onde o sistema inteiro é montado.

Este é o **único** lugar que conhece todas as peças ao mesmo tempo. Ele lê a
configuração, descobre as gavetas, monta registry/resolver/kernel, storage,
job system e a fachada de geração.

Repare no que ele *não* faz: importar um engine concreto. As gavetas entram
por descoberta de manifesto, exatamente como entrará qualquer motor futuro.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .generation.kernel import (
    EngineRegistry,
    EngineResolver,
    GenerationKernel,
    RoutingPolicy,
    discover_manifests,
)
from .generation.pipelines import PipelineRegistry
from .generation.profiles import ProfileRegistry
from .generation.prompting import PromptBuilderRegistry
from .generation.service import GenerationService
from .jobs import (
    GenerationWorker,
    InMemoryJobQueue,
    InMemoryJobStore,
    JobManager,
    JobQueue,
    JobStore,
    QueueRouter,
    RetryPolicy,
)
from .settings import Settings, engine_runtime_configs, load_settings
from .storage import (
    AssetStorageService,
    GenerationRecordRepository,
    InMemoryAssetRepository,
    JsonLinesGenerationRecordRepository,
    LocalFilesystemBackend,
)

__all__ = ["AppContainer", "build_container"]

_LOG = logging.getLogger("assetflow.bootstrap")


@dataclass(slots=True)
class AppContainer:
    """Todas as dependências vivas do backend."""

    settings: Settings
    registry: EngineRegistry
    resolver: EngineResolver
    kernel: GenerationKernel
    profiles: ProfileRegistry
    pipelines: PipelineRegistry
    prompt_builders: PromptBuilderRegistry
    storage: AssetStorageService
    records: GenerationRecordRepository
    job_store: JobStore
    job_queue: JobQueue
    jobs: JobManager
    worker: GenerationWorker
    service: GenerationService
    _worker_started: bool = field(default=False, init=False)

    async def startup(self) -> None:
        """Sobe o worker embutido, quando configurado."""
        if self.settings.worker.embedded and not self._worker_started:
            await self.worker.start()
            self._worker_started = True

    async def shutdown(self) -> None:
        """Encerra worker, fila e descarrega modelos da GPU."""
        if self._worker_started:
            await self.worker.stop()
            self._worker_started = False
        await self.job_queue.close()
        await self.registry.unload_all()


def build_container(settings: Settings | None = None) -> AppContainer:
    """Monta o sistema a partir da configuração."""
    settings = settings or load_settings()

    # -- Estante: registry + gavetas descobertas -------------------------
    defaults = settings.engine_defaults
    registry = EngineRegistry(
        health_cache_ttl_s=float(defaults.get("health_cache_ttl_s", 15.0))
    )
    runtime_configs = engine_runtime_configs(settings)

    discovered = discover_manifests(
        settings.engine_discovery_paths, allowlist=settings.engine_allowlist
    )
    for entry in discovered:
        config = runtime_configs.get(entry.manifest.id)
        if config is None:
            _LOG.info(
                "gaveta '%s' encontrada mas sem bloco em engines.yaml; "
                "registrada desabilitada",
                entry.manifest.id,
            )
        try:
            registry.register_discovered(entry, config)
        except Exception as exc:
            _LOG.error("falha ao registrar gaveta '%s': %s", entry.manifest.id, exc)

    if not registry.ids():
        _LOG.warning(
            "nenhuma gaveta registrada — verifique discovery.paths e a allowlist"
        )

    # -- Roteamento por capacidade ---------------------------------------
    policy = RoutingPolicy.from_config(settings.capabilities_config)
    resolver = EngineResolver(registry, policy)
    kernel = GenerationKernel(
        registry,
        resolver,
        default_timeout_s=float(defaults.get("timeout_s", 300)),
    )

    # -- Produto: profiles, pipelines, prompts ---------------------------
    profiles = ProfileRegistry.from_config(settings.profiles_config)
    pipelines = PipelineRegistry.with_defaults()
    prompt_builders = PromptBuilderRegistry.with_defaults()

    # -- Storage ----------------------------------------------------------
    backend = LocalFilesystemBackend(settings.storage_root)
    records = JsonLinesGenerationRecordRepository(settings.history_path)
    assets = InMemoryAssetRepository()
    storage = AssetStorageService(backend, records=records, assets=assets)

    # -- Job system -------------------------------------------------------
    job_store = InMemoryJobStore()
    job_queue = InMemoryJobQueue()
    router = QueueRouter(settings.worker.queue_routes)
    jobs = JobManager(
        job_store,
        job_queue,
        router=router,
        retry_policy=RetryPolicy(
            max_attempts=settings.worker.max_attempts,
            base_delay_s=settings.worker.retry_base_delay_s,
        ),
    )

    worker = GenerationWorker(
        manager=jobs,
        kernel=kernel,
        pipelines=pipelines,
        profiles=profiles,
        storage=storage,
        prompt_builders=prompt_builders,
        queues=router.queues(),
        concurrency=settings.worker.concurrency,
        job_timeout_s=settings.worker.job_timeout_s,
        poll_timeout_s=settings.worker.poll_timeout_s,
    )

    service = GenerationService(
        kernel=kernel,
        jobs=jobs,
        profiles=profiles,
        pipelines=pipelines,
        records=records,
        default_max_attempts=settings.worker.max_attempts,
    )

    _LOG.info(
        "AssetFlow pronto: %s gaveta(s), %s profile(s), %s pipeline(s)",
        len(registry),
        len(profiles),
        len(pipelines.ids()),
    )

    return AppContainer(
        settings=settings,
        registry=registry,
        resolver=resolver,
        kernel=kernel,
        profiles=profiles,
        pipelines=pipelines,
        prompt_builders=prompt_builders,
        storage=storage,
        records=records,
        job_store=job_store,
        job_queue=job_queue,
        jobs=jobs,
        worker=worker,
        service=service,
    )
