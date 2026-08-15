"""`diffusers-sdxl-v1` — a primeira gaveta real (planos §15 e §16).

Importante para a saúde da arquitetura: **este motor é uma implementação de
referência, não o fundamento do AssetFlow.** Ele existe para provar que o
caminho

    AssetFlow → Contract → Plugin → Diffusers → modelo

funciona. Depois dele, trocar por FLUX ou por um modelo especializado de
Pixel Art deve custar uma pasta nova e uma linha de configuração.

Toda menção a Diffusers/torch está confinada a este pacote — e, dentro dele,
a ``loader.py``.
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
    EngineRuntimeConfig,
    ImageGenerationRequest,
)
from .config import SDXLConfig
from .loader import LoadedPipeline, describe_runtime, load_pipeline, release
from .mapper import to_engine_result
from .prompt_adapter import SDXLPromptAdapter

__all__ = ["DiffusersSDXLEngine"]

_MAX_SEED = 2**31 - 1


class DiffusersSDXLEngine(BaseImageGenerationEngine):
    """Gaveta que opera modelos SDXL através da biblioteca Diffusers."""

    def __init__(self) -> None:
        super().__init__()
        self._sdxl_config = SDXLConfig()
        self._loaded: LoadedPipeline | None = None
        self._adapter = SDXLPromptAdapter()
        self._cancelled_jobs: set[str] = set()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        """Carrega o modelo. Chamado no primeiro job, não no boot (§36)."""
        self._sdxl_config = SDXLConfig.from_runtime(config)
        # `load_pipeline` é bloqueante e pesado: nunca no event loop.
        self._loaded = await asyncio.to_thread(load_pipeline, self._sdxl_config)
        self._logger.info(
            "SDXL pronto (modelo=%s, device=%s, dtype=%s)",
            self._sdxl_config.model_id,
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
        status = EngineHealthStatus.HEALTHY if gpu else EngineHealthStatus.DEGRADED
        return EngineHealth(
            status=status,
            model_loaded=self._loaded is not None,
            gpu_available=gpu,
            detail=None if gpu else "sem GPU disponível: a geração será muito lenta",
            metrics={
                key: value
                for key, value in runtime.items()
                if key not in {"available", "detail"}
            },
        )

    async def cancel(self, job_id: str) -> bool:
        self._cancelled_jobs.add(job_id)
        return job_id in self._active_jobs

    def prompt_adapter(self) -> SDXLPromptAdapter:
        return self._adapter

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
                "pipeline SDXL não inicializado", engine_id=manifest.id
            )

        config = self._sdxl_config
        options = request.options_for(manifest.id)

        # O Kernel já aplicou `prompt_adapter()` — o texto que chega aqui está
        # no dialeto do SDXL. Adaptar de novo duplicaria os reforços.
        positive = request.prompt.positive
        negative = request.prompt.negative

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
                negative=negative,
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
                "SDXL não gera canal alpha; o fundo será tratado no pós-processamento"
            )

        return to_engine_result(
            manifest,
            images,
            seeds,
            model_id=config.model_id,
            model_revision=config.revision,
            inference_ms=inference_ms,
            warnings=warnings,
            engine_metadata={
                "steps": steps,
                "guidance_scale": guidance,
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
        negative: str | None,
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

        generators = [
            torch.Generator(device="cpu").manual_seed(seed) for seed in seeds
        ]

        def on_step_end(_pipe: Any, step: int, _timestep: Any, kwargs: dict) -> dict:
            if context.cancellation.is_cancelled or context.job_id in self._cancelled_jobs:
                raise GenerationCancelled("cancelamento solicitado durante a inferência")
            context.report(min(0.95, (step + 1) / max(1, steps)), "generating")
            return kwargs

        try:
            result = pipeline(
                prompt=positive,
                negative_prompt=negative,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=guidance,
                num_images_per_prompt=len(seeds),
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
                f"falha na inferência SDXL: {exc}",
                engine_id=self.manifest().id,
                detail={"device": device, "cause": repr(exc)},
            ) from exc

        return list(result.images)
