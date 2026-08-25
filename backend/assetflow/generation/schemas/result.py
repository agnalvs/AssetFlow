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
from .strategy import AgentRef, GenerationStrategyType

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
    """Envelope de uma geração — o formato único do sistema.

    Quem o produz é a **estratégia**, e não mais só o Kernel. É por isso que
    ``engine`` deixou de ser obrigatório: um asset desenhado pelo Pixel Agent
    não tem motor, e preencher o campo com algo para satisfazer o modelo faria
    o histórico afirmar que um modelo gerou o que nenhum modelo gerou
    (plano de correção §44, teste 2).

    Exatamente um dos dois vem preenchido — ``engine`` na estratégia por
    modelo, ``agent`` na do agente.
    """

    job_id: str
    request_id: str
    status: GenerationStatus = GenerationStatus.COMPLETED
    capability: Capability
    #: Como o asset foi criado (plano de correção §41).
    strategy: GenerationStrategyType = GenerationStrategyType.MODEL
    #: O motor que gerou. ``None`` quando a estratégia não usa motor.
    engine: EngineRef | None = None
    #: O agente que desenhou. ``None`` quando a estratégia usa motor.
    agent: AgentRef | None = None
    outputs: tuple[GenerationOutput, ...] = ()
    timings: StageTimings = Field(default_factory=StageTimings)

    #: Motor pedido/preferido antes de qualquer fallback.
    requested_engine_id: str | None = None
    fallback_used: bool = False
    attempted_engines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def producer_id(self) -> str:
        """Quem produziu isto, como uma string única para log e histórico.

        Existe para os lugares que só precisam de um rótulo — uma linha de
        log, uma chave de agrupamento — e não deveriam ter de saber se a
        geração veio de motor ou de agente.
        """
        if self.engine is not None:
            return self.engine.id
        if self.agent is not None:
            return self.agent.id
        return "desconhecido"  # pragma: no cover - defensivo

    def without_payloads(self) -> "GenerationResult":
        """Cópia sem bytes — segura para logs e para respostas de API."""
        return self.model_copy(
            update={
                "outputs": tuple(
                    output.model_copy(update={"data": None}) for output in self.outputs
                )
            }
        )
