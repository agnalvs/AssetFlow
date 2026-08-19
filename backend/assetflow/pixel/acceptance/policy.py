"""PixelAcceptancePolicy — quem mede não é quem decide (plano Pixel §59 e §60).

O Validator produz números: ``pixel_exact``, a nota de qualidade e a lista de
hard checks. Ele nunca diz se o asset pode ser entregue. Essa regra mora aqui,
sozinha, por dois motivos do plano §59:

* mudar o limiar de aprovação — ou a política inteira — não pode obrigar a
  tocar em um único check;
* o mesmo relatório precisa poder ser julgado por políticas diferentes, senão
  o benchmark do §76 estaria comparando vereditos em vez de medidas.

A regra da versão 1.0 é a do plano §60::

    falha em hard check           -> REJECTED
    hard pass e nota >= limiar    -> APPROVED
    hard pass e nota <  limiar    -> QUALITY_WARNING

O limiar padrão 70 é **experimental** por decisão do próprio plano §60: foi
escolhido antes de existir amostra suficiente e vai ser recalibrado com os
benchmarks. Por isso ele é configuração (``validation.quality_threshold`` do
profile) e argumento de :meth:`PixelAcceptancePolicy.decide`, nunca uma
constante espalhada pelo código (§64).
"""

from __future__ import annotations

from ..contracts.validation_report import (
    AcceptanceDecision,
    HardCheckResult,
    PixelAssetStatus,
    PixelValidationReport,
)
from ..version import ACCEPTANCE_POLICY_VERSION

__all__ = ["PixelAcceptancePolicy"]


class PixelAcceptancePolicy:
    """Traduz um :class:`PixelValidationReport` em um status oficial (§58).

    Só três dos seis status do plano §58 saem daqui. ``RAW``, ``PROCESSING`` e
    ``TECHNICALLY_VALID`` descrevem o ciclo de vida do asset na camada de
    cima (job, storage) — a política olha um relatório pronto e responde
    apenas "entrega, entrega com ressalva ou não entrega".
    """

    version = ACCEPTANCE_POLICY_VERSION

    def __init__(self, quality_threshold: int = 70) -> None:
        self._quality_threshold = quality_threshold

    @property
    def quality_threshold(self) -> int:
        """Limiar padrão desta instância, usado quando ``decide`` não recebe um."""
        return self._quality_threshold

    # ------------------------------------------------------------------
    def decide(
        self,
        validation: PixelValidationReport,
        *,
        threshold: int | None = None,
    ) -> AcceptanceDecision:
        """Aplica a regra do plano §60 sobre um relatório já fechado.

        Args:
            validation: o veredito técnico do PixelValidator. Só é lido.
            threshold: limiar do profile em uso. Tem precedência sobre o do
                construtor, que é apenas o padrão de quem instanciou a
                política — o profile é quem conhece a exigência do asset.
        """
        limit = self._quality_threshold if threshold is None else threshold
        score = validation.quality.score
        failures = validation.failures

        # Um relatório que se declara não-exato sem listar nenhuma falha ainda
        # é uma reprovação: a política jamais aprova por ausência de evidência.
        if failures or not validation.pixel_exact:
            status = PixelAssetStatus.REJECTED
            reasons: tuple[str, ...] = (
                _rejection_summary(failures),
                *(_diagnostic(check) for check in failures),
            )
        elif score >= limit:
            status = PixelAssetStatus.APPROVED
            reasons = (
                "todos os requisitos obrigatórios passaram",
                f"qualidade {score} >= limiar {limit}",
            )
        else:
            status = PixelAssetStatus.QUALITY_WARNING
            reasons = (
                "todos os requisitos obrigatórios passaram",
                f"qualidade {score} < limiar {limit}: revisão manual recomendada",
            )

        warnings = validation.quality.warnings
        if warnings:
            # Avisos nunca reprovam (§47), mas precisam aparecer na decisão:
            # é o que separa "aprovado limpo" de "aprovado com ressalvas".
            reasons = (*reasons, f"{len(warnings)} aviso(s) de qualidade registrado(s)")

        return AcceptanceDecision(
            status=status,
            pixel_exact=validation.pixel_exact,
            quality_score=score,
            quality_threshold=limit,
            policy_version=self.version,
            reasons=reasons,
            failures=failures,
        )


def _rejection_summary(failures: tuple[HardCheckResult, ...]) -> str:
    """Primeira linha da reprovação, antes dos diagnósticos individuais."""
    if not failures:
        return "reprovado: o relatório não declara o asset como Pixel Exact"
    if len(failures) == 1:
        return "reprovado: 1 requisito obrigatório falhou"
    return f"reprovado: {len(failures)} requisitos obrigatórios falharam"


def _diagnostic(check: HardCheckResult) -> str:
    """O formato de diagnóstico do plano Pixel §62.

    ``"PX-COLOR-001: esperado <=16, obtido 23"``. A frase precisa dizer o que
    foi exigido e o que chegou sem obrigar quem lê o log a abrir o JSON do
    relatório — é por isso que ``expected``/``actual`` são strings prontas.
    """
    if check.expected is not None and check.actual is not None:
        return f"{check.code}: esperado {check.expected}, obtido {check.actual}"
    if check.actual is not None:
        return f"{check.code}: obtido {check.actual}"
    return f"{check.code}: {check.message or check.name}"
