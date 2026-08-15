"""Endpoints de capacidades e profiles (plano §51).

Este é o vocabulário que o frontend usa para montar a tela de geração:
capacidades disponíveis e profiles prontos — jamais nomes de modelo.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..deps import ServiceDep
from ..schemas import CapabilityResponse, ProfileSummary

router = APIRouter(prefix="/api/generation", tags=["capabilities"])


@router.get(
    "/capabilities",
    response_model=list[CapabilityResponse],
    summary="Capacidades conhecidas e quem as atende",
)
async def list_capabilities(service: ServiceDep) -> list[CapabilityResponse]:
    return [CapabilityResponse.model_validate(item) for item in service.capabilities()]


@router.get(
    "/profiles",
    response_model=list[ProfileSummary],
    summary="Generation Profiles disponíveis",
)
async def list_profiles(service: ServiceDep) -> list[ProfileSummary]:
    summaries: list[ProfileSummary] = []
    for profile in service.profiles():
        output = profile.output
        summaries.append(
            ProfileSummary(
                id=profile.id,
                display_name=profile.display_name or profile.id,
                capability=str(profile.capability),
                pipeline=profile.pipeline,
                asset_type=profile.asset.type.value,
                mode=profile.asset.mode.value,
                logical_size=(
                    (output.logical_width, output.logical_height)
                    if output.is_logical
                    else None
                ),
                render_size=(output.render_width, output.render_height),
                variations=output.variations,
                palette_size=profile.palette.size,
            )
        )
    return summaries


@router.get("/pipelines", response_model=list[str], summary="Pipelines registrados")
async def list_pipelines(service: ServiceDep) -> list[str]:
    return list(service.pipelines())
