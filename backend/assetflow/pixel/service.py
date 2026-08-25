"""PixelAssetProcessor — a fachada do módulo Pixel (plano Pixel §4 e §67).

Junta as peças na ordem que o plano define e devolve tudo que o resto do
AssetFlow precisa::

    Raw Image
        -> PixelPostProcessor        (pode alterar pixels)
        -> PixelValidator            V1   (nunca altera pixels)
        -> AssetFlowPixelOptimizer   (corrige pixel a pixel)
        -> PixelValidator            V2
        -> PixelAcceptancePolicy     (decide, sobre a V2)
        -> artefatos + relatórios

O Optimizer entra **aqui**, e não dentro de um motor, e é isso que o torna
obrigatório sem que exista um único ``if engine ==`` no sistema (plano
Optimizer §33 e §80): nenhuma gaveta decide o que acontece depois que ela
devolve a imagem, então toda gaveta herda este caminho. Quem pede um asset
escolhe o motor; a otimização não é opção de quem pede (§46).

É aqui também que mora o limite do plano Pixel §61: se o resultado não passar
na validação, o sistema tenta **uma** correção adicional com um spec
endurecido — e para. Nunca existe loop infinito.

Nada neste arquivo conhece motor, job, projeto ou storage. Ele recebe uma
imagem e um :class:`PixelOutputSpec`; quem persiste é a camada de cima.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from ..generation.schemas import Stopwatch
from .acceptance import PixelAcceptancePolicy
from .contracts.output_spec import PixelOutputSpec
from .contracts.processing_report import ProcessingReport
from .contracts.validation_report import AcceptanceDecision, PixelValidationReport
from .imaging import decode, ensure_rgba
from .optimizer import AssetFlowPixelOptimizer, OptimizationOutcome
from .preview import PreviewGenerator
from .processing.service import PixelPostProcessor
from .processing.stages.exporter import PixelExporter
from .validation.service import PixelValidator
from .version import PIXEL_PIPELINE_VERSION

__all__ = ["PixelAssetOutcome", "PixelAssetProcessor"]

_LOG = logging.getLogger("assetflow.pixel")


@dataclass(slots=True)
class PixelAssetOutcome:
    """Tudo que sai do módulo Pixel para um asset."""

    #: O asset real, na resolução lógica (plano Pixel §33 e §72).
    logical: Image.Image
    #: Ampliação inteira só para visualização (plano Pixel §34 e §73).
    preview: Image.Image | None
    processing: ProcessingReport
    #: A validação **final** (V2) — a que a aceitação usou.
    validation: PixelValidationReport
    decision: AcceptanceDecision
    #: A validação de antes do Optimizer (V1). É a única forma de responder
    #: "a otimização ajudou?" sem reprocessar o asset (plano Optimizer §47).
    initial_validation: PixelValidationReport | None = None
    #: O que o Optimizer fez — ``None`` só se ele não tiver rodado.
    optimization: OptimizationOutcome | None = None
    #: ``{"logical.png": b"...", "preview.png": ..., "palette.json": ...}``.
    artifacts: dict[str, bytes] = field(default_factory=dict)
    #: Quantas passagens de processamento foram necessárias (plano Pixel §61).
    attempts: int = 1
    pipeline_version: str = PIXEL_PIPELINE_VERSION
    #: Métricas de observabilidade do plano Pixel §93.
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def pixel_exact(self) -> bool:
        return self.validation.pixel_exact

    @property
    def quality_score(self) -> int:
        return self.validation.quality.score


class PixelAssetProcessor:
    """Orquestra processamento, validação, aceitação e exportação."""

    version = PIXEL_PIPELINE_VERSION

    def __init__(
        self,
        *,
        processor: PixelPostProcessor | None = None,
        validator: PixelValidator | None = None,
        policy: PixelAcceptancePolicy | None = None,
        preview: PreviewGenerator | None = None,
        exporter: PixelExporter | None = None,
        optimizer: AssetFlowPixelOptimizer | None = None,
    ) -> None:
        self._processor = processor or PixelPostProcessor()
        self._validator = validator or PixelValidator()
        self._policy = policy or PixelAcceptancePolicy()
        self._preview = preview or PreviewGenerator()
        self._exporter = exporter or PixelExporter()
        # Sem `None`: o Optimizer é estágio do pipeline, não peça opcional
        # (plano Optimizer §46). Para desligá-lo, injete um
        # ``AssetFlowPixelOptimizer(enabled=False)`` — e o status `disabled`
        # fica registrado no relatório, que é a diferença entre uma decisão e
        # um sumiço.
        self._optimizer = optimizer or AssetFlowPixelOptimizer()

    # ------------------------------------------------------------------
    def run(
        self,
        source: Image.Image | bytes,
        spec: PixelOutputSpec,
        *,
        raw_data: bytes | None = None,
        export: bool = True,
        logger: logging.Logger | None = None,
    ) -> PixelAssetOutcome:
        """Processa, valida, decide e (opcionalmente) exporta os arquivos.

        Args:
            source: imagem bruta do motor — ``Image`` ou bytes de PNG.
            spec: o contrato de saída do profile Pixel.
            raw_data: bytes originais, preservados como ``raw.png`` para
                debug e benchmark (plano Pixel §71). Se ``source`` já vier em
                bytes, é usado automaticamente.
            export: desligue para só medir, sem gerar arquivos.
        """
        log = logger or _LOG
        if isinstance(source, (bytes, bytearray)):
            raw_data = raw_data or bytes(source)
            image = decode(bytes(source))
        else:
            image = ensure_rgba(source)

        processing_watch = Stopwatch()
        attempt_spec = spec
        attempt = 1
        outcome = self._processor.process(image, attempt_spec, attempt=attempt, logger=log)

        validation_watch = Stopwatch()
        validation = self._validator.validate(outcome.image, spec, logger=log)
        validation_ms = validation_watch.elapsed_ms

        # Plano Pixel §61: no máximo `max_processing_attempts` passagens.
        while not validation.pixel_exact and attempt < spec.attempts.max_processing_attempts:
            hardened = _harden_spec(attempt_spec, validation)
            if hardened is None:
                # Nada a endurecer: repetir daria exatamente o mesmo resultado.
                log.debug("pixel: falha sem correção conhecida, não vale nova tentativa")
                break
            attempt += 1
            attempt_spec = hardened
            log.info(
                "pixel: tentativa %s após %s",
                attempt,
                [check.code for check in validation.failures],
            )
            outcome = self._processor.process(
                image, attempt_spec, attempt=attempt, logger=log
            )
            retry_watch = Stopwatch()
            validation = self._validator.validate(outcome.image, spec, logger=log)
            validation_ms += retry_watch.elapsed_ms

        processing_ms = processing_watch.elapsed_ms - validation_ms

        # ---- Optimizer (plano Optimizer §21) -------------------------
        # O sprite otimizado é revalidado, e é a **V2** que a aceitação usa.
        # Decidir sobre a V1 aprovaria ou reprovaria uma imagem que já não é a
        # entregue — que é exatamente o defeito que o plano veio fechar.
        postprocessed = outcome.image
        initial_validation = validation
        optimization = self._optimizer.optimize(
            postprocessed,
            spec,
            validation,
            revalidate=lambda image: self._validator.validate(image, spec, logger=log),
            logger=log,
        )
        logical = optimization.image

        if optimization.validation is not None:
            # O Optimizer já mediu esta imagem para aplicar o §20; medi-la de
            # novo daria o mesmo relatório e o dobro do custo.
            validation = optimization.validation
        elif logical is not postprocessed:  # pragma: no cover - só sem revalidate
            revalidation_watch = Stopwatch()
            validation = self._validator.validate(logical, spec, logger=log)
            validation_ms += revalidation_watch.elapsed_ms

        decision = self._policy.decide(
            validation, threshold=spec.validation.quality_threshold
        )

        # Uma linha por asset, com o veredito inteiro: é o que permite ler o
        # log de uma sessão de benchmark sem abrir um `validation.json` sequer
        # (plano Pixel §93).
        log.info(
            "pixel[%s]: %s -> %s | %s cores | pixel_exact=%s | qualidade=%s | "
            "otimização=%s | %s%s",
            spec.id,
            "x".join(str(value) for value in outcome.report.source_size),
            "x".join(str(value) for value in outcome.report.logical_size),
            outcome.report.final_color_count,
            validation.pixel_exact,
            validation.quality.score,
            optimization.report.status.value,
            decision.status.value,
            f" | {attempt} tentativas" if attempt > 1 else "",
        )

        preview_image = self._preview.generate(logical, spec)
        artifacts: dict[str, bytes] = {}
        if export:
            artifacts = self._exporter.export(
                logical,
                spec=spec,
                processing=outcome.report,
                validation=validation,
                decision=decision,
                preview=preview_image,
                raw=raw_data,
                postprocessed=postprocessed,
                initial_validation=initial_validation,
                optimization=optimization.report,
                optimizer_actions=optimization.calls.document(),
            )

        return PixelAssetOutcome(
            logical=logical,
            preview=preview_image,
            processing=outcome.report,
            validation=validation,
            decision=decision,
            initial_validation=initial_validation,
            optimization=optimization,
            artifacts=artifacts,
            attempts=attempt,
            metrics=_observability(
                outcome.report,
                validation,
                decision,
                optimization,
                processing_ms=max(0.0, processing_ms),
                validation_ms=validation_ms,
                attempts=attempt,
            ),
        )


def _harden_spec(
    spec: PixelOutputSpec, validation: PixelValidationReport
) -> PixelOutputSpec | None:
    """Monta o spec da segunda tentativa (plano Pixel §61).

    Só existe correção para falhas cuja causa é conhecida e cujo ajuste é
    seguro. Para o resto devolve ``None``: repetir com o mesmo spec queimaria
    uma tentativa para chegar ao mesmo resultado, e insistir às cegas é
    exatamente o que o plano proíbe.
    """
    codes = {check.code for check in validation.failures}
    updates: dict[str, Any] = {}

    if "PX-EMPTY-001" in codes and spec.alpha.threshold > 1:
        # Causa típica: o sprite inteiro veio semitransparente e o corte de
        # alpha apagou tudo. Baixar o limiar recupera a silhueta.
        updates["alpha"] = spec.alpha.model_copy(update={"threshold": 1})

    if "PX-COLOR-001" in codes and spec.dithering.enabled:
        # Dithering espalha cores intermediárias; sem ele o quantizador tem
        # muito mais folga para caber no limite.
        updates["dithering"] = spec.dithering.model_copy(update={"enabled": False})

    if "PX-BOUND-001" in codes and not spec.canvas.trim_transparent:
        # O conteúdo está encostando na borda: recortar a caixa do sprite e
        # reencaixá-lo com folga resolve sem deformar nada.
        updates["canvas"] = spec.canvas.model_copy(
            update={"mode": "contain", "trim_transparent": True}
        )

    if not updates:
        return None
    return spec.model_copy(update=updates)


def _observability(
    processing: ProcessingReport,
    validation: PixelValidationReport,
    decision: AcceptanceDecision,
    optimization: OptimizationOutcome,
    *,
    processing_ms: float,
    validation_ms: float,
    attempts: int,
) -> dict[str, Any]:
    """As métricas por job do plano Pixel §93/§94 e do plano Optimizer §68.

    As do Optimizer respondem a uma pergunta que o benchmark do §69 faz o
    tempo todo: **a otimização valeu a pena neste motor?** Para isso não basta
    saber a nota final — é preciso a nota de antes, a de depois e quantos
    pixels custaram a diferença.
    """
    metrics = validation.quality.metrics
    report = optimization.report
    return {
        "pixel_pipeline_version": PIXEL_PIPELINE_VERSION,
        "postprocessor_version": processing.processor_version,
        "validator_version": validation.validator_version,
        "optimizer_version": optimization.optimizer_version,
        "profile_version": f"{processing.spec_id}@{processing.spec_version}",
        "pixel_processing_time_ms": round(processing_ms, 3),
        "validation_time_ms": round(validation_ms, 3),
        "optimizer_time_ms": round(report.duration_ms, 3),
        "processing_attempts": attempts,
        "optimizer_status": report.status.value,
        "optimizer_reviewer": report.reviewer,
        "optimizer_iterations": report.iterations,
        "optimizer_tool_calls": report.tool_calls,
        "optimizer_pixels_changed": report.pixels_changed,
        "optimizer_reverted": optimization.reverted,
        "raw_dimensions": list(processing.source_size),
        "logical_dimensions": list(processing.logical_size),
        "raw_color_count": processing.source_color_count,
        "final_color_count": processing.final_color_count,
        "orphan_ratio": metrics.orphan_pixel_ratio,
        "microcluster_ratio": metrics.microcluster_ratio,
        "foreground_occupancy": metrics.foreground_occupancy,
        "quality_score_before_optimizer": report.score_before,
        "quality_score": validation.quality.score,
        "quality_improvement": report.improvement,
        "pixel_exact": validation.pixel_exact,
        "status": decision.status.value,
    }
