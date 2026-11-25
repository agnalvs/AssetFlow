"""Registro de pipelines de asset."""

from __future__ import annotations

from typing import Any, Iterable

from ..kernel.exceptions import PipelineNotFound
from .base import AssetPipeline

__all__ = ["PipelineRegistry"]


class PipelineRegistry:
    """Resolve o pipeline pelo id declarado no profile."""

    def __init__(self, pipelines: Iterable[AssetPipeline] = ()) -> None:
        self._pipelines: dict[str, AssetPipeline] = {
            pipeline.id: pipeline for pipeline in pipelines
        }

    @classmethod
    def with_defaults(
        cls, pixel_profiles: Any = None, optimizer: Any = None, validator: Any = None
    ) -> "PipelineRegistry":
        """Registro padrão do produto: só o pipeline Pixel.

        Os pipelines Studio e Raw saíram na Fase A do plano do app
        (``PLANO_APP_DESENHISTA.md``): o app só gera Pixel Art, e nenhuma
        gaveta dele atende ``text_to_image.general``.

        Args:
            pixel_profiles: :class:`~assetflow.pixel.PixelProfileRegistry` com
                os profiles Pixel Exact. Fica opcional de propósito — sem ele
                o pipeline deriva o spec do próprio Generation Profile, e
                todo teste que monta um registro à mão continua valendo.
            optimizer: o :class:`AssetFlowPixelOptimizer` configurado. Também
                opcional, e pelo mesmo motivo — sem ele vale o padrão, que já
                é a otimização ligada (plano Optimizer §46).
            validator: o :class:`~assetflow.pixel.PixelValidator` com a
                calibração de ``config/quality.yaml``. Opcional: sem ele, os
                limiares do plano.
        """
        from .pixel import PixelCharacterPipeline

        return cls((PixelCharacterPipeline(pixel_profiles, optimizer, validator),))

    def register(self, pipeline: AssetPipeline) -> None:
        self._pipelines[pipeline.id] = pipeline

    def get(self, pipeline_id: str) -> AssetPipeline:
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise PipelineNotFound(
                f"pipeline '{pipeline_id}' não existe",
                detail={"available": sorted(self._pipelines)},
            )
        return pipeline

    def find(self, pipeline_id: str) -> AssetPipeline | None:
        return self._pipelines.get(pipeline_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pipelines))

    def list(self) -> list[AssetPipeline]:
        return [self._pipelines[key] for key in sorted(self._pipelines)]
