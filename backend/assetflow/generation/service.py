"""Generation Service — a fachada única do sistema de geração (plano §F/§F).

Regra: **nenhuma outra área do AssetFlow chama engines diretamente.**
Projetos, editor, biblioteca, API e futuros clientes conversam apenas com
esta classe.

    generation_service.submit(request)   ->  Job (status=queued)
    generation_service.get_job(job_id)   ->  Job
    generation_service.cancel_job(id)    ->  Job

Ela também é o ponto de leitura sobre a estante (motores, capacidades,
profiles), para que a API não precise conhecer registry nem resolver.
"""

from __future__ import annotations

import logging
from typing import Any

from ..jobs.manager import JobManager
from ..storage import GenerationRecord, GenerationRecordRepository
from .kernel.capabilities import CATALOG, CapabilityCatalog
from .kernel.exceptions import InvalidGenerationRequest, ProfileNotFound
from .kernel.registry import EngineRegistry
from .kernel.resolver import EngineResolver
from .kernel.service import GenerationKernel
from .pipelines import PipelineRegistry
from .profiles import GenerationProfile, ProfileOutput, ProfileRegistry
from .prompting import (
    PromptBuilderRegistry,
    render_semantic_prompt,
    resolve_semantic_prompt,
)
from .schemas import (
    AssetGenerationRequest,
    AssetSpec,
    Capability,
    EngineDescriptor,
    EngineHealth,
    FinalResolvedSpec,
    Job,
    JobStatus,
    PromptPreview,
)
from .spec import ConstraintResolver, SpecResolution

__all__ = ["GenerationService"]

_LOG = logging.getLogger("assetflow.generation.service")


class GenerationService:
    """Ponto de entrada de tudo que envolve geração."""

    def __init__(
        self,
        *,
        kernel: GenerationKernel,
        jobs: JobManager,
        profiles: ProfileRegistry,
        pipelines: PipelineRegistry,
        prompt_builders: PromptBuilderRegistry | None = None,
        constraints: ConstraintResolver | None = None,
        records: GenerationRecordRepository | None = None,
        catalog: CapabilityCatalog = CATALOG,
        default_max_attempts: int = 2,
    ) -> None:
        self._kernel = kernel
        self._jobs = jobs
        self._profiles = profiles
        self._pipelines = pipelines
        # Os mesmos builders que o worker usa. Se a fachada montasse os seus,
        # a pré-visualização poderia responder com uma leitura que a geração
        # nunca faria — e a tela mentiria com toda a boa-fé.
        self._prompt_builders = prompt_builders or PromptBuilderRegistry.with_defaults()
        # O mesmo resolver que o worker usa, pelo mesmo motivo dos builders:
        # se a fachada montasse o seu, a tela poderia mostrar um spec que a
        # geração nunca executaria — e o painel passaria a mentir com boa-fé.
        self._constraints = constraints or ConstraintResolver()
        self._records = records
        self._catalog = catalog
        self._default_max_attempts = default_max_attempts

    # ------------------------------------------------------------------
    # Submissão de jobs
    # ------------------------------------------------------------------
    async def submit(self, request: AssetGenerationRequest) -> Job:
        """Cria e enfileira um job. Retorna imediatamente (plano §53)."""
        profile = self.resolve_profile(request)
        capability = request.capability or profile.capability
        pipeline_id = request.pipeline or profile.pipeline

        # Falha cedo: pipeline inexistente é erro determinístico.
        self._pipelines.get(pipeline_id)

        if not request.prompt.strip():
            raise InvalidGenerationRequest("o pedido precisa de uma descrição (prompt)")

        # O contrato é resolvido AQUI, uma vez, e viaja com o job (plano T→J
        # §15 e §33). O worker não reinterpreta nada: ele recebe o mesmo
        # objeto que a pré-visualização mostrou. É essa identidade que
        # sustenta a promessa "o JSON exibido é o JSON executado".
        resolved = self.resolve_spec(request, profile=profile, pipeline_id=pipeline_id)

        job = Job(
            project_id=request.project_id,
            user_id=request.user_id,
            pipeline_id=pipeline_id,
            profile_id=profile.id,
            capability=capability,
            request=request,
            max_attempts=self._default_max_attempts,
            resolved_spec=resolved,
            queue=self._jobs.router.route(capability),
            metadata={
                "profile_display_name": profile.display_name,
                "spec_id": resolved.spec_id,
                "spec_hash": resolved.spec_hash,
            },
        )
        return await self._jobs.submit(job)

    def preview_prompt(self, request: AssetGenerationRequest) -> PromptPreview:
        """O que este pedido viraria, sem gerar nada (plano §26 e §28).

        Mesmo corpo do ``POST /jobs``, mesma resolução de profile, mesmo
        builder — só que para até a semântica e não chama o Kernel. É o que
        permite discordar da leitura antes de gastar GPU com ela.

        Diferente do ``submit``, aqui uma descrição vazia não é erro: a tela
        pede a pré-visualização enquanto a pessoa digita, e recusar o pedido
        pela metade transformaria cada tecla em uma mensagem de erro.
        """
        profile = self.resolve_profile(request)
        resolved = self.resolve_spec(request, profile=profile)
        semantic = resolve_semantic_prompt(
            request,
            resolved,
            self._prompt_builders,
            prompt_builder=profile.prompt_builder,
        )
        positive, negative = render_semantic_prompt(semantic)
        return PromptPreview(
            profile=profile.id,
            capability=str(resolved.capability),
            resolved=resolved,
            semantic=semantic,
            positive=positive,
            negative=negative,
            source="request" if request.semantic_prompt is not None else "builder",
        )

    def resolve_spec(
        self,
        request: AssetGenerationRequest,
        *,
        profile: GenerationProfile | None = None,
        pipeline_id: str | None = None,
    ) -> FinalResolvedSpec:
        """O Final Resolved Spec deste pedido (plano T→J §15).

        Ponto único de resolução do sistema. Pré-visualização e submissão
        chamam esta função, e o worker recebe o resultado pronto dentro do
        job — ninguém resolve duas vezes, e por isso ninguém pode divergir.
        """
        return self.resolve_full_spec(
            request, profile=profile, pipeline_id=pipeline_id
        ).spec

    def resolve_full_spec(
        self,
        request: AssetGenerationRequest,
        *,
        profile: GenerationProfile | None = None,
        pipeline_id: str | None = None,
    ) -> SpecResolution:
        """Como :meth:`resolve_spec`, mas com a classificação e as restrições.

        Serve ao diagnóstico: mostra qual termo do vocabulário decidiu o tipo
        e quais trechos da descrição foram lidos como restrição exata.
        """
        profile = profile or self.resolve_profile(request)
        return self._constraints.resolve(request, profile, pipeline_id=pipeline_id)

    def resolve_profile(self, request: AssetGenerationRequest) -> GenerationProfile:
        """Descobre o profile do pedido.

        Caminho normal: o pedido traz ``profile``. Caminho avançado: traz
        ``capability`` (+ ``pipeline``) e o serviço monta um profile ad hoc,
        determinístico e reutilizável entre pedidos equivalentes.
        """
        if request.profile:
            return self._profiles.get(request.profile)

        if not request.capability:
            raise ProfileNotFound(
                "informe 'profile' ou 'capability' no pedido",
                detail={"available_profiles": list(self._profiles.ids())},
            )

        capability = Capability.parse(request.capability)
        pipeline_id = request.pipeline or _default_pipeline_for(capability)
        profile_id = f"adhoc:{capability}:{pipeline_id}"

        existing = self._profiles.find(profile_id)
        if existing is not None:
            return existing

        overrides = request.output
        profile = GenerationProfile(
            id=profile_id,
            display_name=f"Ad hoc — {capability}",
            capability=capability,
            pipeline=pipeline_id,
            asset=AssetSpec(
                type=request.asset_type or AssetSpec().type,
                mode=request.mode or AssetSpec().mode,
            ),
            output=ProfileOutput(
                logical_width=overrides.logical_width,
                logical_height=overrides.logical_height,
                render_width=overrides.render_width or 512,
                render_height=overrides.render_height or 512,
                variations=overrides.variations or 1,
                transparent=bool(overrides.transparent),
            ),
            metadata={"ad_hoc": True},
        )
        return self._profiles.register(profile)

    # ------------------------------------------------------------------
    # Consulta de jobs
    # ------------------------------------------------------------------
    async def get_job(self, job_id: str) -> Job:
        return await self._jobs.get(job_id)

    async def list_jobs(
        self,
        *,
        project_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return await self._jobs.list(
            project_id=project_id, status=status, limit=limit, offset=offset
        )

    async def cancel_job(self, job_id: str) -> Job:
        """Solicita cancelamento (plano §46)."""
        return await self._jobs.request_cancel(job_id)

    # ------------------------------------------------------------------
    # Leitura da estante
    # ------------------------------------------------------------------
    @property
    def registry(self) -> EngineRegistry:
        return self._kernel.registry

    @property
    def resolver(self) -> EngineResolver:
        return self._kernel.resolver

    async def list_engines(self, *, include_health: bool = True) -> list[EngineDescriptor]:
        return await self._kernel.registry.describe_all(include_health=include_health)

    async def get_engine(self, engine_id: str) -> EngineDescriptor:
        return await self._kernel.registry.describe(engine_id)

    async def engine_health(self, *, force: bool = False) -> dict[str, EngineHealth]:
        return await self._kernel.registry.health(force=force)

    def enable_engine(self, engine_id: str) -> None:
        """Liga uma gaveta em runtime (base do Swap Engine Test — §67)."""
        self._kernel.registry.enable(engine_id)

    def disable_engine(self, engine_id: str) -> None:
        self._kernel.registry.disable(engine_id)

    async def reload_engine(self, engine_id: str) -> None:
        await self._kernel.registry.reload(engine_id)

    def capabilities(self) -> list[dict[str, Any]]:
        """Capacidades conhecidas + quem as atende hoje.

        É esta lista que o frontend consome — em nenhum momento ele vê o nome
        de uma tecnologia de IA.
        """
        by_engine = self._kernel.registry.capabilities()
        routing = self._kernel.resolver.policy

        seen: dict[Capability, dict[str, Any]] = {}
        for info in self._catalog.all():
            seen[info.capability] = _capability_payload(
                info.capability,
                description=info.description,
                mode=info.mode.value if info.mode else None,
                experimental=info.experimental,
                engines=by_engine.get(info.capability, ()),
                preferred=routing.preferred_for(info.capability),
            )

        # Capacidades declaradas por motores mas ainda não catalogadas.
        for capability, engines in by_engine.items():
            if capability in seen:
                continue
            seen[capability] = _capability_payload(
                capability,
                description="Capacidade declarada por um motor, ainda não catalogada.",
                mode=None,
                experimental=True,
                engines=engines,
                preferred=routing.preferred_for(capability),
            )

        return [seen[key] for key in sorted(seen, key=str)]

    def profiles(self) -> list[GenerationProfile]:
        return [profile for profile in self._profiles.list() if not profile.id.startswith("adhoc:")]

    def pipelines(self) -> tuple[str, ...]:
        return self._pipelines.ids()

    # ------------------------------------------------------------------
    # Histórico
    # ------------------------------------------------------------------
    async def history(
        self, *, project_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[GenerationRecord]:
        if self._records is None:
            return []
        return await self._records.list(project_id=project_id, limit=limit, offset=offset)


def _capability_payload(
    capability: Capability,
    *,
    description: str,
    mode: str | None,
    experimental: bool,
    engines: tuple[str, ...],
    preferred: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "capability": str(capability),
        "family": capability.family,
        "variant": capability.variant,
        "description": description,
        "mode": mode,
        "experimental": experimental,
        "available": bool(engines),
        "engines": list(engines),
        "preferred_order": list(preferred),
    }


def _default_pipeline_for(capability: Capability) -> str:
    """Pipeline padrão quando o pedido não indica um."""
    if capability.variant == "pixel":
        return "pixel.character"
    if capability.family in {"text_to_image", "character", "prop", "background"}:
        return "studio.character"
    return "raw.image"
