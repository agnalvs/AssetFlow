"""A cópia de segurança de ``backend/data/`` pela tela (lote 9).

O mesmo de ``python -m assetflow.backup criar`` e ``listar``; restaurar fica só
no comando, porque exige a API fechada.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, status

from ...backup import Copia, ErroDaCopia, criar_copia, listar_copias, pasta_das_copias
from ...generation.kernel.exceptions import InvalidGenerationRequest
from ..deps import ContainerDep
from ..schemas import CopiasResponse, CopiaView

router = APIRouter(prefix="/api/backup", tags=["backup"])


def _vista(copia: Copia) -> CopiaView:
    return CopiaView(
        arquivo=str(copia.arquivo),
        nome=copia.arquivo.name,
        criada_em=copia.criada_em,
        tamanho=copia.tamanho,
        arquivos=copia.arquivos,
        commit=copia.commit,
    )


def _ligado(container) -> None:
    if not container.settings.backup.ligado:
        raise InvalidGenerationRequest(
            "a cópia de segurança pela tela está desligada (ASSETFLOW_BACKUP); "
            "o comando python -m assetflow.backup continua valendo"
        )


@router.get("", response_model=CopiasResponse, summary="As cópias de segurança da pasta")
async def listar(container: ContainerDep) -> CopiasResponse:
    _ligado(container)
    copias = await asyncio.to_thread(listar_copias, container.settings)
    return CopiasResponse(
        pasta=str(pasta_das_copias(container.settings)), items=[_vista(c) for c in copias]
    )


@router.post(
    "",
    response_model=CopiaView,
    status_code=status.HTTP_201_CREATED,
    summary="Grava uma cópia de backend/data/ fora do repositório",
)
async def criar(container: ContainerDep) -> CopiaView:
    _ligado(container)
    try:
        copia = await asyncio.to_thread(criar_copia, container.settings)
    except ErroDaCopia as exc:
        raise InvalidGenerationRequest(str(exc)) from exc
    return _vista(copia)
