"""Tipos base compartilhados por todos os schemas de geração do AssetFlow.

Regra deste módulo: ele não pode conhecer nenhum motor, modelo, fornecedor ou
biblioteca de IA. É a camada mais neutra do sistema.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "AssetFlowModel",
    "FrozenModel",
    "AssetMode",
    "AssetType",
    "QualityLevel",
    "StageTimings",
    "Stopwatch",
    "new_id",
    "utcnow",
]


def utcnow() -> datetime:
    """Timestamp UTC consciente de fuso (nunca usar `datetime.utcnow()`)."""
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """Gera um identificador curto e legível, ex.: ``job_9f2c1ab34d10``."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class AssetFlowModel(BaseModel):
    """Modelo base de todos os schemas.

    `extra="forbid"` é intencional: um campo desconhecido em um contrato
    universal quase sempre significa que alguém tentou passar um parâmetro
    específico de motor por fora de ``engine_options`` (plano §20).
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=False,
        ser_json_bytes="base64",
    )


class FrozenModel(AssetFlowModel):
    """Modelo imutável e hashável (usado por value objects)."""

    model_config = ConfigDict(frozen=True)


class AssetMode(str, Enum):
    """Os dois universos visuais do AssetFlow."""

    PIXEL = "pixel"
    STUDIO = "studio"


class AssetType(str, Enum):
    """Tipos de asset previstos pelo produto.

    A lista pode crescer sem impacto arquitetural: o motor não conhece tipos
    de asset, apenas capacidades.
    """

    CHARACTER = "character"
    PROP = "prop"
    BACKGROUND = "background"
    TILE = "tile"
    TILESET = "tileset"
    SPRITESHEET = "spritesheet"
    ICON = "icon"
    EFFECT = "effect"
    UI = "ui"
    RAW = "raw"


class QualityLevel(str, Enum):
    """Knob abstrato de qualidade.

    Existe justamente para NÃO colocar ``steps``/``guidance`` no contrato
    universal (plano §20). Cada motor traduz este nível para os parâmetros
    que fizerem sentido na sua tecnologia — ou ignora, se não fizer sentido.
    """

    DRAFT = "draft"
    STANDARD = "standard"
    HIGH = "high"


class StageTimings(AssetFlowModel):
    """Observabilidade por etapa (plano §48)."""

    queue_ms: float | None = None
    model_load_ms: float | None = None
    inference_ms: float | None = None
    postprocess_ms: float | None = None
    storage_ms: float | None = None
    total_ms: float | None = None

    def merged_with(self, other: "StageTimings") -> "StageTimings":
        """Combina duas medições, somando os campos preenchidos em ambas."""
        data: dict[str, Any] = {}
        for field in self.__class__.model_fields:
            a = getattr(self, field)
            b = getattr(other, field)
            if a is None and b is None:
                data[field] = None
            else:
                data[field] = (a or 0.0) + (b or 0.0)
        return StageTimings(**data)


class Stopwatch:
    """Cronômetro simples usado para preencher :class:`StageTimings`."""

    __slots__ = ("_start", "_elapsed_ms")

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self._elapsed_ms: float | None = None

    def __enter__(self) -> "Stopwatch":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._elapsed_ms = (time.perf_counter() - self._start) * 1000.0

    @property
    def elapsed_ms(self) -> float:
        """Tempo decorrido; congelado após a saída do bloco ``with``."""
        if self._elapsed_ms is not None:
            return self._elapsed_ms
        return (time.perf_counter() - self._start) * 1000.0

    def reset(self) -> None:
        self._start = time.perf_counter()
        self._elapsed_ms = None
