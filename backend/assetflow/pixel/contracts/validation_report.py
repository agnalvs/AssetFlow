"""PixelValidationReport — o veredito técnico (plano Pixel §36 a §57).

A separação que dá nome a este arquivo:

``HARD VALIDATION``
    Requisitos objetivos. Se algum falhar, ``pixel_exact = False``. Não existe
    média que salve: um erro fatal não pode ser escondido por uma nota boa
    (plano Pixel §38).

``QUALITY ANALYSIS``
    Indicadores estruturais (pixels órfãos, microclusters, ocupação). Geram
    avisos e uma pontuação — **nunca** reprovam sozinhos (plano Pixel §47).

Um asset pode ser ``PIXEL EXACT: sim / QUALITY: 58`` (tecnicamente correto,
artisticamente problemático) ou ``PIXEL EXACT: não / QUALITY: 90`` (bonito,
fora da especificação). Guardar as duas coisas juntas destruiria a distinção
que o plano §57 e §107 chamam de essencial.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from ...generation.schemas import AssetFlowModel
from ..version import ACCEPTANCE_POLICY_VERSION, VALIDATOR_VERSION

__all__ = [
    "AcceptanceDecision",
    "CheckStatus",
    "HardCheckResult",
    "PixelAssetStatus",
    "PixelValidationReport",
    "QualityMetrics",
    "QualityReport",
    "QualityWarning",
    "TechnicalSummary",
]


class CheckStatus(str, Enum):
    """Resultado de um hard check."""

    PASS = "pass"
    FAIL = "fail"
    #: O profile desligou este requisito — não conta como aprovação.
    SKIPPED = "skipped"


class HardCheckResult(AssetFlowModel):
    """Um requisito obrigatório, medido (plano Pixel §40 a §46).

    ``expected``/``actual`` são strings legíveis de propósito: o relatório de
    falha precisa dizer ``esperado "<=16" / obtido "23"`` sem que quem lê
    precise decodificar estrutura (plano Pixel §62).
    """

    code: str
    name: str
    status: CheckStatus
    message: str = ""
    expected: str | None = None
    actual: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status is CheckStatus.FAIL


class QualityWarning(AssetFlowModel):
    """Um indicador estrutural digno de nota — nunca uma reprovação."""

    code: str
    message: str = ""
    count: int = 0
    severity: str = Field(default="warning", pattern=r"^(info|warning)$")
    detail: dict[str, Any] = Field(default_factory=dict)


class QualityMetrics(AssetFlowModel):
    """Números crus da análise estrutural (plano Pixel §48 a §55).

    São **indicadores**, não verdades artísticas: Pixel Art profissional usa
    pixels isolados de propósito (plano Pixel §51).
    """

    #: Pixels sem nenhum vizinho da mesma cor.
    orphan_pixel_count: int = 0
    orphan_pixel_ratio: float = 0.0
    orphan_positions: tuple[tuple[int, int], ...] = ()

    #: Componentes conexos por cor.
    cluster_total: int = 0
    single_pixel_clusters: int = 0
    two_pixel_clusters: int = 0
    three_pixel_clusters: int = 0
    microcluster_ratio: float = 0.0

    #: Ocupação do canvas pelo foreground.
    foreground_pixels: int = 0
    foreground_occupancy: float = 0.0
    bounding_box: tuple[int, int, int, int] | None = None
    touches_border: bool = False

    #: Frequência de cada cor final (plano Pixel §54).
    palette_usage: dict[str, int] = Field(default_factory=dict)
    rare_colors: tuple[str, ...] = ()

    #: Pares de cores quase indistinguíveis (plano Pixel §55).
    redundant_color_pairs: tuple[tuple[str, str], ...] = ()

    #: Contorno (plano Pixel §52).
    outline_pixels: int = 0
    outline_colors: tuple[str, ...] = ()
    outline_fragmentation: float = 0.0


class QualityReport(AssetFlowModel):
    """Análise estrutural com pontuação (plano Pixel §56)."""

    score: int = Field(default=100, ge=0, le=100)
    metrics: QualityMetrics = Field(default_factory=QualityMetrics)
    warnings: tuple[QualityWarning, ...] = ()
    #: Analisadores que rodaram — o score só é comparável entre relatórios
    #: produzidos pela mesma lista.
    analyzers: tuple[str, ...] = ()
    #: Quanto cada penalidade tirou da nota, para depurar o próprio score.
    penalties: dict[str, float] = Field(default_factory=dict)


class TechnicalSummary(AssetFlowModel):
    """O bloco ``technical`` do relatório (plano Pixel §56)."""

    size: str = "0x0"
    width: int = 0
    height: int = 0
    colors: int = 0
    alpha_values: tuple[int, ...] = ()


class PixelValidationReport(AssetFlowModel):
    """Relatório completo, serializado como ``validation.json`` (plano §75)."""

    validator_version: str = VALIDATOR_VERSION
    spec_id: str = "inline"
    spec_version: str = "1.0.0"

    pixel_exact: bool = False
    hard_checks: tuple[HardCheckResult, ...] = ()
    technical: TechnicalSummary = Field(default_factory=TechnicalSummary)
    quality: QualityReport = Field(default_factory=QualityReport)
    duration_ms: float = 0.0

    @property
    def failures(self) -> tuple[HardCheckResult, ...]:
        """Só os checks que reprovaram — o "por quê" do plano Pixel §62."""
        return tuple(check for check in self.hard_checks if check.failed)

    @property
    def hard_check_map(self) -> dict[str, str]:
        """``{"PX-DIM-001": "pass", ...}`` — o formato do plano Pixel §46."""
        return {check.code: check.status.value for check in self.hard_checks}


class PixelAssetStatus(str, Enum):
    """Estados oficiais de um asset Pixel (plano Pixel §58)."""

    RAW = "raw"
    PROCESSING = "processing"
    TECHNICALLY_VALID = "technically_valid"
    QUALITY_WARNING = "quality_warning"
    REJECTED = "rejected"
    APPROVED = "approved"


class AcceptanceDecision(AssetFlowModel):
    """Saída da PixelAcceptancePolicy (plano Pixel §59 e §60).

    A regra de aprovação mora na política, nunca no Validator: o Validator
    mede, a política decide. Trocar o limiar não pode exigir tocar em nenhum
    check.
    """

    status: PixelAssetStatus = PixelAssetStatus.RAW
    pixel_exact: bool = False
    quality_score: int = Field(default=0, ge=0, le=100)
    quality_threshold: int = Field(default=70, ge=0, le=100)
    policy_version: str = ACCEPTANCE_POLICY_VERSION
    #: Frases curtas explicando a decisão, em português, prontas para log.
    reasons: tuple[str, ...] = ()
    #: Cópia enxuta das falhas, para quem consome só a decisão (plano §62).
    failures: tuple[HardCheckResult, ...] = ()

    @property
    def accepted(self) -> bool:
        """Aprovado ou aprovado-com-ressalva — ou seja, entregável."""
        return self.status in (
            PixelAssetStatus.APPROVED,
            PixelAssetStatus.QUALITY_WARNING,
        )

    @property
    def rejected(self) -> bool:
        return self.status is PixelAssetStatus.REJECTED
