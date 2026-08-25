"""Aplicação FastAPI do AssetFlow (plano §51).

A API é uma casca fina: valida entrada, chama a fachada
:class:`~assetflow.generation.service.GenerationService` e devolve DTOs.
Ela não conhece registry, resolver, engine ou modelo.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..bootstrap import AppContainer, build_container
from ..generation.kernel.exceptions import ErrorCode, GenerationError
from ..settings import Settings
from ..version import __version__
from .routers import (
    assets,
    capabilities,
    dev_pixel,
    engines,
    jobs,
    prompt,
    strategies,
)
from .schemas import ErrorResponse, HealthResponse

__all__ = ["create_app"]

_LOG = logging.getLogger("assetflow.api")

#: Tradução de erro normalizado -> status HTTP. Um motor novo nunca precisa
#: acrescentar nada aqui: ele fala o mesmo vocabulário de erros.
_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 400,
    ErrorCode.CAPABILITY_NOT_SUPPORTED: 400,
    ErrorCode.JOB_NOT_FOUND: 404,
    ErrorCode.PROFILE_NOT_FOUND: 404,
    ErrorCode.PIPELINE_NOT_FOUND: 404,
    ErrorCode.ENGINE_NOT_FOUND: 404,
    ErrorCode.ENGINE_DISABLED: 409,
    ErrorCode.ENGINE_INCOMPATIBLE: 409,
    ErrorCode.NO_ENGINE_AVAILABLE: 503,
    ErrorCode.ENGINE_UNAVAILABLE: 503,
    ErrorCode.ENGINE_TIMEOUT: 504,
    ErrorCode.ENGINE_OUT_OF_MEMORY: 503,
    ErrorCode.ENGINE_INITIALIZATION_FAILED: 503,
    ErrorCode.ENGINE_EXECUTION_FAILED: 502,
    ErrorCode.CANCELLED: 409,
    ErrorCode.POSTPROCESSING_FAILED: 500,
    ErrorCode.STORAGE_FAILED: 500,
    ErrorCode.INTERNAL: 500,
}


def create_app(
    settings: Settings | None = None, *, container: AppContainer | None = None
) -> FastAPI:
    """Cria a aplicação.

    Args:
        settings: configuração explícita (senão, carregada de YAML/ambiente).
        container: container pronto — usado pelos testes para injetar um
            sistema montado à mão, sem tocar em disco de produção.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_container = container or build_container(settings)
        app.state.container = app_container
        await app_container.startup()
        _LOG.info("AssetFlow API iniciada (v%s)", __version__)
        try:
            yield
        finally:
            await app_container.shutdown()
            _LOG.info("AssetFlow API encerrada")

    resolved_settings = settings or (container.settings if container else None)
    api_settings = resolved_settings.api if resolved_settings else None

    app = FastAPI(
        title=api_settings.title if api_settings else "AssetFlow Generation API",
        version=__version__,
        description=(
            "API de geração de assets do AssetFlow. O cliente pede uma "
            "**capacidade** (ex.: `text_to_image.pixel`) ou um **profile**; "
            "qual motor executa é decisão do EngineResolver."
        ),
        root_path=api_settings.root_path if api_settings else "",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(api_settings.cors_origins) if api_settings else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(GenerationError)
    async def _generation_error_handler(
        _request: Request, exc: GenerationError
    ) -> JSONResponse:
        status_code = _STATUS_BY_CODE.get(exc.code, 500)
        if status_code >= 500:
            _LOG.error("erro de geração: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(
                code=exc.code.value,
                message=exc.message,
                retryable=exc.retryable,
                engine_id=exc.engine_id,
                detail=exc.detail,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """422 no mesmo formato normalizado dos outros erros da API.

        O padrão do FastAPI devolve ``{"detail": [...]}``, que quebra a
        promessa de ``{code, message}`` que o resto da API cumpre — o cliente
        cai no caso genérico e mostra "não conseguimos concluir" para um erro
        que ele sabe corrigir. Com o painel de prompt editável isso deixou de
        ser detalhe: quem escreveu um JSON fora do contrato precisa saber
        **qual campo** está errado, não que algo deu errado.
        """
        errors = [
            {
                "campo": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
                "erro": error.get("msg", ""),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                code="invalid_request",
                message="O corpo do pedido não bate com o contrato da API.",
                retryable=False,
                detail={"errors": errors},
            ).model_dump(mode="json"),
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    async def health(request: Request) -> HealthResponse:
        app_container: AppContainer = request.app.state.container
        engine_health = await app_container.registry.health()
        return HealthResponse(
            status="ok",
            version=__version__,
            engines={
                engine_id: value.status.value for engine_id, value in engine_health.items()
            },
            queued_jobs=await app_container.job_queue.size(
                app_container.jobs.router.default
            ),
        )

    # Métodos antes de motores: é a ordem em que a tela pergunta, e a
    # ordem em que o plano de correção desenha a arquitetura.
    app.include_router(strategies.router)
    app.include_router(engines.router)
    app.include_router(capabilities.router)
    app.include_router(prompt.router)
    app.include_router(jobs.router)
    app.include_router(assets.router)

    # Diagnóstico do Pixel Exact (plano Pixel §78). Quem decide se ele
    # responde é o próprio endpoint, lendo `api.dev_endpoints` do container em
    # tempo de requisição — aqui a configuração pode nem estar carregada
    # ainda. Desligado, ele devolve 404 e some da documentação; o fluxo normal
    # de geração continua sendo `POST /api/generation/jobs` (plano Pixel §77).
    app.include_router(
        dev_pixel.router,
        include_in_schema=bool(api_settings and api_settings.dev_endpoints),
    )
    return app
