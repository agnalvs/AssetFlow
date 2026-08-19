"""Schemas de asset — a saída do AssetFlow, já do lado do produto.

Um *asset* é o que sobra depois que o resultado bruto do motor passou pelo
pipeline e pelo pós-processamento do AssetFlow. Ele pertence a um projeto e é
o que o editor, a biblioteca e a exportação enxergam.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from .common import AssetFlowModel, AssetMode, AssetType, new_id, utcnow
from .engine import EngineRef

__all__ = ["ValidationIssue", "ValidationReport", "AssetVariant", "GeneratedAsset"]


class ValidationIssue(AssetFlowModel):
    """Um achado do validador de pós-processamento."""

    code: str
    message: str
    severity: str = Field(default="warning", pattern=r"^(info|warning|error)$")
    context: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(AssetFlowModel):
    """Relatório de validação de um asset (grid, paleta, alpha...)."""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def with_issue(self, issue: ValidationIssue) -> "ValidationReport":
        return ValidationReport(issues=(*self.issues, issue))


class AssetVariant(AssetFlowModel):
    """Uma variação concreta gerada e persistida."""

    id: str = Field(default_factory=lambda: new_id("var"))
    index: int = Field(default=0, ge=0)
    uri: str
    thumbnail_uri: str | None = None
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    #: Resolução lógica do asset (Pixel Art). `None` para arte 2D convencional.
    logical_width: int | None = None
    logical_height: int | None = None
    seed: int | None = None
    color_count: int | None = None
    palette: tuple[str, ...] = ()
    validation: ValidationReport = Field(default_factory=ValidationReport)

    # -- Veredito Pixel Exact (plano Pixel §56, §58 e §79) ---------------
    # `None` em arte 2D convencional: lá a pergunta não faz sentido.
    #
    # Estes campos são o resumo — o relatório completo vai para os arquivos
    # `validation.json`/`processing.json` referenciados em `artifacts`. Note
    # que `pixel_exact` e `quality_score` moram separados de propósito: um
    # asset pode ser tecnicamente exato e artisticamente ruim, ou o contrário
    # (plano Pixel §57).
    pixel_exact: bool | None = None
    quality_score: int | None = None
    #: Valor de ``PixelAssetStatus`` (plano Pixel §58). Fica como `str` porque
    #: os schemas são a camada neutra e não podem importar `assetflow.pixel`.
    status: str | None = None
    #: Ampliação inteira só para visualização — nunca é o asset (plano Pixel §73).
    preview_uri: str | None = None
    #: ``{"raw.png": "assetflow-local://...", ...}`` (plano Pixel §70).
    artifacts: dict[str, str] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedAsset(AssetFlowModel):
    """Conjunto de variações produzidas por um job, já pronto para o projeto."""

    id: str = Field(default_factory=lambda: new_id("asset"))
    project_id: str
    job_id: str
    type: AssetType
    mode: AssetMode
    name: str = ""
    profile_id: str | None = None
    pipeline_id: str | None = None
    engine: EngineRef
    variants: tuple[AssetVariant, ...] = ()
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
