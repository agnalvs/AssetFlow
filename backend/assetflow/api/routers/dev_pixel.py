"""Endpoint de diagnóstico do Pixel Exact (plano Pixel §78).

Existe para **pesquisa**: mandar uma imagem qualquer e receber de volta o
relatório de validação, ou o resultado completo do processamento, sem passar
por um job de geração. É o que torna possível medir "quão longe do Pixel
Exact" está a saída de um motor novo antes de integrá-lo.

Três decisões conscientes:

1. **Desligado por padrão.** Só entra na aplicação quando
   ``ASSETFLOW_DEV_ENDPOINTS=1``. O plano §77 é explícito: o fluxo normal
   continua sendo ``POST /api/generation/jobs``, e este endpoint não pode
   virar uma porta paralela de processamento em produção.
2. **Imagem em base64, no corpo JSON.** Upload multipart exigiria uma
   dependência nova (``python-multipart``) por causa de um endpoint de
   diagnóstico.
3. **Nada é persistido.** A resposta é o relatório; nenhum asset entra no
   projeto, nenhum arquivo é gravado.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import Field

from ...generation.schemas import AssetFlowModel
from ...pixel import PixelAssetProcessor, PixelValidator
from ...pixel.contracts import PixelOutputSpec
from ...pixel.imaging import decode
from ..deps import ContainerDep

router = APIRouter(prefix="/api/dev/pixel", tags=["dev"])

_MAX_IMAGE_BYTES = 16 * 1024 * 1024


class PixelAnalyzeRequest(AssetFlowModel):
    """Imagem + contrato a conferir."""

    #: PNG/JPEG em base64 (com ou sem prefixo ``data:image/png;base64,``).
    image_base64: str
    #: Profile Pixel de ``config/pixel_profiles.yaml``.
    profile: str | None = None
    #: Alternativa ao profile: o spec inteiro, inline.
    spec: PixelOutputSpec | None = None
    #: ``True`` processa antes de validar (o caminho real do pipeline);
    #: ``False`` valida a imagem exatamente como ela chegou.
    process: bool = False


class PixelAnalyzeResponse(AssetFlowModel):
    """Relatórios devolvidos ao pesquisador."""

    spec_id: str
    pixel_exact: bool
    quality_score: int
    status: str | None = None
    validation: dict[str, Any] = Field(default_factory=dict)
    processing: dict[str, Any] | None = None
    acceptance: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


@router.post(
    "/analyze",
    response_model=PixelAnalyzeResponse,
    summary="Analisa uma imagem contra um contrato Pixel Exact",
)
async def analyze(payload: PixelAnalyzeRequest, container: ContainerDep) -> PixelAnalyzeResponse:
    if not container.settings.api.dev_endpoints:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="endpoints de desenvolvimento desabilitados",
        )

    spec = _resolve_spec(payload, container)
    image = _decode_image(payload.image_base64)

    if payload.process:
        outcome = PixelAssetProcessor().run(image, spec, export=False)
        return PixelAnalyzeResponse(
            spec_id=spec.id,
            pixel_exact=outcome.pixel_exact,
            quality_score=outcome.quality_score,
            status=outcome.decision.status.value,
            validation=outcome.validation.model_dump(mode="json"),
            processing=outcome.processing.model_dump(mode="json"),
            acceptance=outcome.decision.model_dump(mode="json"),
            metrics=outcome.metrics,
        )

    report = PixelValidator().validate(image, spec)
    return PixelAnalyzeResponse(
        spec_id=spec.id,
        pixel_exact=report.pixel_exact,
        quality_score=report.quality.score,
        validation=report.model_dump(mode="json"),
    )


def _resolve_spec(payload: PixelAnalyzeRequest, container: ContainerDep) -> PixelOutputSpec:
    if payload.spec is not None:
        return payload.spec
    if payload.profile:
        spec = container.pixel_profiles.find(payload.profile)
        if spec is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"profile Pixel '{payload.profile}' não existe; "
                    f"disponíveis: {', '.join(container.pixel_profiles.ids())}"
                ),
            )
        return spec
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="informe 'profile' ou 'spec'",
    )


def _decode_image(raw: str):
    """Base64 -> imagem RGBA, com erro claro em vez de stack trace."""
    payload = raw.split(",", 1)[-1] if raw.startswith("data:") else raw
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"imagem base64 inválida: {exc}",
        ) from exc

    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="imagem vazia"
        )
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"imagem acima do limite de {_MAX_IMAGE_BYTES // (1024 * 1024)}MB",
        )

    try:
        return decode(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"não foi possível abrir a imagem: {exc}",
        ) from exc
