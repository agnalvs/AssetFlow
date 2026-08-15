"""Uma gaveta escrita "de fora", registrada programaticamente.

Este teste é a prova prática da promessa arquitetural: alguém pode escrever um
motor novo, com tecnologia própria, e encaixá-lo na estante **sem alterar uma
linha do AssetFlow**. Ele também exercita o Prompt Adapter específico de motor
(plano §27), aplicado pelo Kernel.
"""

from __future__ import annotations

import io

from PIL import Image

from assetflow.generation.kernel import (
    EngineRegistry,
    EngineResolver,
    GenerationKernel,
    ImageGenerationEngine,
    RoutingPolicy,
)
from assetflow.generation.kernel.contracts import EngineExecutionContext
from assetflow.generation.schemas import (
    Capability,
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineManifest,
    EngineRef,
    EngineRuntimeConfig,
    ImageArtifact,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
    SemanticPrompt,
    StageTimings,
)

from tests.conftest import run

PIXEL = Capability.parse("text_to_image.pixel")

MANIFEST = EngineManifest(
    id="terceiro-motor-v1",
    name="Motor de Terceiro",
    version="0.1.0",
    engine_api_version="1",
    provider="remote_api",
    entrypoint="assetflow.generation.engines.terceiro:Motor",
    capabilities=(PIXEL,),
    supports={"seed": True, "negative_prompt": True, "cancellation": True},
    limits={"min_width": 8, "max_width": 512, "max_height": 512, "max_variations": 2},
)


class _ShoutingPromptAdapter:
    """Adapter fictício: este motor "responde melhor" a prompts em caixa alta."""

    def adapt(self, request: ImageGenerationRequest) -> tuple[str, str | None]:
        semantic = request.prompt.semantic
        subject = semantic.subject if semantic else request.prompt.positive
        return f"{subject.upper()}!!", "LOWERCASE"


class TerceiroMotor(ImageGenerationEngine):
    """Implementa a ABC crua — sem herdar nenhuma conveniência do AssetFlow."""

    def __init__(self) -> None:
        self.received_prompts: list[tuple[str, str | None]] = []
        self.initialized = False

    def manifest(self) -> EngineManifest:
        return MANIFEST

    def capabilities(self):
        return MANIFEST.capabilities

    async def initialize(self, config: EngineRuntimeConfig) -> None:
        self.initialized = True

    async def unload(self) -> None:
        self.initialized = False

    async def health_check(self) -> EngineHealth:
        return EngineHealth(status=EngineHealthStatus.HEALTHY, model_loaded=self.initialized)

    async def cancel(self, job_id: str) -> bool:
        return False

    def prompt_adapter(self) -> _ShoutingPromptAdapter:
        return _ShoutingPromptAdapter()

    async def generate(
        self, request: ImageGenerationRequest, context: EngineExecutionContext
    ) -> EngineGenerationResult:
        self.received_prompts.append((request.prompt.positive, request.prompt.negative))

        artifacts = []
        for index in range(request.output.variations):
            buffer = io.BytesIO()
            Image.new(
                "RGBA",
                (request.output.width, request.output.height),
                (200, 30, 90, 255),
            ).save(buffer, format="PNG")
            artifacts.append(
                ImageArtifact(
                    index=index,
                    data=buffer.getvalue(),
                    width=request.output.width,
                    height=request.output.height,
                    seed=(request.generation.seed or 0) + index,
                )
            )

        return EngineGenerationResult(
            engine=EngineRef(id=MANIFEST.id, version=MANIFEST.version, model_id="api://terceiro"),
            artifacts=tuple(artifacts),
            timings=StageTimings(inference_ms=1.0),
        )


def _kernel() -> tuple[GenerationKernel, TerceiroMotor]:
    engine = TerceiroMotor()
    registry = EngineRegistry()
    registry.register(
        MANIFEST,
        lambda: engine,  # factory: qualquer callable serve
        EngineRuntimeConfig(engine_id=MANIFEST.id, enabled=True),
    )
    resolver = EngineResolver(registry, RoutingPolicy(routing={PIXEL: (MANIFEST.id,)}))
    return GenerationKernel(registry, resolver), engine


def _request(**overrides) -> ImageGenerationRequest:
    payload = {
        "capability": PIXEL,
        "prompt": PromptSpec(
            positive="young warrior",
            semantic=SemanticPrompt(subject="young warrior", medium="pixel_art"),
        ),
        "output": OutputSpec(width=128, height=128, variations=1),
        "generation": {"seed": 5},
    }
    payload.update(overrides)
    return ImageGenerationRequest(**payload)


def test_third_party_engine_works_without_touching_assetflow():
    kernel, engine = _kernel()
    result = run(kernel.execute(_request(), job_id="job_terceiro"))

    assert engine.initialized is True
    assert result.engine.id == "terceiro-motor-v1"
    assert result.outputs[0].width == 128
    assert result.status.value == "completed"


def test_kernel_applies_the_engine_prompt_adapter():
    """Plano §27: cada motor recebe o prompt no formato que entende."""
    kernel, engine = _kernel()
    result = run(kernel.execute(_request(), job_id="job_adapter"))

    positive, negative = engine.received_prompts[0]
    assert positive == "YOUNG WARRIOR!!"
    assert negative == "LOWERCASE"

    # O prompt efetivamente enviado fica registrado para reprodutibilidade.
    effective = result.metadata["engine_metadata"]["effective_prompt"]
    assert effective["positive"] == "YOUNG WARRIOR!!"


def test_semantic_prompt_survives_the_adaptation():
    """A semântica é do AssetFlow; o dialeto é do motor."""
    kernel, engine = _kernel()
    request = _request()
    run(kernel.execute(request, job_id="job_semantic"))

    # O request original não é mutado: a troca de motor parte sempre da
    # mesma representação semântica.
    assert request.prompt.positive == "young warrior"
    assert request.prompt.semantic.subject == "young warrior"


def test_batching_applies_to_third_party_limits():
    kernel, engine = _kernel()
    result = run(
        kernel.execute(
            _request(output=OutputSpec(width=128, height=128, variations=5)),
            job_id="job_lotes",
        )
    )
    # max_variations=2 -> lotes [2, 2, 1]
    assert len(result.outputs) == 5
    assert len(engine.received_prompts) == 3
