"""As métricas do benchmark (plano de motores §20 e §21).

O §21 é a parte que mais importa deste módulo, e ele diz uma coisa que é fácil
de esquecer na hora de montar uma tabela: **"engine bonito" e "engine exato"
são dois eixos diferentes**, e misturá-los produz um ranking que não significa
nada.

Então as métricas aqui vêm separadas em dois blocos:

:class:`TechnicalMetrics`
    O que o AssetFlow **mede sozinho**: resolução lógica entregue, contagem de
    cores, alpha, órfãos, microclusters, ocupação, nota do PixelValidator,
    quanto o pós-processamento precisou corrigir, tempo, falhas.
:class:`VisualScore`
    O que só uma pessoa responde: composição, design, legibilidade, estilo. O
    módulo carrega o campo e **não** o preenche. Inventar aqui um número para
    "qualidade da silhueta" a partir de heurísticas daria à opinião a aparência
    de medição, que é pior do que deixar o campo vazio.

A quantidade de correção exigida pelo pós-processamento (§20) é a métrica mais
reveladora das automáticas, e é a que quase nunca se olha: um motor cuja saída
precisa de pouca correção está mais perto de entender pixel art do que um
motor bonito que o PixelPostProcessor teve de reconstruir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "TechnicalMetrics",
    "VisualScore",
    "CaseOutcome",
    "EngineReport",
    "BenchmarkReport",
]


@dataclass(frozen=True, slots=True)
class TechnicalMetrics:
    """O que o sistema mede sozinho, por variação gerada."""

    logical_size: tuple[int, int] | None = None
    requested_logical_size: tuple[int, int] | None = None
    color_count: int | None = None
    max_colors: int | None = None
    pixel_exact: bool | None = None
    quality_score: int | None = None
    status: str | None = None
    orphan_ratio: float | None = None
    microcluster_ratio: float | None = None
    foreground_occupancy: float | None = None
    #: Cores da saída crua do motor, antes da quantização.
    raw_color_count: int | None = None
    #: Tamanho em que o motor entregou, antes da redução lógica.
    raw_size: tuple[int, int] | None = None

    @property
    def size_matches(self) -> bool | None:
        """A resolução lógica entregue é a pedida?"""
        if self.logical_size is None or self.requested_logical_size is None:
            return None
        return self.logical_size == self.requested_logical_size

    @property
    def palette_within_budget(self) -> bool | None:
        if self.color_count is None or self.max_colors is None:
            return None
        return self.color_count <= self.max_colors

    @property
    def correction_ratio(self) -> float | None:
        """Quanto o pós-processamento precisou apertar a paleta (§20).

        ``1 - final/bruto``. Perto de 0, o motor já entregou algo próximo do
        orçamento de cores; perto de 1, o AssetFlow reconstruiu a paleta
        inteira. É a medida de "quanta correção este motor exigiu".
        """
        if not self.raw_color_count or self.color_count is None:
            return None
        if self.raw_color_count <= 0:
            return None
        return max(0.0, 1.0 - (self.color_count / self.raw_color_count))

    def document(self) -> dict[str, Any]:
        return {
            "logical_size": list(self.logical_size) if self.logical_size else None,
            "requested_logical_size": (
                list(self.requested_logical_size) if self.requested_logical_size else None
            ),
            "size_matches": self.size_matches,
            "color_count": self.color_count,
            "max_colors": self.max_colors,
            "palette_within_budget": self.palette_within_budget,
            "pixel_exact": self.pixel_exact,
            "quality_score": self.quality_score,
            "status": self.status,
            "orphan_ratio": self.orphan_ratio,
            "microcluster_ratio": self.microcluster_ratio,
            "foreground_occupancy": self.foreground_occupancy,
            "raw_color_count": self.raw_color_count,
            "raw_size": list(self.raw_size) if self.raw_size else None,
            "correction_ratio": self.correction_ratio,
        }


@dataclass(frozen=True, slots=True)
class VisualScore:
    """A avaliação humana (plano de motores §20 e §21).

    Preenchida à mão, depois de olhar os assets. Fica no mesmo relatório que
    as métricas técnicas — lado a lado, nunca somada a elas.
    """

    fidelity: int | None = None
    silhouette: int | None = None
    clusters: int | None = None
    outline: int | None = None
    readability: int | None = None
    reviewer: str | None = None

    @property
    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.fidelity,
                self.silhouette,
                self.clusters,
                self.outline,
                self.readability,
            )
        )

    def document(self) -> dict[str, Any]:
        return {
            "fidelity": self.fidelity,
            "silhouette": self.silhouette,
            "clusters": self.clusters,
            "outline": self.outline,
            "readability": self.readability,
            "reviewer": self.reviewer,
            "pending": self.is_empty,
        }


@dataclass(slots=True)
class CaseOutcome:
    """O resultado de um caso em um motor."""

    case_id: str
    engine_id: str
    #: O motor que realmente rodou. Diferente de ``engine_id`` significa que
    #: houve fallback — e um caso com fallback **não** conta para o motor
    #: pedido, senão o benchmark credita a um motor o trabalho de outro.
    resolved_engine_id: str | None = None
    succeeded: bool = False
    error: str | None = None
    duration_ms: float = 0.0
    inference_ms: float = 0.0
    postprocess_ms: float = 0.0
    technical: TechnicalMetrics = field(default_factory=TechnicalMetrics)
    visual: VisualScore = field(default_factory=VisualScore)
    asset_uri: str | None = None
    preview_uri: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def counts_for_engine(self) -> bool:
        """Este resultado pode ser creditado ao motor pedido?"""
        if not self.succeeded:
            return False
        if self.resolved_engine_id is None:
            return True
        return self.resolved_engine_id == self.engine_id

    def document(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "engine_id": self.engine_id,
            "resolved_engine_id": self.resolved_engine_id,
            "succeeded": self.succeeded,
            "counts_for_engine": self.counts_for_engine,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "inference_ms": round(self.inference_ms, 2),
            "postprocess_ms": round(self.postprocess_ms, 2),
            "technical": self.technical.document(),
            "visual": self.visual.document(),
            "asset_uri": self.asset_uri,
            "preview_uri": self.preview_uri,
            "warnings": list(self.warnings),
        }


@dataclass(slots=True)
class EngineReport:
    """O agregado de um motor sobre a suíte inteira."""

    engine_id: str
    outcomes: list[CaseOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def succeeded(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.counts_for_engine)

    @property
    def failure_rate(self) -> float:
        """Taxa de falha do §20. Fallback conta como falha do motor pedido.

        E tem de contar: se o motor não conseguiu atender e outro atendeu por
        ele, o pedido foi entregue mas **aquele** motor falhou. Contar o
        fallback como sucesso esconderia exatamente o que o benchmark procura.
        """
        if not self.total:
            return 0.0
        return 1.0 - (self.succeeded / self.total)

    def _values(self, attribute: str) -> list[float]:
        values: list[float] = []
        for outcome in self.outcomes:
            if not outcome.counts_for_engine:
                continue
            value = getattr(outcome.technical, attribute, None)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        return values

    def average(self, attribute: str) -> float | None:
        values = self._values(attribute)
        return sum(values) / len(values) if values else None

    @property
    def average_duration_ms(self) -> float | None:
        values = [
            outcome.duration_ms for outcome in self.outcomes if outcome.counts_for_engine
        ]
        return sum(values) / len(values) if values else None

    @property
    def pixel_exact_rate(self) -> float | None:
        counted = [
            outcome for outcome in self.outcomes if outcome.counts_for_engine
        ]
        if not counted:
            return None
        exact = sum(1 for outcome in counted if outcome.technical.pixel_exact)
        return exact / len(counted)

    def document(self) -> dict[str, Any]:
        return {
            "engine_id": self.engine_id,
            "cases": self.total,
            "succeeded": self.succeeded,
            "failure_rate": round(self.failure_rate, 4),
            "average_duration_ms": (
                round(self.average_duration_ms, 2)
                if self.average_duration_ms is not None
                else None
            ),
            "average_quality_score": _rounded(self.average("quality_score"), 2),
            "pixel_exact_rate": _rounded(self.pixel_exact_rate, 4),
            "average_correction_ratio": _rounded(self.average("correction_ratio"), 4),
            "average_orphan_ratio": _rounded(self.average("orphan_ratio"), 4),
            "average_microcluster_ratio": _rounded(
                self.average("microcluster_ratio"), 4
            ),
            "average_occupancy": _rounded(self.average("foreground_occupancy"), 4),
            "outcomes": [outcome.document() for outcome in self.outcomes],
        }


@dataclass(slots=True)
class BenchmarkReport:
    """O relatório completo: um bloco por motor."""

    engines: list[EngineReport] = field(default_factory=list)
    suite_size: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_engine(self, engine_id: str) -> EngineReport:
        for report in self.engines:
            if report.engine_id == engine_id:
                return report
        report = EngineReport(engine_id=engine_id)
        self.engines.append(report)
        return report

    def document(self) -> dict[str, Any]:
        return {
            "suite_size": self.suite_size,
            "metadata": self.metadata,
            # A separação do §21 aparece no próprio documento: quem ler o JSON
            # vê que a nota visual é um campo à parte, e que ele está vazio até
            # alguém olhar os assets.
            "axes": {
                "technical": "medido pelo AssetFlow (PixelPostProcessor + PixelValidator)",
                "visual": "avaliação humana; preenchida à mão, nunca inferida",
            },
            "engines": [report.document() for report in self.engines],
        }


def _rounded(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)
