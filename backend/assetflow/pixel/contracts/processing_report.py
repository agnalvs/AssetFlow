"""ProcessingReport — o que o PixelPostProcessor fez com a imagem (plano Pixel §74).

O relatório existe para responder, meses depois, à única pergunta que importa
em um benchmark: *este resultado saiu deste algoritmo ou de outro?*

Ele registra a versão do processador, a versão do profile, cada estágio que
rodou (e os que foram pulados, com o motivo) e as métricas de antes/depois.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ...generation.schemas import AssetFlowModel
from ..version import POSTPROCESSOR_VERSION

__all__ = ["ProcessingReport", "ProcessingStepReport"]


class ProcessingStepReport(AssetFlowModel):
    """Uma etapa do pipeline de processamento."""

    name: str
    version: str = "1.0.0"
    applied: bool = True
    #: Preenchido quando ``applied`` é ``False`` (ex.: "cleanup desligado").
    skipped_reason: str | None = None
    duration_ms: float = 0.0
    #: Diagnóstico livre da etapa (tamanho antes/depois, cores, pixels tocados).
    details: dict[str, Any] = Field(default_factory=dict)


class ProcessingReport(AssetFlowModel):
    """Relatório completo de um processamento Pixel Exact.

    Serializado como ``processing.json`` ao lado do asset (plano Pixel §70).
    """

    processor_version: str = POSTPROCESSOR_VERSION
    spec_id: str = "inline"
    spec_version: str = "1.0.0"
    mode: str = "pixel_exact"

    #: Resolução da imagem que entrou (a saída bruta do motor).
    source_size: tuple[int, int] = (0, 0)
    #: Resolução lógica final — a do arquivo entregue.
    logical_size: tuple[int, int] = (0, 0)

    steps: tuple[ProcessingStepReport, ...] = ()

    logical_reduction: str = "box_then_quantize"
    palette_method: str = "max_colors"
    dither: bool = False
    canvas_mode: str = "contain"
    cleanup_mode: str = "conservative"

    #: Cores únicas não transparentes antes e depois (plano Pixel §93/§94).
    source_color_count: int = 0
    final_color_count: int = 0
    palette: tuple[str, ...] = ()

    #: Tentativa em que este resultado foi produzido (1 = primeira) (§61).
    attempt: int = 1
    warnings: tuple[str, ...] = ()
    duration_ms: float = 0.0
    metrics: dict[str, Any] = Field(default_factory=dict)

    @property
    def step_names(self) -> tuple[str, ...]:
        """Nomes das etapas efetivamente aplicadas."""
        return tuple(step.name for step in self.steps if step.applied)

    def step(self, name: str) -> ProcessingStepReport | None:
        for entry in self.steps:
            if entry.name == name:
                return entry
        return None
