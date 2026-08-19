"""Infraestrutura de pós-processamento (plano §23).

O motor entrega **imagem bruta**. Tudo que transforma essa imagem em um asset
do AssetFlow acontece aqui: redução lógica, paleta, limpeza, validação.

É esta camada que garante o item §58 do plano: mesmo que um modelo produza
Pixel Art convincente sozinho, o comportamento do produto não depende dele.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from PIL import Image

from ..profiles import GenerationProfile
from ..schemas import ValidationIssue

__all__ = [
    "ImageBuffer",
    "PostProcessContext",
    "PostProcessor",
    "PostProcessingChain",
]


@dataclass(slots=True)
class ImageBuffer:
    """Imagem em trânsito pelo pipeline de pós-processamento."""

    image: Image.Image
    metadata: dict[str, Any] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    palette: tuple[str, ...] = ()
    logical_size: tuple[int, int] | None = None
    #: Bytes originais entregues pelo motor, quando disponíveis. O Pixel Exact
    #: os preserva como ``raw.png`` para debug e benchmark (plano Pixel §71).
    source_data: bytes | None = field(default=None, repr=False)
    #: Arquivos auxiliares produzidos pela cadeia, por nome
    #: (``preview.png``, ``palette.json``, ``validation.json``...). Quem os
    #: persiste é o pipeline; a cadeia só os produz (plano Pixel §70).
    artifacts: dict[str, bytes] = field(default_factory=dict, repr=False)

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def replace(self, image: Image.Image) -> "ImageBuffer":
        """Troca a imagem preservando metadados acumulados."""
        self.image = image
        return self

    def add_issue(
        self,
        code: str,
        message: str,
        *,
        severity: str = "warning",
        **context: Any,
    ) -> None:
        self.issues.append(
            ValidationIssue(code=code, message=message, severity=severity, context=context)
        )


@dataclass(slots=True)
class PostProcessContext:
    """Contexto disponível para os processadores."""

    profile: GenerationProfile
    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("assetflow.postprocessing")
    )
    extra: dict[str, Any] = field(default_factory=dict)


class PostProcessor(ABC):
    """Uma etapa de pós-processamento."""

    name: str = "postprocessor"

    @abstractmethod
    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        ...

    def applies_to(self, context: PostProcessContext) -> bool:
        """Permite que a etapa se desative com base no profile."""
        return True


class PostProcessingChain:
    """Sequência ordenada de etapas.

    A cadeia é montada a partir do profile — trocar as regras de Pixel Art é
    reordenar/adicionar processadores, nunca alterar o motor.
    """

    def __init__(self, processors: Iterable[PostProcessor] = ()) -> None:
        self._processors: list[PostProcessor] = list(processors)

    @property
    def processors(self) -> Sequence[PostProcessor]:
        return tuple(self._processors)

    def add(self, processor: PostProcessor) -> "PostProcessingChain":
        self._processors.append(processor)
        return self

    def names(self) -> tuple[str, ...]:
        return tuple(processor.name for processor in self._processors)

    def run(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        """Executa todas as etapas aplicáveis, em ordem."""
        applied: list[str] = []
        for processor in self._processors:
            if not processor.applies_to(context):
                continue
            buffer = processor.process(buffer, context)
            applied.append(processor.name)
        buffer.metadata["postprocessing"] = applied
        return buffer

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._processors)
