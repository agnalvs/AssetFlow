"""`gpt-image-v1` — a primeira gaveta remota do AssetFlow.

Ela quebra um padrão de propósito: todas as outras gavetas rodam localmente,
seja carregando um modelo em GPU, seja executando um binário. Esta fala com
uma API. O contrato é o mesmo — recebe ``ImageGenerationRequest``, devolve
``EngineGenerationResult`` —, e é essa igualdade que permite acrescentá-la sem
tocar em kernel, pipeline, pós-processamento ou interface.

O que ela **não** faz, e é o ponto
-----------------------------------
Ela não gera Pixel Art. Ela não pode: o provedor exige no mínimo 655.360
pixels por imagem, e um sprite 32×32 tem 1.024. O que ela entrega é uma
**proposta visual** em ~832×832 — boa composição, boa leitura do pedido, boa
silhueta — e quem transforma isso em asset é o pipeline que já existe::

    GPT Image  ->  PixelPostProcessor  ->  Validator V1
               ->  AssetFlowPixelOptimizer  ->  Validator V2  ->  Aceitação

Essa divisão é a tese inteira: o motor precisa ser bom em *entender o pedido*,
não em *acertar a grade*. A grade é responsabilidade do AssetFlow, e ele a
garante deterministicamente para qualquer motor.

Três capacidades ausentes, todas declaradas
-------------------------------------------
O provedor **não tem seed**, **não tem negative prompt** e o fundo transparente
está em *preview*. Nenhuma das três é escondida: a primeira e a segunda viram
aviso no job, e a terceira está no manifesto. Uma capacidade que falta em
silêncio é pior que uma capacidade que falta.
"""

from __future__ import annotations

import time

from ....generation.kernel.contracts import (
    BaseImageGenerationEngine,
    EngineExecutionContext,
)
from ....generation.kernel.exceptions import EngineExecutionError
from ....generation.schemas import (
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineRef,
    EngineRuntimeConfig,
    ImageArtifact,
    ImageGenerationRequest,
    StageTimings,
)
from .client import GPTImageClient, ImageRequest
from .config import ADAPTER_VERSION, GPTImageConfig
from .prompting import compile_prompt
from .sizing import SizeNotRepresentable, render_size_for

__all__ = ["GPTImageEngine"]

#: Teto de imagens por chamada, do provedor.
MAX_N = 10


class GPTImageEngine(BaseImageGenerationEngine):
    """Ponte para a API de imagens da OpenAI (ou compatível)."""

    def __init__(self) -> None:
        super().__init__()
        self._gpt_config = GPTImageConfig()
        self._client: GPTImageClient | None = None

    # -- Ciclo de vida ---------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        self._gpt_config = GPTImageConfig.from_runtime(config)
        self._client = GPTImageClient(self._gpt_config)
        reason = self._gpt_config.unavailable_reason()
        if reason:
            # Não é erro de inicialização: a gaveta existe e é escolhível, ela
            # só não tem credencial nesta máquina. Quem informa é o health.
            self._logger.warning("gpt-image-v1 indisponível: %s", reason)
        else:
            self._logger.info("gpt-image-v1 pronto: %s", self._client.describe())

    async def on_unload(self) -> None:
        self._client = None

    def _effective_config(self) -> GPTImageConfig:
        """A configuração mesmo antes de ``initialize()``.

        Com ``lazy_load``, o catálogo pergunta a saúde bem antes do primeiro
        job; responder "não configurado" ali sobre uma gaveta configurada é o
        defeito que já trancou as pontes de processo (ver ``lifecycle.py``).
        """
        if self._gpt_config.configured:
            return self._gpt_config
        pending = self.pending_config
        return GPTImageConfig.from_runtime(pending) if pending else self._gpt_config

    async def health_check(self) -> EngineHealth:
        """Confere credencial e configuração — **sem** gastar uma geração.

        Uma chamada de verdade custaria dinheiro a cada abertura da tela, para
        responder algo que a primeira geração responderia de graça.
        """
        config = self._effective_config()
        reason = config.unavailable_reason()
        if reason:
            return EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                gpu_available=False,
                detail=reason,
            )
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=False,
            gpu_available=False,
            detail=f"API remota; modelo {config.model}",
            metrics={"active_jobs": len(self._active_jobs)},
        )

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        config = self._effective_config()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            model_id=config.model,
            provider=manifest.provider,
            adapter_version=ADAPTER_VERSION,
        )

    # -- Execução --------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()
        config = self._effective_config()
        client = self._client or GPTImageClient(config)

        logical = request.output.logical_size
        try:
            render = render_size_for(
                logical, (request.output.width, request.output.height)
            )
        except SizeNotRepresentable as exc:
            raise EngineExecutionError(str(exc), engine_id=manifest.id) from exc

        semantic = request.prompt.semantic
        compiled = compile_prompt(
            positive=request.prompt.positive,
            negative=request.prompt.negative,
            subject=semantic.subject if semantic else "",
            asset_type=request.asset.type.value,
            is_pixel=logical is not None,
            logical=logical,
            max_colors=request.output.max_colors,
            transparent=request.output.transparent,
            view=semantic.view if semantic else None,
            seed_requested=request.generation.seed is not None,
            body_type=request.asset.body_type,
            detail=request.style.detail,
            outline=request.style.outline,
            shading=request.style.shading,
            light_direction=request.style.light_direction,
            reference_count=len(request.reference_images),
        )

        warnings = list(compiled.warnings)
        variations = max(1, request.output.variations)
        if variations > MAX_N:
            warnings.append(
                f"o GPT Image entrega no máximo {MAX_N} imagens por chamada; "
                f"{variations} viraram {MAX_N}"
            )
            variations = MAX_N

        background = "transparent" if request.output.transparent else "auto"
        call = ImageRequest(
            prompt=compiled.text,
            size=render.as_param,
            n=variations,
            quality=config.quality_for(request.generation.quality.value),
            background=background,
            output_format="png",
            moderation=config.moderation,
        )

        context.cancellation.raise_if_cancelled()
        context.report(0.05, "generating", engine_id=manifest.id)

        self._track(context.job_id)
        started = time.perf_counter()
        try:
            images = await client.generate(call)
        finally:
            self._untrack(context.job_id)
        inference_ms = (time.perf_counter() - started) * 1000.0

        # O cancelamento chega depois da resposta porque a chamada HTTP não é
        # interrompível: o que se pode fazer é não gastar o resto do pipeline.
        context.cancellation.raise_if_cancelled()
        context.report(0.95, "generating", engine_id=manifest.id)

        artifacts = tuple(
            ImageArtifact(
                index=index,
                data=data,
                mime_type="image/png",
                width=render.width,
                height=render.height,
                # Sem seed: declarar um número aqui faria o histórico prometer
                # uma reprodutibilidade que não existe.
                seed=None,
                metadata={"renderer": "gpt-image", **render.document()},
            )
            for index, data in enumerate(images)
        )

        return EngineGenerationResult(
            engine=self.engine_ref(),
            artifacts=artifacts,
            timings=StageTimings(inference_ms=inference_ms),
            warnings=tuple(warnings),
            engine_metadata={
                "engine": manifest.id,
                "adapter_version": ADAPTER_VERSION,
                "model": config.model,
                "quality": call.quality,
                "background": background,
                "detail_budget": compiled.budget,
                **render.document(),
                # O texto que de fato gerou o asset. É o que responde "por que
                # saiu isso?" meses depois — o prompt do usuário, sozinho, não.
                "effective_prompt": {
                    "positive": compiled.text,
                    "negative": None,
                },
            },
        )
