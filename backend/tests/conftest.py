"""Infraestrutura comum dos testes.

Os testes rodam sem GPU e sem rede: a gaveta `mock-image-v1` existe
exatamente para permitir isso (plano §69).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

import pytest

from assetflow.bootstrap import AppContainer, build_container
from assetflow.settings import Settings, load_settings

T = TypeVar("T")

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def run(coro: Awaitable[T]) -> T:
    """Executa uma corrotina em um loop próprio.

    Evita a dependência de ``pytest-asyncio``: cada teste é síncrono e
    controla explicitamente o seu loop.
    """
    return asyncio.run(coro)  # type: ignore[arg-type]


@pytest.fixture(name="run")
def run_fixture() -> Callable[[Awaitable[Any]], Any]:
    """Disponibiliza :func:`run` como fixture para os testes de contrato."""
    return run


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Configuração real do projeto, com dados isolados em ``tmp_path``."""
    return load_settings(base_dir=BACKEND_ROOT, data_dir=tmp_path)


@pytest.fixture
def container(settings: Settings) -> AppContainer:
    """Sistema completo montado, com o worker desligado.

    Desligar o worker embutido torna os testes determinísticos: quem decide
    quando um job roda é o teste, via ``worker.run_once()``.
    """
    settings.worker.embedded = False
    # Sem backoff: o retry é exercitado pelo comportamento, não pelo relógio.
    settings.worker.retry_base_delay_s = 0.0
    return build_container(settings)


@pytest.fixture
def make_request() -> Callable[..., Any]:
    """Fábrica de pedidos de asset."""
    from assetflow.generation.schemas import AssetGenerationRequest, AssetOutputOverrides

    def factory(**overrides: Any) -> AssetGenerationRequest:
        payload: dict[str, Any] = {
            "project_id": "project_test",
            "profile": "pixel_character_64",
            "prompt": "young warrior with blue armor",
            "attributes": {"view": "side", "pose": "idle"},
            "seed": 4242,
        }
        output = overrides.pop("output", None)
        payload.update(overrides)
        if output is not None:
            payload["output"] = (
                output
                if isinstance(output, AssetOutputOverrides)
                else AssetOutputOverrides.model_validate(output)
            )
        else:
            payload.setdefault("output", AssetOutputOverrides(variations=2))
        return AssetGenerationRequest.model_validate(payload)

    return factory


async def process_next_job(container: AppContainer, *, timeout: float = 5.0) -> bool:
    """Roda um job da fila com o worker do container."""
    return await container.worker.run_once(timeout=timeout)
