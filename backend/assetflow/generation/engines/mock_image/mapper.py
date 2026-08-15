"""Result Mapper da gaveta mock (plano §22).

Mesmo sem IA, a gaveta segue a arquitetura à risca: a saída "nativa" (aqui,
uma lista de bytes PNG) é convertida para o formato universal do AssetFlow
por um mapper próprio. Quando a gaveta for trocada por SDXL ou FLUX, apenas
este arquivo muda de forma — o resto do sistema não percebe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ....generation.schemas import (
    EngineGenerationResult,
    EngineManifest,
    EngineRef,
    ImageArtifact,
    StageTimings,
)

__all__ = ["NativeRender", "to_engine_result"]


@dataclass(frozen=True, slots=True)
class NativeRender:
    """A "saída nativa" desta gaveta."""

    data: bytes
    width: int
    height: int
    seed: int


def to_engine_result(
    manifest: EngineManifest,
    renders: Sequence[NativeRender],
    *,
    inference_ms: float,
    engine_metadata: dict[str, Any] | None = None,
    warnings: Sequence[str] = (),
) -> EngineGenerationResult:
    """Converte a saída nativa para o resultado universal do AssetFlow."""
    artifacts = tuple(
        ImageArtifact(
            index=index,
            data=render.data,
            mime_type="image/png",
            width=render.width,
            height=render.height,
            seed=render.seed,
            metadata={"renderer": "mock"},
        )
        for index, render in enumerate(renders)
    )
    return EngineGenerationResult(
        engine=EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id="mock://deterministic-placeholder",
            model_revision=manifest.version,
        ),
        artifacts=artifacts,
        timings=StageTimings(inference_ms=inference_ms),
        warnings=tuple(warnings),
        engine_metadata={"engine": manifest.id, **(engine_metadata or {})},
    )
