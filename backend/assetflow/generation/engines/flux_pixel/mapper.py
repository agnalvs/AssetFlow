"""Result Mapper do FLUX Pixel (plano §22).

    saída nativa do FluxPipeline (objetos PIL)
           ↓
    FluxResultMapper
           ↓
    EngineGenerationResult

É aqui que a tecnologia deixa de existir para o resto do sistema. O
``EngineRef`` sai completo — motor, versão, versão do adapter, modelo e LoRA —
porque é ele que o plano de motores §18 exige guardar em cada geração.
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
from .config import ADAPTER_VERSION

__all__ = ["to_engine_result", "engine_ref"]


def engine_ref(
    manifest: EngineManifest,
    *,
    model_id: str | None,
    model_revision: str | None = None,
    lora_id: str | None = None,
) -> EngineRef:
    """Identidade completa desta gaveta para o histórico (plano de motores §18)."""
    return EngineRef(
        id=manifest.id,
        version=manifest.version,
        provider=manifest.provider,
        model_id=model_id,
        model_revision=model_revision,
        adapter_version=ADAPTER_VERSION,
        lora_id=lora_id,
    )


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
    lora_id: str | None,
    inference_ms: float,
    engine_metadata: dict[str, Any] | None = None,
    warnings: Sequence[str] = (),
) -> EngineGenerationResult:
    """Normaliza a saída do FLUX para o formato universal do AssetFlow."""
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
                metadata={"renderer": "flux-pixel", "lora_id": lora_id},
            )
        )

    return EngineGenerationResult(
        engine=engine_ref(
            manifest,
            model_id=model_id,
            model_revision=model_revision,
            lora_id=lora_id,
        ),
        artifacts=tuple(artifacts),
        timings=StageTimings(inference_ms=inference_ms),
        warnings=tuple(warnings),
        engine_metadata={
            "engine": manifest.id,
            "adapter_version": ADAPTER_VERSION,
            **(engine_metadata or {}),
        },
    )
