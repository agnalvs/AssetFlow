"""Pedidos da fila (Fase B do plano do app).

A tela não cria jobs: ela cria **pedidos**. Um pedido espera na fila até o
Claude, pela conversa, pegá-lo com ``pedidos_pendentes`` e desenhá-lo com
``desenhar(pedido_id=...)``. A tela acompanha pela lista.

    POST /api/pedidos/previa          o que a tela mostra antes de pedir
    POST /api/pedidos                 cria (201)
    GET  /api/pedidos                 lista do projeto, do mais novo
    GET  /api/pedidos/{id}            o pedido inteiro
    POST /api/pedidos/{id}/cancelar   pendente ou em desenho -> cancelado (409 se não)
    POST /api/pedidos/{id}/devolver   em desenho -> pendente, sem cancelar (409 se não)

A pré-visualização e a criação montam o mesmo pedido de geração
(``ServicoDePedidos.requisicao``): o spec que a tela mostra é o que fica
gravado, e o que o desenho executa.

A fila é um SQLite que o servidor MCP também usa. Cada operação roda numa
thread, porque o SQLite pode esperar o outro processo (``busy_timeout``).
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, status

from ...generation.schemas import PromptPreview
from ...pedidos import CorpoDoPedido, Pedido, Situacao, agora_utc
from ..deps import ContainerDep
from ..schemas import (
    AssetView,
    PedidoDetalhe,
    PedidoEventoView,
    PedidoListResponse,
    PedidoResumo,
    PedidoView,
)
from .jobs import _url_resolver

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


@router.post(
    "/previa",
    response_model=PromptPreview,
    summary="O que o AssetFlow entenderia deste pedido, com o gerador do app",
)
async def previa(corpo: CorpoDoPedido, container: ContainerDep) -> PromptPreview:
    return container.pedidos.previa(corpo)


@router.post(
    "",
    response_model=PedidoDetalhe,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um pedido na fila",
)
async def criar(corpo: CorpoDoPedido, container: ContainerDep) -> PedidoDetalhe:
    pedido = await container.pedidos.criar(corpo)
    return await _detalhe(pedido, container)


@router.get("", response_model=PedidoListResponse, summary="Pedidos do projeto")
async def listar(
    container: ContainerDep,
    projeto: str | None = Query(default=None),
    situacao: Annotated[list[Situacao] | None, Query()] = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> PedidoListResponse:
    alvo = projeto or container.pedidos.projeto
    pedidos = await asyncio.to_thread(
        container.pedidos.fila.listar,
        projeto=alvo,
        situacoes=tuple(situacao or ()),
        limite=limit,
    )
    agora = agora_utc()
    itens = [await _vista(pedido, container, agora) for pedido in pedidos]
    return PedidoListResponse(projeto=alvo, items=itens)


@router.get("/{pedido_id}", response_model=PedidoDetalhe, summary="Um pedido inteiro")
async def detalhe(pedido_id: str, container: ContainerDep) -> PedidoDetalhe:
    pedido = await asyncio.to_thread(container.pedidos.fila.obter, pedido_id)
    return await _detalhe(pedido, container)


@router.post("/{pedido_id}/cancelar", response_model=PedidoView, summary="Cancela um pedido")
async def cancelar(pedido_id: str, container: ContainerDep) -> PedidoView:
    pedido = await asyncio.to_thread(container.pedidos.fila.cancelar, pedido_id)
    return await _vista(pedido, container, agora_utc())


@router.post(
    "/{pedido_id}/devolver",
    response_model=PedidoView,
    summary="Devolve à fila um pedido em desenho, sem cancelar",
)
async def devolver(pedido_id: str, container: ContainerDep) -> PedidoView:
    pedido = await asyncio.to_thread(container.pedidos.fila.devolver, pedido_id)
    return await _vista(pedido, container, agora_utc())


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
async def _vista(pedido: Pedido, container, agora) -> PedidoView:
    return PedidoView(**await _campos(pedido, container, agora))


async def _detalhe(pedido: Pedido, container) -> PedidoDetalhe:
    campos = await _campos(pedido, container, agora_utc())
    return PedidoDetalhe(
        **campos,
        corpo=pedido.corpo,
        leitura=pedido.leitura,
        eventos=[
            PedidoEventoView(em=evento.em, situacao=evento.situacao.value, nota=evento.nota)
            for evento in pedido.eventos
        ],
        ultimo_laudo=pedido.ultimo_laudo,
    )


async def _campos(pedido: Pedido, container, agora) -> dict:
    asset = None
    gerado = await container.pedidos.asset(pedido.asset_projeto, pedido.job_id)
    if gerado is not None:
        asset = AssetView.from_asset(gerado, _url_resolver(container))
    return {
        "id": pedido.id,
        "tipo": pedido.tipo.value,
        "situacao": pedido.situacao.value,
        "etapa": pedido.etapa(agora).value,
        "texto": pedido.texto,
        "projeto": pedido.projeto,
        "liberdade": pedido.liberdade.value,
        "direcao_de_arte": pedido.direcao_de_arte,
        "origem_asset_id": pedido.origem_asset_id,
        "tentativas": pedido.tentativas,
        "max_tentativas": pedido.max_tentativas,
        "reservado_ate": pedido.reservado_ate,
        "motivo": pedido.motivo,
        "criado_em": pedido.criado_em,
        "atualizado_em": pedido.atualizado_em,
        "resumo": _resumo(pedido),
        "asset": asset,
    }


def _resumo(pedido: Pedido) -> PedidoResumo:
    spec = pedido.leitura.get("resolved") or {}
    logica = spec.get("logical_resolution") or {}
    paleta = spec.get("palette") or {}
    cores = paleta.get("max_colors") or (len(paleta.get("colors") or []) or None)
    return PedidoResumo(
        tipo_asset=(spec.get("asset") or {}).get("type"),
        grade=f"{logica['width']}×{logica['height']}" if logica.get("width") else None,
        cores=cores,
        fundo=(spec.get("background") or {}).get("mode"),
    )
