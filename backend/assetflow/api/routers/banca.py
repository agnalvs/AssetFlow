"""A banca de teste na tela (etapa K1 do plano da base de conhecimento).

    GET  /api/banca                 os itens e as rodadas, com o andamento
    POST /api/banca/rodadas         cria uma rodada (rótulo e modo de conceito)
    GET  /api/banca/comparar?a=&b=  os pares lado a lado, sem dizer o lado
    PUT  /api/banca/votos           a escolha e as duas notas de um par

O resumo só vem com todos os pares avaliados, e é ele que revela os lados.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query, status

from ...banca import Rodada, tokens_estimados
from ..deps import ContainerDep
from ..schemas import (
    AssetView,
    BancaView,
    ComparacaoView,
    LadoView,
    ParView,
    RodadaItemView,
    RodadaNova,
    RodadaView,
    VotoCorpo,
)
from .jobs import _url_resolver

router = APIRouter(prefix="/api/banca", tags=["banca"])

_FIM = {"pronto", "nao_aprovado", "cancelado"}


@router.get("", response_model=BancaView)
async def banca(container: ContainerDep) -> BancaView:
    servico = container.banca
    itens = [{"id": i.id, "texto": i.texto, "testa": i.testa} for i in servico.banca().itens]
    rodadas = [await _rodada(r, container) for r in await asyncio.to_thread(servico.rodadas)]
    return BancaView(itens=itens, rodadas=rodadas)


@router.post("/rodadas", response_model=RodadaView, status_code=status.HTTP_201_CREATED)
async def nova_rodada(corpo: RodadaNova, container: ContainerDep) -> RodadaView:
    rodada = await container.banca.criar_rodada(corpo.rotulo, corpo.modo_conceito)
    return await _rodada(rodada, container)


@router.get("/comparar", response_model=ComparacaoView)
async def comparar(
    container: ContainerDep, a: str = Query(...), b: str = Query(...)
) -> ComparacaoView:
    dados = await container.banca.comparar(a, b)
    pares = []
    for par in dados["pares"]:
        voto = par["voto"]
        pares.append(
            ParView(
                item=par["item"],
                texto=par["texto"],
                testa=par["testa"],
                esquerda=await _lado(par["esquerda"], container),
                direita=await _lado(par["direita"], container),
                escolha=voto.escolha if voto else None,
                nota_esquerda=voto.nota_esquerda if voto else None,
                nota_direita=voto.nota_direita if voto else None,
            )
        )
    return ComparacaoView(
        a=dados["a"], b=dados["b"], pares=pares, avaliados=dados["avaliados"], resumo=dados["resumo"]
    )


@router.put("/votos", status_code=status.HTTP_204_NO_CONTENT)
async def votar(corpo: VotoCorpo, container: ContainerDep) -> None:
    await asyncio.to_thread(
        container.banca.votar,
        corpo.a, corpo.b, corpo.item, corpo.escolha, corpo.nota_esquerda, corpo.nota_direita,
    )


async def _lado(pedido, container) -> LadoView:
    if pedido is None:
        return LadoView()
    asset = None
    if pedido.situacao.value == "concluido":
        gerado = await container.pedidos.asset(pedido.asset_projeto, pedido.job_id)
        if gerado is not None:
            asset = AssetView.from_asset(gerado, _url_resolver(container))
    from ...pedidos import agora_utc

    return LadoView(asset=asset, etapa=pedido.etapa(agora_utc()).value)


async def _rodada(rodada: Rodada, container) -> RodadaView:
    from ...pedidos import agora_utc

    pedidos = await asyncio.to_thread(container.banca.pedidos_da_rodada, rodada)
    agora = agora_utc()
    itens = []
    for entrada in rodada.itens:
        pedido = pedidos.get(entrada["item"])
        itens.append(
            RodadaItemView(
                item=entrada["item"],
                pedido_id=entrada["pedido_id"],
                ordem=entrada["ordem"],
                etapa=pedido.etapa(agora).value if pedido else None,
                asset_id=pedido.asset_id if pedido else None,
            )
        )
    return RodadaView(
        id=rodada.id,
        rotulo=rodada.rotulo,
        modo_conceito=rodada.modo_conceito,
        criada_em=rodada.criada_em,
        versao_base=rodada.versao_base,
        git_commit=rodada.git_commit,
        interruptores=rodada.interruptores,
        licoes=rodada.licoes,
        itens=itens,
        pronta=bool(itens) and all(i.etapa in _FIM for i in itens),
        tokens_estimados=sum(tokens_estimados(p.custo) for p in pedidos.values() if p),
    )
