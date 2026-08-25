"""Endpoint dos métodos de criação (plano de correção §32).

O nível acima de ``/engines``. A tela pergunta aqui **como** criar; só depois,
e só quando o método usar motor, ela pergunta **com o quê**.

Uma chamada só devolve as três listas — métodos, motores e agentes — porque a
tela precisa das três ao mesmo tempo para decidir o que mostrar. E quem decide
é o backend: cada método vem com ``selects_engine`` e ``selects_agent``, em vez
de o frontend inferir isso de um ``if id == 'pixel_agent'`` (plano §5).
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from ...generation.pixel_agent import AGENT_ID, AGENT_VERSION
from ...generation.schemas import AgentQualityMode
from ..deps import ServiceDep
from ..schemas import AgentSummary, StrategyCatalogResponse

router = APIRouter(prefix="/api/generation/strategies", tags=["strategies"])


@router.get(
    "",
    response_model=StrategyCatalogResponse,
    summary="Métodos de criação (o que o seletor 'Método de criação' usa)",
)
async def list_strategies(
    service: ServiceDep,
    capability: str | None = Query(
        default=None,
        description="Filtra os motores pelos que atendem esta capacidade.",
    ),
) -> StrategyCatalogResponse:
    strategies = await service.strategy_catalog(capability=capability)
    engines = await service.engine_catalog(capability=capability)

    return StrategyCatalogResponse(
        items=tuple(strategies),
        engines=tuple(engines),
        agents=(
            AgentSummary(
                id=AGENT_ID,
                display_name="AssetFlow Pixel Agent",
                version=AGENT_VERSION,
                summary=(
                    "Planeja o desenho, pinta com ferramentas na própria grade "
                    "e revisa o resultado."
                ),
            ),
        ),
        # `auto` incluído: é o padrão do controle de qualidade, e deixá-lo de
        # fora obrigaria a tela a acrescentá-lo por conta própria.
        quality_modes=tuple(mode.value for mode in AgentQualityMode),
        capability=capability,
    )
