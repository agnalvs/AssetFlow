"""Contrato de estágio do PixelPostProcessor (plano Pixel §7, §8 e §9).

O plano proíbe explicitamente a função única ``fix_pixel_art(image)``: ela
cresceria, acoplaria tudo e travaria a evolução. No lugar dela existe uma
lista de transformações substituíveis::

    for transform in transforms:
        image = transform.apply(image, context)

Trocar ``PaletteQuantizerV1`` por ``PaletteQuantizerV2`` passa a ser editar
uma lista, não reescrever um pipeline.

Nenhum estágio conhece motor, job, projeto ou storage. O contrato inteiro é
``(imagem, PixelOutputSpec) -> imagem``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from ...contracts.output_spec import PixelOutputSpec

__all__ = ["PixelContext", "PixelTransform"]

_LOG = logging.getLogger("assetflow.pixel.processing")


@dataclass(slots=True)
class PixelContext:
    """Tudo que um estágio pode consultar, e o caderno onde ele anota.

    ``details`` é o rascunho do estágio **atual**: o serviço o esvazia entre
    uma transformação e outra e o transforma em um
    :class:`~assetflow.pixel.contracts.processing_report.ProcessingStepReport`.
    """

    spec: PixelOutputSpec
    logger: logging.Logger = field(default_factory=lambda: _LOG)
    #: Tentativa corrente (plano Pixel §61: nunca mais que ``max_processing_attempts``).
    attempt: int = 1
    #: Anotações do estágio em execução.
    details: dict[str, Any] = field(default_factory=dict)
    #: Avisos que sobem para o ProcessingReport.
    warnings: list[str] = field(default_factory=list)
    #: Espaço compartilhado entre estágios (ex.: paleta escolhida pelo quantizador).
    shared: dict[str, Any] = field(default_factory=dict)

    def detail(self, key: str, value: Any) -> None:
        """Registra um número do estágio atual no relatório."""
        self.details[key] = value

    def warn(self, message: str) -> None:
        """Anota um aviso — nunca interrompe o processamento."""
        self.warnings.append(message)
        self.logger.debug("pixel: %s", message)

    def take_details(self) -> dict[str, Any]:
        """Devolve e limpa o rascunho do estágio."""
        details, self.details = self.details, {}
        return details


class PixelTransform(ABC):
    """Uma etapa do PixelPostProcessor.

    ``name``/``version`` acompanham o ProcessingReport: sem os dois é
    impossível comparar dois benchmarks (plano Pixel §76).
    """

    name: str = "pixel.transform"
    version: str = "1.0.0"

    @abstractmethod
    def apply(self, image: Image.Image, context: PixelContext) -> Image.Image:
        """Recebe a imagem, devolve a imagem transformada."""

    def applies_to(self, context: PixelContext) -> bool:
        """Permite que o estágio se desligue conforme o spec."""
        return True

    def skip_reason(self, context: PixelContext) -> str:
        """Motivo registrado no relatório quando o estágio não roda."""
        return "desativado pelo PixelOutputSpec"

    def __repr__(self) -> str:  # pragma: no cover - diagnóstico
        return f"<{type(self).__name__} {self.name} v{self.version}>"
