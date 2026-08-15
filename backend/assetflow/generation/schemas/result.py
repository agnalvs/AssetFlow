"""Generation Result universal (plano §21).

Todos os motores devolvem exatamente a mesma estrutura. O frontend jamais
precisa saber se quem gerou foi SDXL, FLUX, um mock ou uma API remota.

Há dois níveis, por uma razão de acoplamento:

``EngineGenerationResult``
    O que a **gaveta** devolve. Contém bytes de imagem e metadados de
    inferência. A gaveta não conhece job, projeto, storage nem URI.

``GenerationResult``
    O envelope do **kernel**. Acrescenta job, motor efetivamente usado,
    fallback, tempos por etapa e, depois do storage, as URIs.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from .capability import Capability
from .common import AssetFlowModel, StageTimings
from .engine import EngineRef

__all__ = [
    "GenerationStatus",
    "ImageArtifact",
    "EngineGenerationResult",
    "GenerationOutput",
    "GenerationResult",
]


class GenerationStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImageArtifact(AssetFlowModel):
    """Uma imagem produzida por uma gaveta.

    ``data`` é excluído da serialização: bytes crus não trafegam em JSON de
    API. Quem transforma bytes em URI é o AssetStorageService (plano §39).
    """

    index: int = Field(default=0, ge=0)
    data: bytes = Field(repr=False, exclude=True)
    mime_type: str = "image/png"
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    seed: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def size_bytes(self) -> int:
        return len(self.data)


class EngineGenerationResult(AssetFlowModel):
    """Resultado normalizado devolvido por uma gaveta.

    Produzido pelo *Result Mapper* interno de cada motor (plano §22): é ali
    que a saída nativa (tensores, objetos de pipeline, JSON de API remota)
    vira este formato único.
    """

    engine: EngineRef
    artifacts: tuple[ImageArtifact, ...]
    timings: StageTimings = Field(default_factory=StageTimings)
    warnings: tuple[str, ...] = ()
    engine_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnóstico livre do motor (passos, sampler, device...).",
    )


class GenerationOutput(AssetFlowModel):
    """Uma saída no nível do kernel/produto.

    Carrega bytes enquanto trafega em memória e ganha ``uri`` depois que o
    storage persiste o arquivo.
    """

    index: int = Field(default=0, ge=0)
    type: str = "image"
    mime_type: str = "image/png"
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    seed: int | None = None
    uri: str | None = None
    thumbnail_uri: str | None = None
    data: bytes | None = Field(default=None, repr=False, exclude=True)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_artifact(cls, artifact: ImageArtifact) -> "GenerationOutput":
        return cls(
            index=artifact.index,
            mime_type=artifact.mime_type,
            width=artifact.width,
            height=artifact.height,
            seed=artifact.seed,
            data=artifact.data,
            metadata=dict(artifact.metadata),
        )


class GenerationResult(AssetFlowModel):
    """Envelope do Generation Kernel — o formato único do sistema."""

    job_id: str
    request_id: str
    status: GenerationStatus = GenerationStatus.COMPLETED
    capability: Capability
    engine: EngineRef
    outputs: tuple[GenerationOutput, ...] = ()
    timings: StageTimings = Field(default_factory=StageTimings)

    #: Motor pedido/preferido antes de qualquer fallback.
    requested_engine_id: str | None = None
    fallback_used: bool = False
    attempted_engines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    def without_payloads(self) -> "GenerationResult":
        """Cópia sem bytes — segura para logs e para respostas de API."""
        return self.model_copy(
            update={
                "outputs": tuple(
                    output.model_copy(update={"data": None}) for output in self.outputs
                )
            }
        )
