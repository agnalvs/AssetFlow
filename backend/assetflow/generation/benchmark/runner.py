"""BenchmarkRunner — roda a suíte em cada motor (plano de motores §19).

O runner usa o **caminho normal** do sistema: ele monta um
``AssetGenerationRequest`` com seleção manual de motor e o envia pelo
``GenerationService``, como a interface faria. Nada de atalho chamando a
gaveta direto.

Isso não é purismo. Um benchmark que chamasse ``engine.generate()`` mediria o
motor sozinho, e o que interessa comparar é o **asset entregue** — depois do
prompt adapter, do pós-processamento e da validação. O plano de motores §21 é explícito:
o PixelPostProcessor e o PixelValidator continuam indispensáveis em todos os
motores, então eles têm de estar no caminho medido.

Seleção manual com ``allow_fallback=False``, por um motivo: se o motor pedido
cair e outro atender, o benchmark estaria creditando a um motor o trabalho de
outro. Sem fallback, a queda vira o que ela é — uma falha daquele motor, que
entra na taxa de falha do §20.

Desde o plano de correção, o alvo é **método + motor** (§43). É o que
permite pôr motores diferentes na mesma tabela sem fingir
que são a mesma tecnologia — que é justamente o que o §43 pede.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Iterable, Sequence

from ...jobs.worker import GenerationWorker
from ..kernel.exceptions import GenerationError
from ..schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    EngineSelector,
    Job,
    JobStatus,
)
from ..service import GenerationService
from .metrics import BenchmarkReport, CaseOutcome, TechnicalMetrics
from .suite import BenchmarkCase, BenchmarkSuite, BenchmarkTarget

__all__ = ["BenchmarkRunner"]

_LOG = logging.getLogger("assetflow.generation.benchmark")

#: Quantas voltas do worker esperar por um job antes de desistir dele.
_MAX_WORKER_TURNS = 4


class BenchmarkRunner:
    """Executa a suíte comparativa."""

    def __init__(
        self,
        service: GenerationService,
        worker: GenerationWorker,
        *,
        suite: BenchmarkSuite | None = None,
    ) -> None:
        self._service = service
        self._worker = worker
        self._suite = suite or BenchmarkSuite()

    @property
    def suite(self) -> BenchmarkSuite:
        return self._suite

    # ------------------------------------------------------------------
    async def run(
        self,
        *,
        targets: Sequence[BenchmarkTarget | str] | None = None,
        engines: Sequence[str] | None = None,
        cases: Iterable[str] | None = None,
        progress: Any = None,
    ) -> BenchmarkReport:
        """Roda cada caso em cada alvo e devolve o relatório.

        ``engines`` continua aceito e é lido como "por modelo, com este
        motor": chamadas escritas antes da camada de estratégias existir
        continuam valendo, e dizem a mesma coisa.
        """
        suite = self._suite.filtered(cases)
        chosen = targets if targets is not None else engines
        if chosen is None:
            resolved = list(suite.targets) or await self._default_targets()
        else:
            resolved = [
                item if isinstance(item, BenchmarkTarget) else BenchmarkTarget.parse(item)
                for item in chosen
            ]

        report = BenchmarkReport(
            suite_size=len(suite.cases),
            metadata={"targets": [item.label for item in resolved], **suite.metadata},
        )
        if not resolved:
            _LOG.warning("nenhum alvo disponível para o benchmark")
            return report

        for target in resolved:
            block = report.for_target(target)
            for case in suite.cases:
                if progress is not None:
                    progress(target.label, case)
                outcome = await self._run_case(case, target, suite.project_id)
                block.outcomes.append(outcome)
        return report

    # ------------------------------------------------------------------
    async def _default_targets(self) -> list[BenchmarkTarget]:
        """Cada motor disponível — e nada além deles (plano Optimizer §69).

        Gavetas ocultas ficam de fora: um número de referência ao lado dos
        motores de produção sugeriria que são comparáveis, e o mock não gera
        arte, gera um padrão determinístico.

        Todos os alvos atravessam o mesmo Pixel Optimizer, então a tabela
        compara motores — não pipelines.
        """
        entries = await self._service.engine_catalog(check_health=True)
        return [
            BenchmarkTarget(engine_id=entry.engine_id)
            for entry in entries
            if entry.available
        ]

    async def _run_case(
        self, case: BenchmarkCase, target: BenchmarkTarget, project_id: str
    ) -> CaseOutcome:
        """Um caso em um alvo, do pedido ao asset."""
        request = _build_request(case, target, project_id)
        started = time.perf_counter()

        try:
            job = await self._service.submit(request)
        except GenerationError as exc:
            return CaseOutcome(
                case_id=case.id,
                target=target,
                succeeded=False,
                error=f"{exc.code.value}: {exc.message}",
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )

        job = await self._drain(job)
        duration_ms = (time.perf_counter() - started) * 1000.0

        if job.status is not JobStatus.COMPLETED or job.asset is None:
            return CaseOutcome(
                case_id=case.id,
                target=target,
                resolved_engine_id=job.engine.id if job.engine else None,
                succeeded=False,
                error=job.error.message if job.error else f"job terminou {job.status.value}",
                duration_ms=duration_ms,
                warnings=job.warnings,
            )

        return _outcome_from_job(case, target, job, duration_ms)

    async def _drain(self, job: Job) -> Job:
        """Roda o worker até o job terminar.

        O runner dirige o worker explicitamente em vez de esperar por um loop
        de fundo: um benchmark tem de ser determinístico e terminar, e
        `run_once` dá as duas coisas.
        """
        for _ in range(_MAX_WORKER_TURNS):
            await self._worker.run_once(timeout=0.1)
            current = await self._service.get_job(job.id)
            if current.status.is_terminal:
                return current
        return await self._service.get_job(job.id)


def _build_request(
    case: BenchmarkCase, target: BenchmarkTarget, project_id: str
) -> AssetGenerationRequest:
    """O pedido de um caso, com método e motor fixados."""
    output = AssetOutputOverrides(variations=case.variations)
    if case.logical_size:
        output = output.model_copy(
            update={
                "logical_width": case.logical_size,
                "logical_height": case.logical_size,
            }
        )
    if case.max_colors:
        output = output.model_copy(update={"palette_size": case.max_colors})

    return AssetGenerationRequest(
        project_id=project_id,
        profile=case.profile,
        prompt=case.prompt,
        asset_type=case.asset_type,
        output=output,
        seed=case.seed,
        engine=(
            EngineSelector(
                mode="manual",
                engine_id=target.engine_id,
                # Sem fallback: ver a docstring do módulo. Um caso atendido
                # por outro motor não mede este motor.
                allow_fallback=False,
            )
            if target.engine_id
            else EngineSelector()
        ),
        metadata={"benchmark_case": case.id, "benchmark_target": target.label},
    )


def _outcome_from_job(
    case: BenchmarkCase, target: BenchmarkTarget, job: Job, duration_ms: float
) -> CaseOutcome:
    """Extrai as métricas do §20 de um job concluído."""
    variant = job.asset.variants[0] if job.asset and job.asset.variants else None
    metadata = dict(variant.metadata) if variant else {}
    pixel = dict(metadata.get("pixel_metrics") or {})

    requested = (
        (case.logical_size, case.logical_size) if case.logical_size else None
    )
    raw_size = metadata.get("render_size")

    technical = TechnicalMetrics(
        logical_size=(
            (variant.logical_width, variant.logical_height)
            if variant and variant.logical_width and variant.logical_height
            else None
        ),
        requested_logical_size=requested,
        color_count=variant.color_count if variant else None,
        max_colors=case.max_colors,
        pixel_exact=variant.pixel_exact if variant else None,
        quality_score=variant.quality_score if variant else None,
        status=variant.status if variant else None,
        orphan_ratio=pixel.get("orphan_ratio"),
        microcluster_ratio=pixel.get("microcluster_ratio"),
        foreground_occupancy=pixel.get("foreground_occupancy"),
        raw_color_count=pixel.get("raw_color_count"),
        raw_size=tuple(raw_size) if isinstance(raw_size, (list, tuple)) else None,
        # O que o Optimizer precisou fazer com a saída deste motor (§69).
        optimizer_status=pixel.get("optimizer_status"),
        optimizer_pixels_changed=pixel.get("optimizer_pixels_changed"),
        optimizer_iterations=pixel.get("optimizer_iterations"),
        quality_score_before_optimizer=pixel.get("quality_score_before_optimizer"),
        optimizer_reverted=pixel.get("optimizer_reverted"),
    )

    return CaseOutcome(
        case_id=case.id,
        target=target,
        resolved_engine_id=job.engine.id if job.engine else None,
        succeeded=True,
        duration_ms=duration_ms,
        inference_ms=job.timings.inference_ms or 0.0,
        postprocess_ms=job.timings.postprocess_ms or 0.0,
        technical=technical,
        asset_uri=variant.uri if variant else None,
        preview_uri=variant.preview_uri if variant else None,
        warnings=job.warnings,
    )
