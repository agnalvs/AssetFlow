"""`flux-pixel-v1` — FLUX.2-klein-4B + LoRA de Pixel Art (plano de motores §8.1 e §12).

O que esta gaveta promete, e o que ela não promete
--------------------------------------------------
Ela entrega a **base visual**: composição, silhueta, cor, leitura do pedido.
Ela **não** promete exatidão técnica — grid lógico, alpha binário, contagem de
cores. Isso continua sendo do Pixel Exact, depois dela, e é o plano de motores §8.1 que
diz isso com todas as letras. Um motor de difusão que jurasse entregar 32×32
com 16 cores estaria mentindo: ele pinta em 1024 px e não sabe o que é um
pixel lógico.

Toda menção a FLUX/diffusers/torch está confinada a este pacote — e, dentro
dele, a ``loader.py``.
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from ....generation.kernel.contracts import (
    BaseImageGenerationEngine,
    EngineExecutionContext,
)
from ....generation.kernel.exceptions import (
    EngineExecutionError,
    EngineOutOfMemoryError,
    GenerationCancelled,
)
from ....generation.schemas import (
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineRef,
    EngineRuntimeConfig,
    ImageGenerationRequest,
)
from .config import ADAPTER_VERSION, FluxPixelConfig
from .loader import LoadedFluxPipeline, describe_runtime, load_pipeline, release
from .mapper import engine_ref, to_engine_result
from .prompt_adapter import FluxPixelPromptAdapter

__all__ = ["FluxPixelEngine"]

_MAX_SEED = 2**31 - 1


class FluxPixelEngine(BaseImageGenerationEngine):
    """Gaveta que opera FLUX através da biblioteca Diffusers."""

    def __init__(self) -> None:
        super().__init__()
        self._flux_config = FluxPixelConfig()
        self._loaded: LoadedFluxPipeline | None = None
        self._adapter = FluxPixelPromptAdapter(self._flux_config.lora_trigger)
        self._cancelled_jobs: set[str] = set()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        """Carrega o modelo. Chamado no primeiro job, não no boot (§36)."""
        self._flux_config = FluxPixelConfig.from_runtime(config)
        # O gatilho da LoRA é configuração, então o adapter só pode ser
        # montado depois de ler a configuração — não no `__init__`.
        self._adapter = FluxPixelPromptAdapter(self._flux_config.lora_trigger)
        self._loaded = await asyncio.to_thread(load_pipeline, self._flux_config)
        self._logger.info(
            "FLUX pronto (modelo=%s, lora=%s, device=%s, dtype=%s)",
            self._flux_config.model_id,
            self._loaded.lora_id or "nenhuma",
            self._loaded.device,
            self._loaded.dtype,
        )

    async def on_unload(self) -> None:
        await asyncio.to_thread(release, self._loaded)
        self._loaded = None
        self._cancelled_jobs.clear()

    async def health_check(self) -> EngineHealth:
        """Diagnostica sem carregar o modelo (plano §43)."""
        runtime = describe_runtime()
        if not runtime.get("available"):
            return EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                gpu_available=False,
                detail=runtime.get("detail"),
            )

        gpu = bool(runtime.get("gpu_available"))
        detail: str | None = None
        status = EngineHealthStatus.HEALTHY
        if not gpu:
            status = EngineHealthStatus.DEGRADED
            detail = "sem GPU disponível: a geração será muito lenta"
        elif self._loaded is not None and self._loaded.lora_error:
            # O motor funciona, mas não é o motor que a pessoa escolheu: sem
            # a LoRA de Pixel Art, "FLUX Pixel" é só FLUX. Degradado é
            # exatamente o estado certo para isso.
            status = EngineHealthStatus.DEGRADED
            detail = self._loaded.lora_error

        return EngineHealth(
            status=status,
            model_loaded=self._loaded is not None,
            gpu_available=gpu,
            detail=detail,
            metrics={
                key: value
                for key, value in runtime.items()
                if key not in {"available", "detail"}
            },
        )

    async def cancel(self, job_id: str) -> bool:
        self._cancelled_jobs.add(job_id)
        return job_id in self._active_jobs

    def prompt_adapter(self) -> FluxPixelPromptAdapter:
        return self._adapter

    def engine_ref(self) -> EngineRef:
        return engine_ref(
            self.manifest(),
            model_id=self._flux_config.model_id,
            model_revision=self._flux_config.revision,
            lora_id=self._loaded.lora_id if self._loaded else self._flux_config.lora_id,
        )

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()
        if self._loaded is None:
            raise EngineExecutionError(
                "pipeline FLUX não inicializado", engine_id=manifest.id
            )

        config = self._flux_config
        options = request.options_for(manifest.id)

        # O Kernel já aplicou `prompt_adapter()`: o texto que chega aqui está
        # no dialeto do FLUX, com o gatilho da LoRA na frente.
        positive = request.prompt.positive

        steps = int(options.get("steps", config.steps_for(request.generation.quality)))
        guidance = float(options.get("guidance", config.guidance_scale))

        base_seed = request.generation.seed
        if base_seed is None:
            base_seed = random.randint(0, _MAX_SEED)
        seeds = [
            (base_seed + index) % (_MAX_SEED + 1)
            for index in range(request.output.variations)
        ]

        self._track(context.job_id)
        started = time.perf_counter()
        try:
            images = await asyncio.to_thread(
                self._run_pipeline,
                positive=positive,
                width=request.output.width,
                height=request.output.height,
                steps=steps,
                guidance=guidance,
                seeds=seeds,
                context=context,
            )
        finally:
            self._untrack(context.job_id)
            self._cancelled_jobs.discard(context.job_id)

        inference_ms = (time.perf_counter() - started) * 1000.0

        warnings: list[str] = []
        if request.output.transparent:
            warnings.append(
                "FLUX não gera canal alpha; o fundo será tratado no pós-processamento"
            )
        if self._loaded.lora_error:
            warnings.append(self._loaded.lora_error)
        if request.output.logical_size:
            # Honestidade sobre a divisão de trabalho do §8.1: o motor recebeu
            # o grid lógico no request, mas não desenha nele.
            warnings.append(
                "FLUX pinta em alta resolução; a redução ao grid lógico é do "
                "pós-processamento do AssetFlow"
            )

        return to_engine_result(
            manifest,
            images,
            seeds,
            model_id=config.model_id,
            model_revision=config.revision,
            lora_id=self._loaded.lora_id,
            inference_ms=inference_ms,
            warnings=warnings,
            engine_metadata={
                "steps": steps,
                "guidance_scale": guidance,
                "lora_scale": config.lora_scale if self._loaded.lora_id else None,
                "device": self._loaded.device,
                "dtype": self._loaded.dtype,
                "offloaded": self._loaded.offloaded,
                "quality": request.generation.quality.value,
            },
        )

    # ------------------------------------------------------------------
    def _run_pipeline(
        self,
        *,
        positive: str,
        width: int,
        height: int,
        steps: int,
        guidance: float,
        seeds: list[int],
        context: EngineExecutionContext,
    ) -> list[Any]:
        """Executa a inferência (bloqueante, roda em thread separada).

        Traduz as exceções da tecnologia para o vocabulário de erros do
        AssetFlow — nenhuma camada acima conhece ``torch.cuda.OutOfMemoryError``.
        """
        import torch

        assert self._loaded is not None
        pipeline = self._loaded.pipeline
        device = self._loaded.device

        generators = [torch.Generator(device="cpu").manual_seed(seed) for seed in seeds]

        def on_step_end(_pipe: Any, step: int, _timestep: Any, kwargs: dict) -> dict:
            if context.cancellation.is_cancelled or context.job_id in self._cancelled_jobs:
                raise GenerationCancelled("cancelamento solicitado durante a inferência")
            context.report(min(0.95, (step + 1) / max(1, steps)), "generating")
            return kwargs

        try:
            result = pipeline(
                prompt=positive,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=guidance,
                num_images_per_prompt=len(seeds),
                max_sequence_length=self._flux_config.max_sequence_length,
                generator=generators,
                callback_on_step_end=on_step_end,
            )
        except GenerationCancelled:
            raise
        except torch.cuda.OutOfMemoryError as exc:  # pragma: no cover - depende de GPU
            torch.cuda.empty_cache()
            raise EngineOutOfMemoryError(
                "VRAM insuficiente para este lote", engine_id=self.manifest().id
            ) from exc
        except Exception as exc:
            message = str(exc).lower()
            if "out of memory" in message:  # pragma: no cover - depende de GPU
                raise EngineOutOfMemoryError(
                    "memória insuficiente durante a inferência",
                    engine_id=self.manifest().id,
                ) from exc
            raise EngineExecutionError(
                f"falha na inferência FLUX: {exc}",
                engine_id=self.manifest().id,
                detail={
                    "device": device,
                    "adapter_version": ADAPTER_VERSION,
                    "cause": repr(exc),
                },
            ) from exc

        return list(result.images)
