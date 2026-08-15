"""Entrega dos arquivos gerados e do histórico.

Em produção com storage remoto, este router some e as URIs viram URLs
assinadas do bucket — nada acima muda, porque quem resolve URI é o
AssetStorageService.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from ...generation.kernel.exceptions import StorageError
from ...storage.backends.local import LOCAL_URI_SCHEME
from ..deps import ContainerDep, ServiceDep

router = APIRouter(prefix="/api/assets", tags=["assets"])

_CONTENT_TYPES = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".json": "application/json",
}


@router.get("/history", summary="Histórico de gerações do projeto")
async def history(
    service: ServiceDep,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    records = await service.history(project_id=project_id, limit=limit, offset=offset)
    return [record.model_dump(mode="json") for record in records]


@router.get("/files/{key:path}", summary="Baixa um arquivo gerado")
async def get_file(key: str, container: ContainerDep) -> Response:
    if not container.settings.api.serve_local_assets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="entrega local desabilitada"
        )
    try:
        data = await container.storage.backend.get(key)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    suffix = key[key.rfind(".") :].lower() if "." in key else ""
    return Response(content=data, media_type=_CONTENT_TYPES.get(suffix, "application/octet-stream"))


@router.get("/resolve", summary="Converte uma URI de asset em caminho público")
async def resolve_uri(uri: str, container: ContainerDep) -> dict[str, str | None]:
    key = container.storage.backend.key_from_uri(uri)
    return {
        "uri": uri,
        "scheme": LOCAL_URI_SCHEME,
        "key": key,
        "url": f"/api/assets/files/{key}" if key else None,
    }
