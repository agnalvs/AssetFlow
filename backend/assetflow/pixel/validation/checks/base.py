"""Contrato de um HARD CHECK (plano Pixel §37 a §46).

Regra fundamental deste pacote inteiro: **o Validator nunca altera pixels**.
Ele mede, analisa, classifica e reporta. Quem corrige é o PixelPostProcessor
(plano Pixel §104).

Um check devolve sempre um
:class:`~assetflow.pixel.contracts.validation_report.HardCheckResult`. Se
qualquer um deles falhar, o asset não é Pixel Exact — não existe média que
compense (plano Pixel §38 e §39).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from ...contracts.output_spec import PixelOutputSpec
from ...contracts.validation_report import CheckStatus, HardCheckResult
from ...imaging import opaque_mask, to_array

__all__ = ["HardCheck", "ValidationContext"]

_LOG = logging.getLogger("assetflow.pixel.validation")


@dataclass(slots=True)
class ValidationContext:
    """A imagem final e o spec — nada além disso.

    O array RGBA e a máscara de foreground são calculados uma vez e
    compartilhados por todos os checks e analisadores: são a base de quase
    toda medida e recalcular custaria caro à toa.
    """

    image: Image.Image
    spec: PixelOutputSpec
    logger: logging.Logger = field(default_factory=lambda: _LOG)
    shared: dict[str, Any] = field(default_factory=dict)

    _array: np.ndarray | None = field(default=None, init=False, repr=False)
    _mask: np.ndarray | None = field(default=None, init=False, repr=False)

    @property
    def array(self) -> np.ndarray:
        """Imagem como ``(altura, largura, 4)`` ``uint8``."""
        if self._array is None:
            self._array = to_array(self.image)
        return self._array

    @property
    def mask(self) -> np.ndarray:
        """Máscara booleana dos pixels não totalmente transparentes."""
        if self._mask is None:
            self._mask = opaque_mask(self.array)
        return self._mask

    @property
    def size(self) -> tuple[int, int]:
        return (self.image.width, self.image.height)

    @property
    def canvas_pixels(self) -> int:
        return self.image.width * self.image.height


class HardCheck(ABC):
    """Um requisito obrigatório do Pixel Exact."""

    #: Código estável do check (``PX-DIM-001``...). Entra no relatório e vira
    #: contrato com o frontend e com o benchmark — não renomeie.
    code: str = "PX-000"
    name: str = "check"

    @abstractmethod
    def run(self, context: ValidationContext) -> HardCheckResult:
        """Mede a imagem e devolve o veredito. Nunca modifica nada."""

    def applies_to(self, context: ValidationContext) -> bool:
        """Profiles podem desligar um requisito (plano Pixel §65)."""
        return True

    def skip_reason(self, context: ValidationContext) -> str:
        return "requisito desativado pelo profile"

    # ------------------------------------------------------------------
    # Açúcar para as implementações
    # ------------------------------------------------------------------
    def _result(
        self,
        status: CheckStatus,
        message: str = "",
        *,
        expected: str | None = None,
        actual: str | None = None,
        **detail: Any,
    ) -> HardCheckResult:
        return HardCheckResult(
            code=self.code,
            name=self.name,
            status=status,
            message=message,
            expected=expected,
            actual=actual,
            detail=detail,
        )

    def passed(self, message: str = "", **kwargs: Any) -> HardCheckResult:
        return self._result(CheckStatus.PASS, message, **kwargs)

    def failed(self, message: str, **kwargs: Any) -> HardCheckResult:
        return self._result(CheckStatus.FAIL, message, **kwargs)

    def skipped(self, message: str = "", **kwargs: Any) -> HardCheckResult:
        return self._result(CheckStatus.SKIPPED, message, **kwargs)
