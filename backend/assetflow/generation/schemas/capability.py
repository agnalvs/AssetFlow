"""Capability — a unidade de roteamento do AssetFlow (plano §7).

O AssetFlow **nunca** procura por "SDXL". Ele procura por uma capacidade,
por exemplo ``text_to_image.pixel``. Motores declaram quais capacidades
conseguem executar; o resolver casa pedido e oferta.

Formato: ``<family>.<variant>``

    text_to_image.pixel
    inpainting.general
    character.2d

O curinga ``*`` é aceito no variant (``text_to_image.*``) para motores
generalistas que atendem qualquer variação de uma família.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import model_serializer, model_validator

from .common import FrozenModel

__all__ = ["Capability", "CapabilityParseError"]

_TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")
_VARIANT_TOKEN = re.compile(r"^([a-z][a-z0-9_]*|\*|[0-9]d)$")


class CapabilityParseError(ValueError):
    """String de capacidade malformada."""


class Capability(FrozenModel):
    """Value object imutável e hashável que representa uma capacidade.

    Aceita tanto a forma estruturada quanto a string curta em qualquer campo
    pydantic, e serializa sempre como string — o JSON do contrato universal
    permanece legível::

        {"capability": "text_to_image.pixel"}
    """

    family: str
    variant: str

    # ------------------------------------------------------------------
    # Construção
    # ------------------------------------------------------------------
    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _split(value)
        if isinstance(value, Capability):
            return {"family": value.family, "variant": value.variant}
        return value

    @model_validator(mode="after")
    def _validate_tokens(self) -> "Capability":
        if not _TOKEN.match(self.family):
            raise CapabilityParseError(f"família de capacidade inválida: {self.family!r}")
        if not _VARIANT_TOKEN.match(self.variant):
            raise CapabilityParseError(f"variante de capacidade inválida: {self.variant!r}")
        return self

    @classmethod
    def parse(cls, value: "str | Capability") -> "Capability":
        """Constrói a partir de ``"family.variant"``."""
        if isinstance(value, Capability):
            return value
        return cls(**_split(value))

    # ------------------------------------------------------------------
    # Comportamento
    # ------------------------------------------------------------------
    @model_serializer
    def _serialize(self) -> str:
        return str(self)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.family}.{self.variant}"

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Capability({str(self)!r})"

    @property
    def is_wildcard(self) -> bool:
        return self.variant == "*"

    def matches(self, requested: "Capability | str") -> bool:
        """Diz se *esta* capacidade declarada atende a capacidade pedida.

        Um motor que declara ``text_to_image.*`` atende ``text_to_image.pixel``.
        A recíproca não é verdadeira: pedir o curinga não é atendido por uma
        declaração específica, porque o pedido precisaria ser desambiguado
        antes de chegar ao resolver.
        """
        other = Capability.parse(requested)
        if self.family != other.family:
            return False
        return self.is_wildcard or self.variant == other.variant


def _split(value: str) -> dict[str, str]:
    raw = value.strip().lower()
    if raw.count(".") != 1:
        raise CapabilityParseError(
            f"capacidade {value!r} deve ter o formato '<family>.<variant>', "
            "por exemplo 'text_to_image.pixel'"
        )
    family, variant = raw.split(".")
    if not family or not variant:
        raise CapabilityParseError(f"capacidade {value!r} possui parte vazia")
    return {"family": family, "variant": variant}
