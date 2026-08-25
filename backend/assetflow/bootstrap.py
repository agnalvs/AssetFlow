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
    AutoEnginePolicy,
    EngineCatalog,
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
from .generation.spec import (
    AssetTaxonomy,
    AssetTypeClassifier,
    ConstraintResolver,
)
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
from .llm import ChatClient, ChatConfig, LLMPixelReviewer
from .pixel import PixelProfileRegistry
from .pixel.optimizer import AssetFlowPixelOptimizer, PixelReviewer, ReviewLoop
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
    catalog: EngineCatalog
    engine_policy: AutoEnginePolicy
    resolver: EngineResolver
    kernel: GenerationKernel
    #: O estágio que toda geração Pixel atravessa (plano Optimizer §33).
    #: Ele não está no ``EngineRegistry`` e nunca estará: não é uma tecnologia
    #: de geração de imagem, é o que corrige a imagem gerada (§79).
    optimizer: AssetFlowPixelOptimizer
    profiles: ProfileRegistry
    pixel_profiles: PixelProfileRegistry
    pipelines: PipelineRegistry
    prompt_builders: PromptBuilderRegistry
    taxonomy: AssetTaxonomy
    constraints: ConstraintResolver
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
        # Ferramenta interna não existe em produção (plano de correção §6).
        # Note que ela é pulada no **registro**, e não escondida depois: uma
        # gaveta registrada continua resolvível por capacidade, e "escondida
        # mas usável" não é o que o §6 pede.
        if entry.manifest.catalog.dev_only and not settings.show_mock_engines:
            _LOG.info(
                "gaveta '%s' é de desenvolvimento e foi ignorada (APP_ENV=%s)",
                entry.manifest.id,
                settings.app_env.value,
            )
            continue
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

    # -- Vitrine e política de seleção automática (plano de motores §6 e §16) ------
    # O catálogo descreve as gavetas para quem escolhe; a política diz o que
    # "Auto" prefere. Nenhum dos dois executa nada — quem executa é o kernel.
    catalog = EngineCatalog(registry)
    engine_policy = AutoEnginePolicy.from_config(registry, settings.engine_policy_config)

    # -- Roteamento por capacidade ---------------------------------------
    policy = RoutingPolicy.from_config(settings.capabilities_config)
    resolver = EngineResolver(registry, policy)
    kernel = GenerationKernel(
        registry,
        resolver,
        default_timeout_s=float(defaults.get("timeout_s", 300)),
    )

    # -- Pixel Optimizer (plano Optimizer §33 e §46) ----------------------
    #
    # Ele é montado aqui, ao lado do kernel, e **não** entra no registry de
    # gavetas. A distinção é a arquitetura inteira do plano: uma gaveta é
    # escolhível e produz imagem; o Optimizer não é escolhível e corrige a
    # imagem produzida. Quem pede um asset escolhe o motor, e só (§25).
    optimizer = _pixel_optimizer(settings)

    # -- Produto: profiles, pipelines, prompts ---------------------------
    profiles = ProfileRegistry.from_config(settings.profiles_config)
    # Profiles Pixel Exact: o contrato do arquivo final (resolução lógica,
    # paleta, alpha, canvas, preview). Vive em YAML pelo mesmo motivo dos
    # outros — trocar a regra não pode exigir alterar código (plano Pixel §64).
    pixel_profiles = PixelProfileRegistry.from_config(settings.pixel_profiles_config)
    pipelines = PipelineRegistry.with_defaults(pixel_profiles, optimizer)
    prompt_builders = PromptBuilderRegistry.with_defaults()

    # Taxonomia + resolver de restrições: o caminho do texto até o Final
    # Resolved Spec (plano T→J §11 e §15). O vocabulário é configuração, como
    # profiles e contratos Pixel — nenhum termo mora em código.
    taxonomy = AssetTaxonomy.from_directory(settings.asset_taxonomy_dir)
    # A política entra como *conselheiro* do resolver: é assim que o modo
    # "Auto" ganha um motor e um motivo já na pré-visualização, sem que a
    # camada que resolve o contrato precise conhecer a estante (plano de motores §17).
    constraints = ConstraintResolver(
        AssetTypeClassifier(taxonomy),
        advisor=engine_policy,
    )

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
        constraints=constraints,
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
        prompt_builders=prompt_builders,
        constraints=constraints,
        records=records,
        engine_catalog=catalog,
        default_max_attempts=settings.worker.max_attempts,
    )

    _LOG.info(
        "AssetFlow pronto [%s]: %s gaveta(s), %s profile(s), "
        "%s profile(s) Pixel, %s pipeline(s), %s vocabulário(s) de asset "
        "| otimização %s",
        settings.app_env.value,
        len(registry),
        len(profiles),
        len(pixel_profiles),
        len(pipelines.ids()),
        len(taxonomy),
        "ligada" if optimizer.enabled else "DESLIGADA",
    )

    return AppContainer(
        settings=settings,
        registry=registry,
        catalog=catalog,
        engine_policy=engine_policy,
        resolver=resolver,
        optimizer=optimizer,
        kernel=kernel,
        profiles=profiles,
        pixel_profiles=pixel_profiles,
        pipelines=pipelines,
        prompt_builders=prompt_builders,
        taxonomy=taxonomy,
        constraints=constraints,
        storage=storage,
        records=records,
        job_store=job_store,
        job_queue=job_queue,
        jobs=jobs,
        worker=worker,
        service=service,
    )


def _pixel_optimizer(settings: Settings) -> AssetFlowPixelOptimizer:
    """O Pixel Optimizer, montado a partir de ``config/optimizer.yaml`` (§42).

    Configuração ausente é o caso normal, não o excepcional: os padrões do
    próprio Optimizer já são os do plano — revisor determinístico, três
    voltas, ligado. O arquivo existe para quem quiser mudar isso.

    ``enabled: false`` é um interruptor de **instalação**, para diagnóstico.
    Ele não é uma opção de quem pede um asset (§46), e quando está desligado o
    relatório do job traz o status ``disabled`` — um estágio que não rodou
    precisa aparecer, nunca sumir.
    """
    config = (settings.optimizer_config.get("optimizer") or {})
    enabled = bool(config.get("enabled", True))

    try:
        iterations = int(config.get("max_iterations", 3))
    except (TypeError, ValueError):
        _LOG.warning(
            "max_iterations inválido em optimizer.yaml: %r; valem 3 voltas",
            config.get("max_iterations"),
        )
        iterations = 3

    return AssetFlowPixelOptimizer(
        loop=ReviewLoop(
            reviewer=_pixel_reviewer(config.get("reviewer") or {}),
            max_iterations=iterations,
        ),
        enabled=enabled,
    )


def _pixel_reviewer(config: dict) -> PixelReviewer:
    """Quem diagnostica o sprite (plano Optimizer §42).

    ``heuristic`` por padrão. Com ``type: llm`` e um provedor configurado, o
    revisor deixa de ter lista fixa de problemas — e as correções continuam
    com as mesmas garantias, porque só o **diagnóstico** muda: quem decide o
    reparo é o planejador determinístico, atrás da guarda de paleta e da regra
    de que otimizar não pode piorar (§16, §17, §20).

    Configuração incompleta não derruba o boot nem vira surpresa em tempo de
    geração: o aviso sai aqui, e o Optimizer segue com o determinístico.
    """
    kind = str(config.get("type") or "heuristic").strip().lower()
    if kind != "llm":
        return PixelReviewer()

    chat = ChatConfig.from_config(config)
    if not chat.configured:
        _LOG.warning(
            "reviewer.type='llm' mas falta `base_url`/`model` em optimizer.yaml; "
            "o Pixel Optimizer vai usar o revisor determinístico"
        )
        return PixelReviewer()

    _LOG.info("revisor do Pixel Optimizer: %s", ChatClient(chat).describe())
    return LLMPixelReviewer(
        ChatClient(chat),
        fallback=PixelReviewer(),
        max_attempts=int(config.get("max_attempts", 2)),
    )
