"""Asset Pipelines — a lógica de negócio da geração (planos §4, §18, §57, §62).

Diferença crítica que esta camada materializa:

    Engine   sabe  ->  gerar imagem
    Pipeline sabe  ->  gerar asset

O pipeline conhece Pixel Art, personagem, paleta, projeto. Ele **não** conhece
SDXL. Ele pede uma capacidade ao Kernel e recebe imagens normalizadas.

Proibição arquitetural (plano §18): é proibido escrever aqui
``from generation.engines.diffusers_sdxl.engine import SDXLEngine``.
O caminho correto é sempre::

    result = await kernel.execute(request, ...)   # capability routing
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ...storage import AssetStorageService, GenerationRecord, GenerationRecordOutput
from ..kernel.contracts import CancellationToken, NullProgressReporter, ProgressReporter
from ..kernel.service import GenerationKernel
from ..postprocessing import (
    ImageBuffer,
    PostProcessContext,
    PostProcessingChain,
    decode_image,
    encode_png,
)
from ..profiles import GenerationProfile
from ..prompting import PromptBuilderRegistry, render_semantic_prompt
from ..schemas import (
    AssetGenerationRequest,
    AssetSpec,
    AssetVariant,
    EngineSelector,
    GeneratedAsset,
    GenerationParams,
    GenerationResult,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
    SemanticPrompt,
    StageTimings,
    Stopwatch,
    ValidationReport,
)

__all__ = ["PipelineContext", "PipelineOutcome", "AssetPipeline", "ImageAssetPipeline"]

_LOG = logging.getLogger("assetflow.generation.pipelines")


@dataclass(slots=True)
class PipelineContext:
    """Tudo que um pipeline precisa para produzir um asset."""

    job_id: str
    request: AssetGenerationRequest
    profile: GenerationProfile
    kernel: GenerationKernel
    storage: AssetStorageService
    prompt_builders: PromptBuilderRegistry
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    progress: ProgressReporter = field(default_factory=NullProgressReporter)
    logger: logging.Logger = field(default_factory=lambda: _LOG)

    def report(self, progress: float, stage: str = "", **extra: Any) -> None:
        try:
            self.progress(max(0.0, min(1.0, progress)), stage, **extra)
        except Exception:  # pragma: no cover - observabilidade nunca quebra job
            self.logger.debug("progress reporter falhou", exc_info=True)


@dataclass(slots=True)
class PipelineOutcome:
    """Resultado completo de um pipeline."""

    asset: GeneratedAsset
    result: GenerationResult
    timings: StageTimings
    warnings: tuple[str, ...] = ()
    record: GenerationRecord | None = None


class AssetPipeline(ABC):
    """Contrato de um pipeline de produto."""

    id: str = "base"
    display_name: str = "Pipeline"

    @abstractmethod
    async def run(self, context: PipelineContext) -> PipelineOutcome:
        ...


class ImageAssetPipeline(AssetPipeline):
    """Implementação comum a todos os pipelines de imagem.

    Fluxo (plano §57)::

        AssetGenerationRequest
              -> PromptBuilder -> SemanticPrompt
              -> ImageGenerationRequest
              -> Generation Kernel -> EngineResolver -> Engine
              -> Raw Image
              -> PostProcessing (regras do AssetFlow)
              -> Storage
              -> Asset

    Subclasses normalmente só precisam definir ``id`` e
    :meth:`build_postprocessing_chain`.
    """

    #: Cadeia de pós-processamento aplicada às imagens brutas.
    @abstractmethod
    def build_postprocessing_chain(self, context: PipelineContext) -> PostProcessingChain:
        ...

    # ------------------------------------------------------------------
    # Etapas
    # ------------------------------------------------------------------
    def build_semantic_prompt(self, context: PipelineContext) -> SemanticPrompt:
        """Converte o pedido humano em representação semântica (plano §26)."""
        builder = context.prompt_builders.resolve(context.profile)
        return builder.build(context.request, context.profile)

    def build_generation_request(
        self, context: PipelineContext, semantic: SemanticPrompt
    ) -> ImageGenerationRequest:
        """Monta o request universal.

        O texto neutro é gerado aqui; se o motor escolhido tiver um adapter
        próprio, ele reinterpreta o ``semantic`` internamente (plano §27).
        """
        profile = context.profile
        request = context.request
        overrides = request.output

        positive, negative = render_semantic_prompt(semantic)

        width = overrides.render_width or profile.output.render_width
        height = overrides.render_height or profile.output.render_height
        variations = overrides.variations or profile.output.variations
        transparent = (
            overrides.transparent
            if overrides.transparent is not None
            else profile.output.transparent
        )

        engine_options = {**profile.engine_options}
        for engine_id, options in request.engine_options.items():
            engine_options[engine_id] = {**engine_options.get(engine_id, {}), **options}

        return ImageGenerationRequest(
            capability=request.capability or profile.capability,
            asset=AssetSpec(
                type=request.asset_type or profile.asset.type,
                mode=request.mode or profile.asset.mode,
            ),
            prompt=PromptSpec(positive=positive, negative=negative, semantic=semantic),
            output=OutputSpec(
                width=width,
                height=height,
                variations=variations,
                transparent=transparent,
            ),
            generation=GenerationParams(seed=request.seed, quality=request.quality),
            engine=request.engine or EngineSelector(),
            reference_images=request.reference_images,
            structural_controls=request.structural_controls,
            engine_options=engine_options,
            metadata={
                "project_id": request.project_id,
                "profile_id": profile.id,
                "pipeline_id": self.id,
                "job_id": context.job_id,
            },
        )

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def run(self, context: PipelineContext) -> PipelineOutcome:
        profile = context.profile
        request = context.request

        context.report(0.01, "building_prompt")
        semantic = self.build_semantic_prompt(context)
        generation_request = self.build_generation_request(context, semantic)

        context.cancellation.raise_if_cancelled()

        # --- Geração (o único ponto que fala com o Kernel) --------------
        result = await context.kernel.execute(
            generation_request,
            job_id=context.job_id,
            cancellation=context.cancellation,
            progress=context.progress,
        )

        context.cancellation.raise_if_cancelled()

        # --- Pós-processamento + storage --------------------------------
        chain = self.build_postprocessing_chain(context)
        post_context = PostProcessContext(profile=profile, logger=context.logger)

        postprocess_watch = Stopwatch()
        buffers: list[tuple[int, ImageBuffer, bytes]] = []
        total = max(1, len(result.outputs))

        for position, output in enumerate(result.outputs):
            context.cancellation.raise_if_cancelled()
            if output.data is None:  # pragma: no cover - defensivo
                continue

            buffer = await asyncio.to_thread(
                _process_image, output.data, chain, post_context
            )
            buffers.append((output.index, buffer, encode_png(buffer.image)))
            context.report(
                0.9 + 0.05 * ((position + 1) / total),
                "postprocessing",
                engine_id=result.engine.id,
            )
        postprocess_ms = postprocess_watch.elapsed_ms

        storage_watch = Stopwatch()
        variants: list[AssetVariant] = []
        for (index, buffer, data), output in zip(buffers, result.outputs):
            stored = await context.storage.persist_variant(
                project_id=request.project_id,
                job_id=context.job_id,
                index=index,
                data=data,
                thumbnail_scale=profile.postprocessing.thumbnail_scale,
                image=buffer.image,
            )
            variants.append(
                AssetVariant(
                    index=index,
                    uri=stored.uri,
                    thumbnail_uri=stored.thumbnail_uri,
                    width=buffer.image.width,
                    height=buffer.image.height,
                    logical_width=buffer.logical_size[0] if buffer.logical_size else None,
                    logical_height=buffer.logical_size[1] if buffer.logical_size else None,
                    seed=output.seed,
                    color_count=buffer.metadata.get("color_count"),
                    palette=buffer.palette,
                    validation=ValidationReport(issues=tuple(buffer.issues)),
                    metadata={
                        **buffer.metadata,
                        "size_bytes": stored.size_bytes,
                        "render_size": [output.width, output.height],
                    },
                )
            )
        storage_ms = storage_watch.elapsed_ms

        asset = GeneratedAsset(
            project_id=request.project_id,
            job_id=context.job_id,
            type=generation_request.asset.type,
            mode=generation_request.asset.mode,
            name=request.name or semantic.subject[:80],
            profile_id=profile.id,
            pipeline_id=self.id,
            engine=result.engine,
            variants=tuple(variants),
            metadata={
                "capability": str(generation_request.capability),
                "fallback_used": result.fallback_used,
                "user_prompt": request.prompt,
            },
        )
        await context.storage.persist_asset_metadata(asset)

        timings = result.timings.model_copy(
            update={
                "postprocess_ms": postprocess_ms,
                "storage_ms": storage_ms,
                "total_ms": (result.timings.total_ms or 0.0) + postprocess_ms + storage_ms,
            }
        )

        record = await context.storage.record_generation(
            _build_record(
                context=context,
                asset=asset,
                result=result,
                generation_request=generation_request,
                semantic=semantic,
                timings=timings,
            )
        )

        context.report(1.0, "completed", engine_id=result.engine.id)
        return PipelineOutcome(
            asset=asset,
            result=result.without_payloads(),
            timings=timings,
            warnings=result.warnings,
            record=record,
        )


def _process_image(
    data: bytes, chain: PostProcessingChain, context: PostProcessContext
) -> ImageBuffer:
    """Executa a cadeia em thread separada (trabalho de CPU)."""
    buffer = ImageBuffer(image=decode_image(data))
    return chain.run(buffer, context)


def _build_record(
    *,
    context: PipelineContext,
    asset: GeneratedAsset,
    result: GenerationResult,
    generation_request: ImageGenerationRequest,
    semantic: SemanticPrompt,
    timings: StageTimings,
) -> GenerationRecord:
    """Monta o registro persistido da geração (planos §41 e §42)."""
    # O prompt registrado é o que foi *efetivamente* enviado ao motor: se a
    # gaveta tiver um adapter próprio, é o texto no dialeto dela.
    effective = (result.metadata.get("engine_metadata") or {}).get("effective_prompt") or {}
    return GenerationRecord(
        job_id=context.job_id,
        project_id=context.request.project_id,
        user_id=context.request.user_id,
        asset_id=asset.id,
        profile_id=context.profile.id,
        pipeline_id=asset.pipeline_id,
        capability=generation_request.capability,
        fallback_used=result.fallback_used,
        attempted_engines=result.attempted_engines,
        user_prompt=context.request.prompt,
        positive_prompt=effective.get("positive") or generation_request.prompt.positive,
        negative_prompt=effective.get("negative") or generation_request.prompt.negative,
        semantic_prompt=semantic,
        seed=generation_request.generation.seed,
        generation_parameters={
            "quality": generation_request.generation.quality.value,
            "width": generation_request.output.width,
            "height": generation_request.output.height,
            "variations": generation_request.output.variations,
            "transparent": generation_request.output.transparent,
        },
        engine_options=generation_request.engine_options,
        outputs=tuple(
            GenerationRecordOutput(
                index=variant.index,
                uri=variant.uri,
                thumbnail_uri=variant.thumbnail_uri,
                width=variant.width,
                height=variant.height,
                logical_width=variant.logical_width,
                logical_height=variant.logical_height,
                seed=variant.seed,
                color_count=variant.color_count,
                palette=variant.palette,
            )
            for variant in asset.variants
        ),
        timings=timings,
        warnings=result.warnings,
        metadata=result.metadata,
        **GenerationRecord.engine_fields(result.engine),
    )
