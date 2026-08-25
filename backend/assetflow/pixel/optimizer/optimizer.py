"""AssetFlowPixelOptimizer — o estágio obrigatório do pipeline (§38 e §45).

A peça que o resto do AssetFlow enxerga. Ela recebe ``(imagem, spec,
validação)`` e devolve ``(imagem, OptimizationReport)``.

O que ele **é**
---------------
Um estágio de pós-geração, dentro da ilha Pixel Exact, entre a primeira
validação e a aceitação. Todo motor passa por ele — não porque cada motor o
chame, mas porque nenhum motor decide o que acontece depois de gerar a imagem
(§80). É o que torna a otimização obrigatória sem que exista um único ``if
engine ==`` em lugar nenhum.

O que ele **não é** (§79)
-------------------------
Não é um motor, e por isso não aparece em ``EngineRegistry``, não tem
``manifest.json`` e não é escolhível na interface. Ele não gera imagem: ele
corrige a que chegou. Um sprite em branco entra em branco e sai em branco, com
um laudo dizendo que não havia o que corrigir — porque preencher seria gerar,
e gerar é do motor.

Não é opcional. ``OptimizationStatus.SKIPPED`` é uma decisão do Optimizer
("olhei e não havia o que fazer"), nunca uma decisão de quem pediu o asset
(§46). O único jeito de desligá-lo é a configuração explícita do servidor, e aí
o status é ``DISABLED`` — que fica registrado no relatório do job.

Regra de ouro: a otimização não pode piorar o asset (§20)
---------------------------------------------------------
Se a nota depois for **menor** que a nota antes, a versão otimizada é
descartada e o sprite original volta. Um corretor que às vezes estraga é pior
que nenhum corretor, porque ninguém consegue prever qual dos dois recebeu.

A comparação é entre notas de qualidade, e só quando o ``pixel_exact`` não
regrediu: um asset que ficou tecnicamente correto com nota menor **é** uma
melhora, e desfazê-la seria devolver um arquivo fora de especificação.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PIL import Image

from ...generation.schemas import Stopwatch
from ..contracts.output_spec import PixelOutputSpec
from ..contracts.validation_report import PixelValidationReport
from .canvas import PixelCanvas
from .contracts import OptimizationReport, OptimizationStatus
from .executor import ToolCallLog
from .loop import ReviewLoop

__all__ = ["OPTIMIZER_VERSION", "AssetFlowPixelOptimizer", "OptimizationOutcome"]

_LOG = logging.getLogger("assetflow.pixel.optimizer")

#: Versão do Optimizer. Acompanha os relatórios pelo mesmo motivo que
#: ``VALIDATOR_VERSION``: duas otimizações só são comparáveis se saíram da
#: mesma versão (plano Pixel §76).
OPTIMIZER_VERSION = "1.0.0"


@dataclass(slots=True)
class OptimizationOutcome:
    """O que sai do Optimizer para o :class:`PixelAssetProcessor`."""

    #: A imagem que segue no pipeline — otimizada, ou a original de volta se a
    #: otimização tiver piorado o asset (§20).
    image: Image.Image
    report: OptimizationReport
    #: O relatório de validação que corresponde a :attr:`image`. Vem
    #: preenchido porque o Optimizer **precisou** medir a imagem otimizada
    #: para aplicar o §20 — devolvê-lo poupa o chamador de validar de novo o
    #: mesmo arquivo. ``None`` só quando ``revalidate`` não foi informado.
    validation: PixelValidationReport | None = None
    #: Histórico de tool calls, gravado como ``optimizer_actions.json`` (§47).
    calls: ToolCallLog = field(default_factory=ToolCallLog)
    #: A otimização foi descartada por ter piorado a nota?
    reverted: bool = False
    optimizer_version: str = OPTIMIZER_VERSION

    @property
    def changed(self) -> bool:
        return self.report.changed_anything and not self.reverted


class AssetFlowPixelOptimizer:
    """Revisa e corrige o sprite depois do pós-processamento (§38)."""

    version = OPTIMIZER_VERSION
    name = "AssetFlow Pixel Optimizer"

    def __init__(
        self,
        *,
        loop: ReviewLoop | None = None,
        enabled: bool = True,
    ) -> None:
        self._loop = loop
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    def optimize(
        self,
        image: Image.Image,
        spec: PixelOutputSpec,
        validation: PixelValidationReport,
        *,
        revalidate=None,
        logger: logging.Logger | None = None,
    ) -> OptimizationOutcome:
        """Corrige o que der para corrigir e devolve a imagem que vale.

        Args:
            image: o sprite **já na resolução lógica**, saído do
                ``PixelPostProcessor``. Otimizar antes da redução devolveria o
                problema pela mesma porta por onde ele entrou (§14).
            spec: o contrato de saída — paleta, alpha, limpeza.
            validation: o relatório da validação V1.
            revalidate: função ``(imagem) -> PixelValidationReport`` usada para
                aplicar a regra do §20. Sem ela a comparação não acontece e a
                imagem otimizada segue como está.

        ``report.duration_ms`` cobre a chamada inteira, **inclusive** a
        revalidação: a V2 só existe porque o Optimizer rodou, e cobrá-la do
        tempo de validação faria a otimização parecer mais barata do que é.
        """
        watch = Stopwatch()
        outcome = self._optimize(image, spec, validation, revalidate, logger or _LOG)
        outcome.report.duration_ms = watch.elapsed_ms
        return outcome

    # ------------------------------------------------------------------
    def _optimize(
        self,
        image: Image.Image,
        spec: PixelOutputSpec,
        validation: PixelValidationReport,
        revalidate,
        out: logging.Logger,
    ) -> OptimizationOutcome:
        if not self._enabled:
            report = OptimizationReport(status=OptimizationStatus.DISABLED)
            report.score_before = validation.quality.score
            report.score_after = validation.quality.score
            return OptimizationOutcome(
                image=image, report=report, validation=validation
            )

        canvas = PixelCanvas.from_image(image)
        calls = ToolCallLog()
        report = self._run(canvas, spec, validation, calls, out)
        report.score_before = validation.quality.score

        if not report.changed_anything:
            report.score_after = validation.quality.score
            return OptimizationOutcome(
                image=image, report=report, calls=calls, validation=validation
            )

        optimized = canvas.to_image()
        if revalidate is None:
            return OptimizationOutcome(image=optimized, report=report, calls=calls)

        after = revalidate(optimized)
        report.score_after = after.quality.score

        if _worsened(validation, after):
            out.info(
                "optimizer: correção descartada — qualidade %s -> %s",
                validation.quality.score,
                after.quality.score,
            )
            return OptimizationOutcome(
                image=image,
                report=report,
                calls=calls,
                reverted=True,
                validation=validation,
            )

        return OptimizationOutcome(
            image=optimized, report=report, calls=calls, validation=after
        )

    # ------------------------------------------------------------------
    def _run(
        self,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        validation: PixelValidationReport,
        calls: ToolCallLog,
        logger: logging.Logger,
    ) -> OptimizationReport:
        """Executa o laço de revisão.

        A guarda de paleta não é montada aqui: quem a monta é o próprio laço,
        por asset, porque ela carrega o estado da paleta **daquele** sprite —
        quantas cores já foram gastas e quais (ver :func:`loop.guard_for`).
        """
        loop = self._loop or ReviewLoop()
        return loop.run(canvas, spec, validation, log=calls, logger=logger)


# ----------------------------------------------------------------------
def _worsened(before: PixelValidationReport, after: PixelValidationReport) -> bool:
    """A otimização piorou o asset? (plano Optimizer §20)

    Ficar tecnicamente correto nunca é piorar, mesmo com nota menor: o
    ``pixel_exact`` é requisito, e a nota é indicador. Desfazer uma correção
    que colocou o asset dentro da especificação devolveria um arquivo fora
    dela — com um número mais bonito ao lado.
    """
    if after.pixel_exact and not before.pixel_exact:
        return False
    if before.pixel_exact and not after.pixel_exact:
        return True
    return after.quality.score < before.quality.score
