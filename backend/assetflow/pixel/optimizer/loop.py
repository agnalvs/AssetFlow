"""ReviewLoop — revisar, planejar, corrigir, repetir (plano Optimizer §18/§19).

    revisar -> planejar -> executar -> revisar de novo

Três voltas no máximo (§19). O teto não é economia de tempo: é a única coisa
que separa "corrigir" de "insistir". Um problema que sobrevive a três voltas de
correção não vai ceder na quarta — ele é de outra natureza, e o lugar dele é a
validação final, não mais um remendo.

Por que o laço revalida entre as voltas
---------------------------------------
O revisor lê o relatório do Validator para saber *o que* está errado. Depois da
primeira correção esse relatório descreve uma imagem que não existe mais: a
paleta pode já caber no orçamento, e o revisor continuaria pedindo que ela
fosse absorvida — corrigindo um problema resolvido, volta após volta.

Então cada volta a partir da segunda começa medindo de novo. O custo é baixo
(o canvas tem dezenas de pixels de lado, não milhares) e o alternativo é um
laço que trabalha em cima de um diagnóstico vencido.

As quatro saídas, e o que cada uma quer dizer
---------------------------------------------
``SKIPPED``
    O revisor não achou nada. **Não** significa que o Optimizer é opcional
    (§46): significa que ele olhou e decidiu não mexer — que é a decisão certa
    para um asset que já chegou bom.
``NO_SAFE_REPAIRS``
    O revisor achou problema e o planejador não tem correção honesta para
    nenhum deles. O sprite sai como entrou, e o laudo diz o porquê.
``OPTIMIZED``
    Alguma correção foi aplicada.
``EXHAUSTED``
    As três voltas acabaram com problemas ainda em aberto.

Duas paradas antecipadas
------------------------
**Plano vazio** encerra o laço: se nada mudou, revisar de novo produz o mesmo
laudo e o mesmo plano vazio.

**Nenhum pixel alterado** encerra também: o plano existia, foi executado e não
mexeu em nada (toda ação recusada pela paleta travada, por exemplo).
Continuar é o mesmo caso, escrito de outro jeito.
"""

from __future__ import annotations

import logging

from ..contracts.output_spec import PixelOutputSpec
from ..contracts.validation_report import PixelValidationReport
from ..validation.service import PixelValidator
from .canvas import PixelCanvas
from .contracts import OptimizationReport, OptimizationStatus
from .executor import PixelToolExecutor, ToolCallLog
from .palette import PaletteGuard
from .planner import RepairPlanner
from .reviewer import PixelReviewer

__all__ = ["MAX_ITERATIONS", "ReviewLoop", "guard_for"]

_LOG = logging.getLogger("assetflow.pixel.optimizer")

#: Teto de voltas do laço (plano Optimizer §19).
MAX_ITERATIONS = 3


class ReviewLoop:
    """O laço de revisão do Optimizer (plano Optimizer §18)."""

    def __init__(
        self,
        *,
        reviewer: PixelReviewer | None = None,
        planner: RepairPlanner | None = None,
        executor: PixelToolExecutor | None = None,
        validator: PixelValidator | None = None,
        max_iterations: int = MAX_ITERATIONS,
    ) -> None:
        self._reviewer = reviewer or PixelReviewer()
        self._planner = planner or RepairPlanner()
        # ``None`` é o caminho normal: o executor é montado **por asset**, em
        # :meth:`run`, porque a guarda de paleta carrega o estado da paleta
        # daquele sprite — quantas cores já foram gastas e quais. Um executor
        # compartilhado entre jobs vazaria as cores de um asset para o
        # orçamento do seguinte.
        self._executor = executor
        self._validator = validator or PixelValidator()
        self._max_iterations = max(1, max_iterations)

    def run(
        self,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        validation: PixelValidationReport,
        *,
        log: ToolCallLog | None = None,
        logger: logging.Logger | None = None,
    ) -> OptimizationReport:
        """Corrige o canvas **no lugar** e devolve o relatório do que fez."""
        journal = log if log is not None else ToolCallLog()
        out = logger or _LOG
        executor = self._executor or PixelToolExecutor(palette=guard_for(spec, canvas))
        report = OptimizationReport(reviewer=self._reviewer.name)
        current = validation

        for iteration in range(1, self._max_iterations + 1):
            if iteration > 1:
                current = self._validator.validate(canvas.to_image(), spec, logger=out)

            review = self._reviewer.review(canvas, spec, current)
            report.reviews.append(review)

            if review.approved:
                report.status = (
                    OptimizationStatus.OPTIMIZED
                    if report.pixels_changed
                    else OptimizationStatus.SKIPPED
                )
                break

            plan = self._planner.plan(review, canvas, spec)
            report.plans.append(plan)

            if plan.is_empty:
                report.status = (
                    OptimizationStatus.OPTIMIZED
                    if report.pixels_changed
                    else OptimizationStatus.NO_SAFE_REPAIRS
                )
                out.debug(
                    "optimizer: %s problema(s) sem correção segura na volta %s",
                    len(review.issues),
                    iteration,
                )
                break

            before = journal.pixels_changed
            executor.execute_all(canvas, plan.actions, journal)
            changed = journal.pixels_changed - before

            report.iterations = iteration
            report.tool_calls = len(journal.records)
            report.pixels_changed = journal.pixels_changed
            report.status = OptimizationStatus.OPTIMIZED

            out.debug(
                "optimizer: volta %s — %s ação(ões), %s pixel(s) alterado(s)",
                iteration,
                len(plan.actions),
                changed,
            )

            if changed == 0:
                # O plano rodou e não mexeu em nada. Outra volta produziria o
                # mesmo plano e o mesmo nada.
                report.status = (
                    OptimizationStatus.OPTIMIZED
                    if report.pixels_changed
                    else OptimizationStatus.NO_SAFE_REPAIRS
                )
                break
        else:
            # As três voltas se esgotaram com problema ainda em aberto. Pode
            # ter havido correção — ``pixels_changed`` conta —, mas o estado
            # que interessa é este: o laço parou por teto, não por acerto.
            report.status = OptimizationStatus.EXHAUSTED

        return report


def guard_for(spec: PixelOutputSpec, canvas: PixelCanvas) -> PaletteGuard:
    """A guarda de paleta deste asset (plano Optimizer §16).

    Em paleta travada, as cores permitidas são as do **projeto** — não as que
    a imagem tem. É a diferença entre "só estas cores" e "as que já estão aí",
    e a segunda deixaria passar exatamente as intrusas que o reparo veio
    corrigir.
    """
    if spec.palette.is_locked:
        return PaletteGuard(spec.palette.colors, locked=True)
    return PaletteGuard(
        list(canvas.colors()), max_colors=spec.palette.effective_limit
    )
