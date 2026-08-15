"""`mock-image-v1` — a primeira gaveta (plano §69).

Ela existe para provar que a estante funciona **antes** de qualquer GPU
entrar na história: API → Job → Resolver → Engine → Storage → Result.

Se algo estiver errado aqui, o problema é arquitetural. Se algo estiver
errado no engine de Diffusers e certo aqui, o problema é de IA. Essa
separação de diagnóstico é o motivo de esta gaveta existir.
"""

from __future__ import annotations

import asyncio
import random
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
    EngineRuntimeConfig,
    ImageGenerationRequest,
)
from .config import MockImageConfig
from .mapper import NativeRender, to_engine_result
from .renderer import render_placeholder

__all__ = ["MockImageEngine"]

_MAX_SEED = 2**31 - 1


class MockImageEngine(BaseImageGenerationEngine):
    """Gaveta determinística de referência, sem dependência de IA."""

    def __init__(self) -> None:
        super().__init__()
        self._mock_config = MockImageConfig()

    # -- Ciclo de vida ---------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        self._mock_config = MockImageConfig.from_runtime(config)
        self._logger.info(
            "mock-image-v1 inicializado (latência simulada=%sms, paleta=%s)",
            self._mock_config.simulated_latency_ms,
            self._mock_config.palette,
        )

    async def on_unload(self) -> None:
        self._mock_config = MockImageConfig()

    async def health_check(self) -> EngineHealth:
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=self.is_initialized,
            gpu_available=False,
            detail="gaveta mock sempre disponível",
            metrics={"active_jobs": len(self._active_jobs)},
        )

    # -- Execução --------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()
        config = self._mock_config
        options = request.options_for(manifest.id)

        # `fail_always` também é aceito por request para exercitar o fallback
        # automático do kernel sem precisar reconfigurar o motor.
        if bool(options.get("fail_always", config.fail_always)):
            raise EngineExecutionError(
                "falha simulada por configuração (fail_always)", engine_id=manifest.id
            )

        latency_ms = float(options.get("simulated_latency_ms", config.simulated_latency_ms))
        palette = str(options.get("palette", config.palette))

        base_seed = request.generation.seed
        if base_seed is None:
            base_seed = random.randint(0, _MAX_SEED)

        variations = request.output.variations
        label = str(request.capability)
        renders: list[NativeRender] = []
        started = time.perf_counter()

        self._track(context.job_id)
        try:
            for index in range(variations):
                context.cancellation.raise_if_cancelled()

                if latency_ms > 0:
                    await asyncio.sleep(latency_ms / 1000.0)

                seed = (
                    (base_seed + index) % (_MAX_SEED + 1)
                    if request.generation.deterministic_variations
                    else random.randint(0, _MAX_SEED)
                )
                data = render_placeholder(
                    width=request.output.width,
                    height=request.output.height,
                    seed=seed,
                    label=label,
                    palette=palette,
                    transparent=request.output.transparent,
                    watermark=config.watermark,
                )
                renders.append(
                    NativeRender(
                        data=data,
                        width=request.output.width,
                        height=request.output.height,
                        seed=seed,
                    )
                )
                context.report(
                    (index + 1) / variations, "generating", engine_id=manifest.id
                )
        finally:
            self._untrack(context.job_id)

        inference_ms = (time.perf_counter() - started) * 1000.0
        return to_engine_result(
            manifest,
            renders,
            inference_ms=inference_ms,
            engine_metadata={
                "palette": palette,
                "quality": request.generation.quality.value,
                "prompt_chars": len(request.prompt.positive),
                "device": "cpu",
            },
        )
