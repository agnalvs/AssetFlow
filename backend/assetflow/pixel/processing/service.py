"""PixelPostProcessor — executa a lista de transformações (plano Pixel §6 a §9).

Este módulo é deliberadamente burro. Ele não sabe reduzir resolução, escolher
paleta nem cortar alpha: ele só percorre estágios, mede o tempo de cada um e
monta o :class:`ProcessingReport`. Toda a inteligência mora em
``stages/`` — que é o que permite trocar um estágio sem reescrever o pipeline.

    PixelPostProcessor **pode** alterar pixels (plano Pixel §6).
    PixelValidator **nunca** altera pixels (plano Pixel §37 e §104).

E, principalmente: nada aqui conhece o motor que produziu a imagem
(plano Pixel §5 e §105).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image

from ...generation.schemas import Stopwatch
from ..contracts.output_spec import PixelOutputSpec
from ..contracts.processing_report import ProcessingReport, ProcessingStepReport
from ..imaging import count_colors, ensure_rgba, to_array
from ..version import POSTPROCESSOR_VERSION
from .stages import (
    AlphaNormalizer,
    CanvasNormalizer,
    ConservativeCleaner,
    InputNormalizer,
    LogicalPixelReducer,
    PaletteQuantizer,
)
from .stages.base import PixelContext, PixelTransform

__all__ = ["PixelPostProcessor", "ProcessingOutcome", "default_transforms"]

_LOG = logging.getLogger("assetflow.pixel.processing")


def default_transforms() -> tuple[PixelTransform, ...]:
    """A ordem do plano Pixel §8.

    A ordem importa e não é arbitrária:

    1. ``input`` normaliza para RGBA e valida o que chegou;
    2. ``canvas`` acerta o aspect ratio **antes** de reduzir, senão a redução
       deformaria o personagem;
    3. ``logical_reducer`` leva à resolução lógica final — é o marco a partir
       do qual nenhum resampling suavizado pode mais acontecer (§20);
    4. ``alpha`` binariza a transparência **antes** da paleta, para que
       pixels invisíveis não gastem entradas de paleta;
    5. ``palette`` produz o conjunto exato de cores;
    6. ``cleanup`` corrige só o que for de altíssima confiança (§30).

    O ``PixelExporter`` não está nesta lista de propósito: ele precisa dos
    relatórios de processamento **e** de validação, que só existem depois.
    """
    return (
        InputNormalizer(),
        CanvasNormalizer(),
        LogicalPixelReducer(),
        AlphaNormalizer(),
        PaletteQuantizer(),
        ConservativeCleaner(),
    )


@dataclass(slots=True)
class ProcessingOutcome:
    """Imagem Pixel Exact + o relatório do que foi feito (plano Pixel §5)."""

    image: Image.Image
    report: ProcessingReport


class PixelPostProcessor:
    """Transforma uma imagem bruta em um asset tecnicamente exato."""

    version = POSTPROCESSOR_VERSION

    def __init__(self, transforms: Sequence[PixelTransform] | None = None) -> None:
        self._transforms: tuple[PixelTransform, ...] = tuple(
            transforms if transforms is not None else default_transforms()
        )

    @property
    def transforms(self) -> tuple[PixelTransform, ...]:
        return self._transforms

    def names(self) -> tuple[str, ...]:
        return tuple(transform.name for transform in self._transforms)

    # ------------------------------------------------------------------
    def process(
        self,
        image: Image.Image,
        spec: PixelOutputSpec,
        *,
        attempt: int = 1,
        logger: logging.Logger | None = None,
    ) -> ProcessingOutcome:
        """Roda a cadeia inteira e devolve imagem + relatório."""
        context = PixelContext(spec=spec, attempt=attempt, logger=logger or _LOG)
        watch = Stopwatch()

        current = ensure_rgba(image)
        source_size = current.size
        source_color_count = count_colors(to_array(current))

        steps: list[ProcessingStepReport] = []
        for transform in self._transforms:
            if not transform.applies_to(context):
                steps.append(
                    ProcessingStepReport(
                        name=transform.name,
                        version=transform.version,
                        applied=False,
                        skipped_reason=transform.skip_reason(context),
                    )
                )
                context.take_details()
                continue

            step_watch = Stopwatch()
            current = transform.apply(current, context)
            steps.append(
                ProcessingStepReport(
                    name=transform.name,
                    version=transform.version,
                    applied=True,
                    duration_ms=step_watch.elapsed_ms,
                    details=context.take_details(),
                )
            )

        final = ensure_rgba(current)
        array = to_array(final)
        palette = tuple(context.shared.get("palette", ()))

        report = ProcessingReport(
            processor_version=self.version,
            spec_id=spec.id,
            spec_version=spec.version,
            mode=spec.mode,
            source_size=source_size,
            logical_size=final.size,
            steps=tuple(steps),
            logical_reduction=spec.logical_reduction.method,
            palette_method=spec.palette.mode,
            dither=spec.dithering.enabled,
            canvas_mode=spec.canvas.mode,
            cleanup_mode=spec.cleanup.mode,
            source_color_count=source_color_count,
            final_color_count=count_colors(array),
            palette=palette,
            attempt=attempt,
            warnings=tuple(context.warnings),
            duration_ms=watch.elapsed_ms,
            metrics={
                "source_pixels": source_size[0] * source_size[1],
                "logical_pixels": final.width * final.height,
                "color_reduction_ratio": (
                    round(count_colors(array) / source_color_count, 6)
                    if source_color_count
                    else 0.0
                ),
            },
        )
        return ProcessingOutcome(image=final, report=report)
