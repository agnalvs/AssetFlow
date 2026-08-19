"""Ponte entre a cadeia de pós-processamento e o módulo Pixel Exact.

A cadeia de pós-processamento é o encaixe genérico do AssetFlow (vale também
para o modo Studio). O Pixel Exact é uma tecnologia inteira, com estágios,
validação, política de aceitação e relatórios próprios. Esta ponte é o ponto
único em que uma coisa chama a outra::

    PostProcessingChain
        -> PixelExactProcessor        (este arquivo, ~100 linhas)
            -> PixelAssetProcessor    (assetflow/pixel/, a tecnologia)

Por que uma ponte em vez de espalhar os estágios do Pixel na cadeia: o módulo
``assetflow.pixel`` precisa continuar utilizável fora do pipeline de geração —
pelo endpoint de diagnóstico, por um script de benchmark, por um editor
futuro. Se ele dependesse de ``ImageBuffer``/``PostProcessContext``, isso
deixaria de ser verdade (plano Pixel §68 e §105).
"""

from __future__ import annotations

from ....pixel import PixelAssetProcessor, PixelProfileRegistry
from ....pixel.contracts import CheckStatus
from ...schemas import AssetOutputOverrides
from ..base import ImageBuffer, PostProcessContext, PostProcessor
from .spec import spec_from_profile

__all__ = ["PixelExactProcessor"]


class PixelExactProcessor(PostProcessor):
    """Aplica o Pixel Exact e traz os relatórios de volta para o buffer."""

    name = "pixel.exact"

    def __init__(
        self,
        registry: PixelProfileRegistry | None = None,
        processor: PixelAssetProcessor | None = None,
    ) -> None:
        self._registry = registry
        self._processor = processor or PixelAssetProcessor()

    # ------------------------------------------------------------------
    def _spec(self, context: PostProcessContext):
        overrides = context.extra.get("output_overrides")
        if not isinstance(overrides, AssetOutputOverrides):
            overrides = None
        return spec_from_profile(context.profile, self._registry, overrides=overrides)

    def applies_to(self, context: PostProcessContext) -> bool:
        return self._spec(context) is not None

    def process(self, buffer: ImageBuffer, context: PostProcessContext) -> ImageBuffer:
        spec = self._spec(context)
        if spec is None:  # pragma: no cover - `applies_to` já filtrou
            return buffer

        outcome = self._processor.run(
            buffer.image,
            spec,
            raw_data=buffer.source_data,
            logger=context.logger,
        )

        buffer.replace(outcome.logical)
        buffer.logical_size = outcome.logical.size
        buffer.palette = outcome.processing.palette
        buffer.artifacts.update(outcome.artifacts)
        buffer.metadata.update(
            {
                "color_count": outcome.processing.final_color_count,
                "logical_size": list(outcome.logical.size),
                "source_size": list(outcome.processing.source_size),
                "pixel_exact": outcome.pixel_exact,
                "quality_score": outcome.quality_score,
                "status": outcome.decision.status.value,
                "pixel_spec_id": spec.id,
                "pixel_steps": list(outcome.processing.step_names),
                "pixel_attempts": outcome.attempts,
                "hard_checks": outcome.validation.hard_check_map,
                "pixel_metrics": outcome.metrics,
            }
        )

        _record_issues(buffer, outcome)
        return buffer


def _record_issues(buffer: ImageBuffer, outcome) -> None:
    """Traduz o relatório Pixel para o vocabulário de issues do asset.

    Falha de hard check vira ``error``; indicador estrutural vira ``warning``.
    A distinção do plano Pixel §38 sobrevive à tradução: um aviso de qualidade
    jamais pode se disfarçar de erro técnico, nem o contrário.
    """
    # O contexto é montado como dicionário, e não expandido em `**kwargs`, para
    # que um check futuro que use `expected` ou `count` como chave de detalhe
    # não derrube o job com um argumento duplicado.
    for check in outcome.validation.hard_checks:
        if check.status is not CheckStatus.FAIL:
            continue
        buffer.add_issue(
            check.code,
            check.message or f"{check.name} reprovado",
            severity="error",
            **{"expected": check.expected, "actual": check.actual, **check.detail},
        )

    for warning in outcome.validation.quality.warnings:
        buffer.add_issue(
            warning.code,
            warning.message,
            severity="warning",
            **{"count": warning.count, **warning.detail},
        )
