"""Endpoints de motores (plano §51).

A API expõe a estante para diagnóstico e administração. Note que habilitar e
desabilitar uma gaveta é uma operação de runtime — é ela que sustenta o
"Engine Swap" sem reiniciar o backend.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...generation.schemas import ENGINE_API_VERSION, EngineDescriptor
from ..deps import ServiceDep
from ..schemas import EngineListResponse, EngineSummary

router = APIRouter(prefix="/api/generation/engines", tags=["engines"])


def _to_summary(descriptor: EngineDescriptor) -> EngineSummary:
    manifest = descriptor.manifest
    return EngineSummary(
        id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        engine_api_version=manifest.engine_api_version,
        provider=manifest.provider,
        description=manifest.description,
        state=descriptor.state.value,
        enabled=descriptor.enabled,
        api_compatible=descriptor.api_compatible,
        capabilities=tuple(str(capability) for capability in manifest.capabilities),
        supports=manifest.supports.model_dump(),
        limits=manifest.limits.model_dump(),
        resources=manifest.resources.model_dump(),
        health=descriptor.health.model_dump(mode="json") if descriptor.health else None,
        last_error=descriptor.last_error,
        source=descriptor.source,
    )


@router.get("", response_model=EngineListResponse, summary="Lista as gavetas instaladas")
async def list_engines(
    service: ServiceDep,
    include_health: bool = Query(default=True, description="Executa health check."),
) -> EngineListResponse:
    descriptors = await service.list_engines(include_health=include_health)
    return EngineListResponse(
        items=tuple(_to_summary(descriptor) for descriptor in descriptors),
        engine_api_version=ENGINE_API_VERSION,
    )


@router.get("/{engine_id}", response_model=EngineSummary, summary="Detalha uma gaveta")
async def get_engine(engine_id: str, service: ServiceDep) -> EngineSummary:
    return _to_summary(await service.get_engine(engine_id))


@router.post(
    "/{engine_id}/enable",
    response_model=EngineSummary,
    summary="Habilita uma gaveta em runtime",
)
async def enable_engine(engine_id: str, service: ServiceDep) -> EngineSummary:
    service.enable_engine(engine_id)
    return _to_summary(await service.get_engine(engine_id))


@router.post(
    "/{engine_id}/disable",
    response_model=EngineSummary,
    summary="Desabilita uma gaveta em runtime",
)
async def disable_engine(engine_id: str, service: ServiceDep) -> EngineSummary:
    service.disable_engine(engine_id)
    return _to_summary(await service.get_engine(engine_id))


@router.post(
    "/{engine_id}/reload",
    response_model=EngineSummary,
    summary="Descarrega o modelo e relê o manifesto",
)
async def reload_engine(engine_id: str, service: ServiceDep) -> EngineSummary:
    await service.reload_engine(engine_id)
    return _to_summary(await service.get_engine(engine_id))
