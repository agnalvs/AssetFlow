"""`mock-pixel-alt-v1` — a gaveta que prova a substituição (plano §67/§68).

Esta implementação foi escrita **do zero**, implementando diretamente a ABC
:class:`ImageGenerationEngine`, sem herdar de ``BaseImageGenerationEngine`` e
sem reaproveitar uma linha da gaveta `mock-image-v1`.

Isso é proposital: demonstra que o Engine Contract, sozinho, basta para
encaixar uma tecnologia completamente diferente na estante. O
`PixelCharacterPipeline` roda igual nas duas — é exatamente o que o
"Definition of Done arquitetural" exige.
"""

from __future__ import annotations

import asyncio
import io
import json
import random
import time
from pathlib import Path

from PIL import Image

from ....generation.kernel.contracts import (
    EngineExecutionContext,
    ImageGenerationEngine,
)
from ....generation.kernel.exceptions import EngineExecutionError
from ....generation.schemas import (
    Capability,
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineManifest,
    EngineRef,
    EngineRuntimeConfig,
    ImageArtifact,
    ImageGenerationRequest,
    StageTimings,
)

__all__ = ["MockPixelAltEngine"]

_MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
_MAX_SEED = 2**31 - 1

#: Resolução interna do sprite antes do upscale para o tamanho pedido.
_SPRITE_GRID = 16


class MockPixelAltEngine(ImageGenerationEngine):
    """Gerador procedural de sprites simétricos."""

    _manifest: EngineManifest | None = None

    def __init__(self) -> None:
        self._config: EngineRuntimeConfig | None = None
        self._ready = False
        self._active: set[str] = set()
        self._symmetry = True
        self._latency_ms = 0.0

    # -- Descoberta ------------------------------------------------------
    def manifest(self) -> EngineManifest:
        if type(self)._manifest is None:
            with _MANIFEST_PATH.open("r", encoding="utf-8") as handle:
                type(self)._manifest = EngineManifest.model_validate(json.load(handle))
        return type(self)._manifest  # type: ignore[return-value]

    def capabilities(self) -> tuple[Capability, ...]:
        return self.manifest().capabilities

    # -- Ciclo de vida ---------------------------------------------------
    async def initialize(self, config: EngineRuntimeConfig) -> None:
        self._config = config
        options = config.options or {}
        self._symmetry = bool(options.get("symmetry", True))
        self._latency_ms = float(options.get("simulated_latency_ms", 0.0))
        self._ready = True

    async def unload(self) -> None:
        self._ready = False
        self._active.clear()

    async def health_check(self) -> EngineHealth:
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=self._ready,
            gpu_available=False,
            detail="gerador procedural de sprites",
            metrics={"active_jobs": len(self._active)},
        )

    async def cancel(self, job_id: str) -> bool:
        return job_id in self._active

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id="procedural://symmetric-sprite",
            model_revision=manifest.version,
        )

    # -- Execução --------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()
        if not self._ready:
            raise EngineExecutionError(
                "gaveta usada antes de initialize()", engine_id=manifest.id
            )

        options = request.options_for(manifest.id)
        symmetry = bool(options.get("symmetry", self._symmetry))
        latency_ms = float(options.get("simulated_latency_ms", self._latency_ms))

        base_seed = request.generation.seed
        if base_seed is None:
            base_seed = random.randint(0, _MAX_SEED)

        artifacts: list[ImageArtifact] = []
        started = time.perf_counter()
        self._active.add(context.job_id)
        try:
            for index in range(request.output.variations):
                context.cancellation.raise_if_cancelled()
                if latency_ms > 0:
                    await asyncio.sleep(latency_ms / 1000.0)

                seed = (base_seed + index * 7919) % (_MAX_SEED + 1)
                data = _render_sprite(
                    width=request.output.width,
                    height=request.output.height,
                    seed=seed,
                    symmetry=symmetry,
                    transparent=request.output.transparent,
                )
                artifacts.append(
                    ImageArtifact(
                        index=index,
                        data=data,
                        width=request.output.width,
                        height=request.output.height,
                        seed=seed,
                        metadata={"renderer": "symmetric-sprite", "grid": _SPRITE_GRID},
                    )
                )
                context.report(
                    (index + 1) / request.output.variations,
                    "generating",
                    engine_id=manifest.id,
                )
        finally:
            self._active.discard(context.job_id)

        return EngineGenerationResult(
            engine=self.engine_ref(),
            artifacts=tuple(artifacts),
            timings=StageTimings(inference_ms=(time.perf_counter() - started) * 1000.0),
            warnings=(),
            engine_metadata={
                "engine": manifest.id,
                "symmetry": symmetry,
                "sprite_grid": _SPRITE_GRID,
                "device": "cpu",
            },
        )


def _render_sprite(
    *, width: int, height: int, seed: int, symmetry: bool, transparent: bool
) -> bytes:
    """Desenha um sprite simétrico em grade baixa e amplia por nearest-neighbor."""
    rng = random.Random(seed)
    grid = _SPRITE_GRID
    half = grid // 2

    body = (rng.randrange(60, 200), rng.randrange(60, 200), rng.randrange(60, 200), 255)
    accent = (rng.randrange(180, 255), rng.randrange(120, 255), rng.randrange(60, 200), 255)
    outline = (
        max(0, body[0] - 45),
        max(0, body[1] - 45),
        max(0, body[2] - 45),
        255,
    )
    background = (0, 0, 0, 0) if transparent else (
        rng.randrange(20, 60),
        rng.randrange(20, 60),
        rng.randrange(30, 80),
        255,
    )

    sprite = Image.new("RGBA", (grid, grid), background)
    pixels = sprite.load()

    for y in range(2, grid - 2):
        for x in range(half):
            filled = rng.random() < (0.62 if 4 <= y <= grid - 5 else 0.32)
            if not filled:
                continue
            color = accent if rng.random() < 0.22 else body
            pixels[x, y] = color
            if symmetry:
                pixels[grid - 1 - x, y] = color

    # Contorno simples: pixel vazio vizinho de pixel cheio vira outline.
    filled_map = [
        [pixels[x, y][3] > 0 and pixels[x, y][:3] != background[:3] for y in range(grid)]
        for x in range(grid)
    ]
    for x in range(grid):
        for y in range(grid):
            if filled_map[x][y]:
                continue
            neighbours = [
                filled_map[x + dx][y + dy]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= x + dx < grid and 0 <= y + dy < grid
            ]
            if any(neighbours):
                pixels[x, y] = outline

    image = sprite.resize((width, height), Image.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
