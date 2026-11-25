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
from datetime import timedelta

from .generation.kernel import (
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
from .pedidos import FilaDePedidos, ServicoDePedidos
from .pixel import PixelProfileRegistry, PixelValidator, QualityCalibration
from .pixel.optimizer import AssetFlowPixelOptimizer, PixelReviewer, ReviewLoop
from .pixel_knowledge import BaseDeConhecimento
from .referencias import ReferenciasAtivas
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
    resolver: EngineResolver
    kernel: GenerationKernel
    #: O estágio que toda geração Pixel atravessa (plano Optimizer §33).
    #: Ele não está no ``EngineRegistry`` e nunca estará: não é uma tecnologia
    #: de geração de imagem, é o que corrige a imagem gerada (§79).
    optimizer: AssetFlowPixelOptimizer
    #: O validador Pixel, com os limiares de `config/quality.yaml`. É o mesmo
    #: no pipeline e no laço do Optimizer: "otimizar não pode piorar" só vale
    #: se as duas notas saem da mesma régua.
    pixel_validator: PixelValidator
    profiles: ProfileRegistry
    pixel_profiles: PixelProfileRegistry
    pipelines: PipelineRegistry
    prompt_builders: PromptBuilderRegistry
    taxonomy: AssetTaxonomy
    constraints: ConstraintResolver
    #: A base de conhecimento do desenhista (plano desenhista, Fase 3). Só a
    #: porta MCP a lê, para montar o recorte de ``consultar_pedido``; nenhum
    #: pipeline, gaveta ou validador depende dela.
    conhecimento: BaseDeConhecimento
    #: Os pacotes de referência ativos, já medidos (``data/referencias/``).
    #: Também só a porta MCP lê: a linha ``referências:`` e ``ver_referencia``.
    referencias: ReferenciasAtivas
    storage: AssetStorageService
    records: GenerationRecordRepository
    job_store: JobStore
    job_queue: JobQueue
    jobs: JobManager
    worker: GenerationWorker
    service: GenerationService
    #: A fila de pedidos da tela (Fase B do plano do app), num SQLite que a API
    #: e o servidor MCP dividem. ``pedidos.fila`` é o arquivo.
    pedidos: ServicoDePedidos
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
        # Gaveta de referência (mock) só existe nos testes (Fase A do plano do
        # app). Ela é pulada no **registro**, e não escondida depois: uma
        # gaveta registrada continua resolvível por capacidade e habilitável
        # pela API, e "escondida mas usável" é o que deixava um mock gerar no
        # lugar da desenhista.
        if entry.manifest.catalog.dev_only and not settings.show_mock_engines:
            _LOG.info(
                "gaveta '%s' é de referência (só nos testes) e foi ignorada (APP_ENV=%s)",
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

    # -- Vitrine (plano de motores §6) -----------------------------------
    # Descreve as gavetas, para diagnóstico pela API. Não executa nada.
    catalog = EngineCatalog(registry)

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
    pixel_validator = _pixel_validator(settings)
    optimizer = _pixel_optimizer(settings, pixel_validator)

    # -- Produto: profiles, pipelines, prompts ---------------------------
    profiles = ProfileRegistry.from_config(settings.profiles_config)
    # Profiles Pixel Exact: o contrato do arquivo final (resolução lógica,
    # paleta, alpha, canvas, preview). Vive em YAML pelo mesmo motivo dos
    # outros — trocar a regra não pode exigir alterar código (plano Pixel §64).
    pixel_profiles = PixelProfileRegistry.from_config(settings.pixel_profiles_config)
    pipelines = PipelineRegistry.with_defaults(pixel_profiles, optimizer, pixel_validator)
    prompt_builders = PromptBuilderRegistry.with_defaults()

    # Taxonomia + resolver de restrições: o caminho do texto até o Final
    # Resolved Spec (plano T→J §11 e §15). O vocabulário é configuração, como
    # profiles e contratos Pixel — nenhum termo mora em código.
    taxonomy = AssetTaxonomy.from_directory(settings.asset_taxonomy_dir)
    constraints = ConstraintResolver(AssetTypeClassifier(taxonomy))

    # Base de conhecimento do desenhista: paletas, luz, proporções e moldes,
    # lidos como a taxonomia — YAML, sem código, e diretório ausente não
    # derruba o boot. Arquivo torto é ignorado com aviso, e o aviso fica aqui.
    conhecimento = BaseDeConhecimento.do_diretorio(settings.pixel_knowledge_dir)
    # Referências: só o que já foi medido; nada é medido no boot. Sem pasta ou
    # sem pacote ativo, a coleção vem vazia e a linha do recorte some.
    referencias = ReferenciasAtivas.carregar(settings.referencias_dir, settings.referencias_config)

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

    # -- Fila de pedidos (Fase B do plano do app) --------------------------
    # Nada é aberto aqui: cada operação abre e fecha o SQLite. Um arquivo
    # travado ou danificado vira erro na hora de usar a fila, não no boot.
    fila = FilaDePedidos(
        settings.pedidos_path,
        espera_s=settings.pedidos.espera_s,
        max_tentativas=settings.pedidos.tentativas,
        reserva=timedelta(minutes=settings.pedidos.reserva_min),
    )
    pedidos = ServicoDePedidos(
        fila,
        service,
        storage,
        records,
        projeto=settings.pedidos.projeto_padrao,
        gerador=settings.gerador,
    )

    _LOG.info(
        "AssetFlow pronto [%s]: %s gaveta(s), %s profile(s), "
        "%s profile(s) Pixel, %s pipeline(s), %s vocabulário(s) de asset, "
        "%s molde(s) de desenho, %s quadro(s) de referência | otimização %s",
        settings.app_env.value,
        len(registry),
        len(profiles),
        len(pixel_profiles),
        len(pipelines.ids()),
        len(taxonomy),
        len(conhecimento.moldes),
        len(referencias.quadros),
        "ligada" if optimizer.enabled else "DESLIGADA",
    )

    return AppContainer(
        settings=settings,
        registry=registry,
        catalog=catalog,
        resolver=resolver,
        optimizer=optimizer,
        pixel_validator=pixel_validator,
        kernel=kernel,
        profiles=profiles,
        pixel_profiles=pixel_profiles,
        pipelines=pipelines,
        prompt_builders=prompt_builders,
        taxonomy=taxonomy,
        constraints=constraints,
        conhecimento=conhecimento,
        referencias=referencias,
        storage=storage,
        records=records,
        job_store=job_store,
        job_queue=job_queue,
        jobs=jobs,
        worker=worker,
        service=service,
        pedidos=pedidos,
    )


def _pixel_validator(settings: Settings) -> PixelValidator:
    """O validador Pixel com a calibração de ``config/quality.yaml``.

    Ausente ou vazio, valem os limiares do plano §60, escritos no código — e o
    boot avisa, porque com eles o aviso de blocos pequenos aparece em quase
    todo desenho com detalhe. Número recusado (sem ``a_calibrar`` nem
    ``fonte``, fora da faixa) fica com o do plano e vira aviso aqui.
    """
    if not settings.quality_config:
        _LOG.warning(
            "quality.yaml ausente ou vazio: a nota usa os limiares do plano §60, "
            "sem a calibração pelas referências"
        )
    calibration = QualityCalibration.from_config(settings.quality_config)
    for problem in calibration.problems:
        _LOG.warning("quality.yaml: %s", problem)
    return PixelValidator(calibration=calibration)


def _pixel_optimizer(settings: Settings, validator: PixelValidator) -> AssetFlowPixelOptimizer:
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
            validator=validator,
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
