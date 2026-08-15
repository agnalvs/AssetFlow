"""Result Mapper do SDXL (plano §22).

    SDXL output (objetos PIL do pipeline Diffusers)
           ↓
    SDXLResultMapper
           ↓
    AssetFlowGenerationResult

Este é o ponto exato onde a tecnologia deixa de existir para o resto do
sistema. Um `FluxResultMapper` faria a mesma tradução a partir de outra
saída nativa, e o AssetFlow não notaria a diferença.
"""

from __future__ import annotations

import io
from typing import Any, Sequence

from ....generation.schemas import (
    EngineGenerationResult,
    EngineManifest,
    EngineRef,
    ImageArtifact,
    StageTimings,
)

__all__ = ["to_engine_result"]


def _encode(image: Any) -> tuple[bytes, int, int]:
    """Converte a imagem devolvida pelo pipeline em PNG."""
    buffer = io.BytesIO()
    rgba = image.convert("RGBA")
    rgba.save(buffer, format="PNG")
    return buffer.getvalue(), rgba.width, rgba.height


def to_engine_result(
    manifest: EngineManifest,
    images: Sequence[Any],
    seeds: Sequence[int],
    *,
    model_id: str,
    model_revision: str | None,
    inference_ms: float,
    engine_metadata: dict[str, Any] | None = None,
    warnings: Sequence[str] = (),
) -> EngineGenerationResult:
    """Normaliza a saída do SDXL para o formato universal do AssetFlow."""
    artifacts: list[ImageArtifact] = []
    for index, image in enumerate(images):
        data, width, height = _encode(image)
        artifacts.append(
            ImageArtifact(
                index=index,
                data=data,
                mime_type="image/png",
                width=width,
                height=height,
                seed=seeds[index] if index < len(seeds) else None,
                metadata={"renderer": "diffusers-sdxl"},
            )
        )

    return EngineGenerationResult(
        engine=EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id=model_id,
            model_revision=model_revision,
        ),
        artifacts=tuple(artifacts),
        timings=StageTimings(inference_ms=inference_ms),
        warnings=tuple(warnings),
        engine_metadata={"engine": manifest.id, **(engine_metadata or {})},
    )
