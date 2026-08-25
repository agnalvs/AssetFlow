"""`pixel-forge-v1` — sprites 32×32 nativos (plano de motores §8.3 e §14).

O Pixel Forge é uma gaveta **especializada**, e o valor dela está justamente
em não ser genérica: ela gera 32×32 nativamente, que é o tamanho de um item,
de um ícone, de um prop pequeno. Para isso ela tende a ganhar de um modelo de
difusão que pinta em 1024 e depois encolhe.

Fora dessa faixa ela não se apresenta como opção — e é o manifesto que diz
isso, através de ``limits`` e de ``supported_logical_sizes``. O resolver
descarta a gaveta sozinho quando o pedido não cabe (§12); nenhum
``if engine_id == ...`` participa dessa decisão.
"""

from __future__ import annotations

import random
import tempfile
import time
from pathlib import Path

from ....generation.kernel.contracts import (
    BaseImageGenerationEngine,
    EngineExecutionContext,
)
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
from .bridge import binary_available, render_args, run_forge
from .config import ADAPTER_VERSION, NATIVE_SIZE, PixelForgeConfig

__all__ = ["PixelForgeEngine"]

_MAX_SEED = 2**31 - 1


class PixelForgeEngine(BaseImageGenerationEngine):
    """Ponte para o executável local do Pixel Forge."""

    def __init__(self) -> None:
        super().__init__()
        self._forge_config = PixelForgeConfig()

    # ------------------------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        self._forge_config = PixelForgeConfig.from_runtime(config)
        problem = binary_available(
            self._forge_config.binary, self._forge_config.working_dir
        )
        if problem:
            self._logger.warning("Pixel Forge indisponível: %s", problem)

    async def health_check(self) -> EngineHealth:
        problem = binary_available(
            self._forge_config.binary, self._forge_config.working_dir
        )
        if problem:
            return EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                gpu_available=False,
                detail=problem,
            )
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=False,
            gpu_available=False,
            detail=f"binário local; resolução nativa {NATIVE_SIZE}×{NATIVE_SIZE}",
            metrics={"active_jobs": len(self._active_jobs)},
        )

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id=self._forge_config.model_id,
            adapter_version=ADAPTER_VERSION,
        )

    # ------------------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()

        seed = request.generation.seed
        if seed is None:
            seed = random.randint(0, _MAX_SEED)

        # O grid pedido, se houver; senão o nativo. O aviso abaixo cobre o
        # caso em que os dois discordam — a pessoa precisa saber que o sprite
        # nasceu 32×32 e foi o AssetFlow que o levou ao tamanho pedido.
        logical = request.output.logical_size or (NATIVE_SIZE, NATIVE_SIZE)
        warnings: list[str] = []
        if logical != (NATIVE_SIZE, NATIVE_SIZE):
            warnings.append(
                f"Pixel Forge gera em {NATIVE_SIZE}×{NATIVE_SIZE}; o ajuste para "
                f"{logical[0]}×{logical[1]} é feito pelo pós-processamento"
            )

        self._track(context.job_id)
        started = time.perf_counter()
        try:
            images = await self._render(request, context, seed)
        finally:
            self._untrack(context.job_id)

        inference_ms = (time.perf_counter() - started) * 1000.0
        artifacts = tuple(
            ImageArtifact(
                index=index,
                data=data,
                mime_type="image/png",
                width=NATIVE_SIZE,
                height=NATIVE_SIZE,
                seed=(seed + index) % (_MAX_SEED + 1),
                metadata={"renderer": "pixel-forge", "native_size": NATIVE_SIZE},
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
                "native_size": NATIVE_SIZE,
                "quality": request.generation.quality.value,
            },
        )

    # ------------------------------------------------------------------
    async def _render(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
        seed: int,
    ) -> list[bytes]:
        config = self._forge_config
        collected: list[bytes] = []
        total = max(1, request.output.variations)

        for index in range(total):
            context.cancellation.raise_if_cancelled()
            context.report(index / total, "generating", engine_id=self.manifest().id)

            with tempfile.TemporaryDirectory(prefix="assetflow-forge-") as tmp:
                output_dir = Path(config.output_dir or tmp)
                output_dir.mkdir(parents=True, exist_ok=True)
                values = {
                    "prompt": request.prompt.positive,
                    "seed": (seed + index) % (_MAX_SEED + 1),
                    "size": NATIVE_SIZE,
                    "width": NATIVE_SIZE,
                    "height": NATIVE_SIZE,
                    "max_colors": request.output.max_colors or "",
                    "model": config.model_id,
                    "output_dir": str(output_dir),
                    "output": str(output_dir / f"{index:03d}.png"),
                    "workspace": self.config.workspace_dir or tmp,
                }
                command = [config.binary, *render_args(config.args, values)]
                result = await run_forge(
                    command,
                    working_dir=config.working_dir,
                    output_dir=output_dir,
                    output_glob=config.output_glob,
                    timeout_s=config.process_timeout_s,
                    env=config.env,
                    cancellation=context.cancellation,
                )
                collected.append(result.images[0])

        context.report(0.95, "generating", engine_id=self.manifest().id)
        return collected
