"""ModelGenerationStrategy — prompt → motor → imagem (plano de correção §13).

    FinalResolvedSpec
          ↓
    ImageGenerationRequest      o contrato universal
          ↓
    GenerationKernel            resolve o motor, aplica timeout, faz fallback
          ↓
    Engine.generate()           FLUX, SDXL, SD-πXL, Pixel Forge
          ↓
    GenerationResult

Esta estratégia é o caminho que o AssetFlow sempre teve; o que mudou é que
agora ele tem nome. Antes, "gerar com um modelo" era simplesmente o que o
pipeline fazia, e por isso não havia onde encaixar um modo de criação que
*não* fosse esse — o agente de desenho acabou virando um motor por falta de
lugar melhor.

Ela não conhece FLUX, SDXL, SD-πXL nem Pixel Forge. Pede uma capacidade ao
Kernel e recebe imagens normalizadas: a mesma regra de sempre (plano §18).
"""

from __future__ import annotations

import logging

from ..kernel.registry import EngineRegistry
from ..prompting import render_semantic_prompt
from ..schemas import (
    AssetSpec,
    EngineSelector,
    FinalResolvedSpec,
    GenerationParams,
    GenerationResult,
    GenerationStrategyType,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)
from .base import GenerationStrategy, StrategyContext

__all__ = ["ModelGenerationStrategy"]

_LOG = logging.getLogger("assetflow.generation.strategies.model")


class ModelGenerationStrategy(GenerationStrategy):
    """Gera pedindo uma imagem a um motor."""

    strategy_id = GenerationStrategyType.MODEL
    display_name = "Modelo de imagem"
    summary = (
        "Um modelo generativo produz a imagem a partir da descrição. "
        "Rápido para iterar e forte em composição."
    )
    highlights = (
        "melhor leitura do pedido em assets maiores",
        "escolha do motor entre FLUX, SD-πXL, Pixel Forge e SDXL",
        "a exatidão do grid vem do Pixel Exact, depois da geração",
    )

    def __init__(self, registry: EngineRegistry | None = None) -> None:
        # O registry entra só para responder :meth:`available`. Executar
        # continua sendo trabalho do Kernel, que a estratégia recebe por job.
        self._registry = registry

    def supports(self, spec: FinalResolvedSpec) -> bool:
        """Atende qualquer pedido — é o caminho geral do sistema."""
        return True

    async def available(self) -> tuple[bool, str | None]:
        """Disponível enquanto houver ao menos um motor habilitado.

        Sem registry — estratégia montada à mão em teste — a resposta é sim:
        a checagem existe para a vitrine, e um teste que constrói a estratégia
        diretamente não está perguntando sobre o ambiente.
        """
        if self._registry is None:
            return (True, None)
        if any(record.enabled for record in self._registry.list()):
            return (True, None)
        return (False, "nenhum motor de imagem está habilitado nesta instalação")

    async def generate(self, context: StrategyContext) -> GenerationResult:
        request = self.build_request(context)
        context.cancellation.raise_if_cancelled()

        result = await context.kernel.execute(
            request,
            job_id=context.job_id,
            cancellation=context.cancellation,
            progress=context.progress,
        )
        # O Kernel não conhece estratégia — ele conhece capacidade e motor. É
        # aqui, na volta, que o resultado ganha a etiqueta de como foi feito.
        return result.model_copy(update={"strategy": self.strategy_id})

    # ------------------------------------------------------------------
    def build_request(self, context: StrategyContext) -> ImageGenerationRequest:
        """Monta o :class:`ImageGenerationRequest` a partir do contrato.

        Nenhuma linha aqui consulta o profile: os valores já foram resolvidos
        uma vez, com precedência, e reabrir a negociação é como o pedido do
        usuário se perdia (plano T→J §37).
        """
        resolved = context.resolved
        profile = context.profile
        request = context.request

        positive, negative = render_semantic_prompt(context.semantic)
        logical = resolved.logical_resolution
        palette = resolved.palette

        engine_options = {**profile.engine_options}
        for engine_id, options in request.engine_options.items():
            engine_options[engine_id] = {**engine_options.get(engine_id, {}), **options}

        return ImageGenerationRequest(
            capability=resolved.capability,
            asset=AssetSpec(type=resolved.asset.type, mode=resolved.asset.mode),
            prompt=PromptSpec(
                positive=positive, negative=negative, semantic=context.semantic
            ),
            output=OutputSpec(
                width=resolved.render_resolution.width,
                height=resolved.render_resolution.height,
                variations=resolved.generation.variations,
                transparent=resolved.background.transparent,
                # O grid lógico viaja junto para os motores que sabem desenhar
                # nele (SD-πXL, Pixel Forge). Quem não souber ignora.
                logical_width=logical.width if logical else None,
                logical_height=logical.height if logical else None,
                max_colors=palette.max_colors if palette else None,
            ),
            generation=GenerationParams(
                seed=resolved.generation.seed, quality=resolved.generation.quality
            ),
            engine=_selector(resolved),
            reference_images=request.reference_images,
            structural_controls=request.structural_controls,
            engine_options=engine_options,
            metadata={
                "project_id": request.project_id,
                "profile_id": profile.id,
                "pipeline_id": context.metadata.get("pipeline_id", ""),
                "job_id": context.job_id,
                "spec_id": resolved.spec_id,
                "spec_hash": resolved.spec_hash,
                "strategy": self.strategy_id.value,
            },
        )


def _selector(resolved: FinalResolvedSpec) -> EngineSelector:
    """A decisão de motor do spec, no formato que o Kernel entende.

    Em ``auto`` o id vira **dica** e em ``manual`` vira **exigência**. A
    tradução acontece aqui, uma vez, e é o que garante que a diferença entre
    sugerir e exigir sobreviva até o resolver (plano de motores §16 e §25).
    """
    engine = resolved.engine
    if engine.selection_mode == "manual" and engine.engine_id:
        return EngineSelector(
            mode="manual",
            engine_id=engine.engine_id,
            allow_fallback=engine.allow_fallback,
        )
    return EngineSelector(
        mode="auto",
        allow_fallback=engine.allow_fallback,
        preferred_engine_id=engine.engine_id,
    )
