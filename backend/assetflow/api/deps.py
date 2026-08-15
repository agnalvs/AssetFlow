"""Injeção de dependências da API.

O container é montado uma vez no ``lifespan`` e fica em ``app.state``. Os
routers recebem apenas a fachada :class:`GenerationService` — nenhum router
enxerga registry, resolver ou engine.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from ..bootstrap import AppContainer
from ..generation.service import GenerationService

__all__ = ["get_container", "get_service", "ContainerDep", "ServiceDep"]


def get_container(request: Request) -> AppContainer:
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - erro de configuração
        raise RuntimeError("container não inicializado no lifespan da aplicação")
    return container


def get_service(request: Request) -> GenerationService:
    return get_container(request).service


ContainerDep = Annotated[AppContainer, Depends(get_container)]
ServiceDep = Annotated[GenerationService, Depends(get_service)]
