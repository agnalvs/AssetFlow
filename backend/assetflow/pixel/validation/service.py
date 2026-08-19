"""PixelValidator — o veredito técnico (plano Pixel §36 a §57).

    PixelValidator.validate(logical_image, output_spec) -> PixelValidationReport

Regra fundamental (§37 e §104): este serviço **não modifica a imagem**. Ele
mede, analisa, classifica e reporta. Nem ele nem nenhum check ou analisador
recebe permissão para "consertar" nada — corrigir é trabalho do
PixelPostProcessor, e misturar as duas coisas esconderia defeitos.

Segunda regra (§38): HARD CHECKS e QUALITY ANALYSIS ficam separados. Um erro
fatal nunca pode ser diluído por uma nota média boa.

Terceira regra (§59): a decisão de aprovar não mora aqui. Este relatório vai
para a :class:`~assetflow.pixel.acceptance.policy.PixelAcceptancePolicy`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PIL import Image

from ...generation.schemas import Stopwatch
from ..contracts.output_spec import PixelOutputSpec
from ..contracts.validation_report import (
    CheckStatus,
    HardCheckResult,
    PixelValidationReport,
    QualityMetrics,
    QualityReport,
    QualityWarning,
    TechnicalSummary,
)
from ..imaging import alpha_values, count_colors
from ..version import VALIDATOR_VERSION
from .analyzers import (
    ClusterAnalyzer,
    ColorRedundancyAnalyzer,
    OrphanPixelAnalyzer,
    OutlineAnalyzer,
    PaletteUsageAnalyzer,
    SpriteOccupancyAnalyzer,
)
from .analyzers.base import QualityAnalyzer
from .checks import (
    AlphaCheck,
    BoundaryCheck,
    ColorCountCheck,
    DimensionsCheck,
    EmptyImageCheck,
    LockedPaletteCheck,
)
from .checks.base import HardCheck, ValidationContext
from .scoring import QualityScorer

__all__ = ["PixelValidator", "default_analyzers", "default_checks"]

_LOG = logging.getLogger("assetflow.pixel.validation")


def default_checks() -> tuple[HardCheck, ...]:
    """Os requisitos obrigatórios do plano Pixel §40 a §45."""
    return (
        DimensionsCheck(),      # PX-DIM-001
        AlphaCheck(),           # PX-ALPHA-001
        ColorCountCheck(),      # PX-COLOR-001
        LockedPaletteCheck(),   # PX-PALETTE-001
        EmptyImageCheck(),      # PX-EMPTY-001
        BoundaryCheck(),        # PX-BOUND-001
    )


def default_analyzers() -> tuple[QualityAnalyzer, ...]:
    """Os indicadores estruturais do plano Pixel §48 a §55."""
    return (
        OrphanPixelAnalyzer(),
        ClusterAnalyzer(),
        SpriteOccupancyAnalyzer(),
        PaletteUsageAnalyzer(),
        ColorRedundancyAnalyzer(),
        OutlineAnalyzer(),
    )


class PixelValidator:
    """Inspeciona a imagem final e produz um relatório estruturado."""

    version = VALIDATOR_VERSION

    def __init__(
        self,
        checks: Sequence[HardCheck] | None = None,
        analyzers: Sequence[QualityAnalyzer] | None = None,
        scorer: QualityScorer | None = None,
    ) -> None:
        self._checks: tuple[HardCheck, ...] = tuple(
            checks if checks is not None else default_checks()
        )
        self._analyzers: tuple[QualityAnalyzer, ...] = tuple(
            analyzers if analyzers is not None else default_analyzers()
        )
        self._scorer = scorer or QualityScorer()

    @property
    def checks(self) -> tuple[HardCheck, ...]:
        return self._checks

    @property
    def analyzers(self) -> tuple[QualityAnalyzer, ...]:
        return self._analyzers

    # ------------------------------------------------------------------
    def validate(
        self,
        image: Image.Image,
        spec: PixelOutputSpec,
        *,
        logger: logging.Logger | None = None,
    ) -> PixelValidationReport:
        """Mede a imagem contra o spec. Não altera um único pixel."""
        watch = Stopwatch()
        context = ValidationContext(image=image, spec=spec, logger=logger or _LOG)

        hard_checks = tuple(self._run_checks(context))
        quality = self._run_quality(context)

        # `pixel_exact` exige que NENHUM check obrigatório tenha falhado. Um
        # check pulado (desligado pelo profile) não conta como aprovação nem
        # como reprovação — ele simplesmente não foi exigido.
        pixel_exact = not any(check.failed for check in hard_checks)

        return PixelValidationReport(
            validator_version=self.version,
            spec_id=spec.id,
            spec_version=spec.version,
            pixel_exact=pixel_exact,
            hard_checks=hard_checks,
            technical=_technical_summary(context),
            quality=quality,
            duration_ms=watch.elapsed_ms,
        )

    # ------------------------------------------------------------------
    def _run_checks(self, context: ValidationContext) -> list[HardCheckResult]:
        results: list[HardCheckResult] = []
        for check in self._checks:
            if not check.applies_to(context):
                results.append(
                    HardCheckResult(
                        code=check.code,
                        name=check.name,
                        status=CheckStatus.SKIPPED,
                        message=check.skip_reason(context),
                    )
                )
                continue
            try:
                results.append(check.run(context))
            except Exception as exc:  # pragma: no cover - defensivo
                context.logger.exception("check %s falhou", check.code)
                results.append(
                    HardCheckResult(
                        code=check.code,
                        name=check.name,
                        status=CheckStatus.FAIL,
                        message=f"erro ao executar o check: {exc}",
                    )
                )
        return results

    def _run_quality(self, context: ValidationContext) -> QualityReport:
        metrics: dict[str, object] = {}
        warnings: list[QualityWarning] = []
        applied: list[str] = []

        for analyzer in self._analyzers:
            if not analyzer.applies_to(context):
                continue
            try:
                result = analyzer.analyze(context)
            except Exception:  # pragma: no cover - análise nunca derruba job
                context.logger.exception("analisador %s falhou", analyzer.name)
                continue
            metrics.update(result.metrics)
            warnings.extend(result.warnings)
            applied.append(analyzer.name)

        quality_metrics = QualityMetrics.model_validate(metrics)
        score, penalties = self._scorer.score(quality_metrics, tuple(warnings), context.spec)
        return QualityReport(
            score=score,
            metrics=quality_metrics,
            warnings=tuple(warnings),
            analyzers=tuple(applied),
            penalties=penalties,
        )


def _technical_summary(context: ValidationContext) -> TechnicalSummary:
    """O bloco objetivo do relatório (plano Pixel §56)."""
    width, height = context.size
    return TechnicalSummary(
        size=f"{width}x{height}",
        width=width,
        height=height,
        colors=count_colors(context.array),
        alpha_values=alpha_values(context.array),
    )
