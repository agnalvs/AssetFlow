"""O painel de custo da tela (lote 12): tokens estimados por pedido e por dia.

A conta é a estimativa de ``assetflow/pedidos/custo.py`` sobre os eventos que
o servidor MCP grava na fila. O limite diário avisa (aqui e nas respostas do
MCP) e não bloqueia nada.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Query

from ...generation.kernel.exceptions import InvalidGenerationRequest
from ...pedidos import ErroDaFila
from ...pedidos.custo import inicio_do_dia, por_dia, tokens_estimados
from ..deps import ContainerDep

router = APIRouter(prefix="/api/custo", tags=["custo"])


@router.get("", summary="Tokens estimados por dia e por pedido, e o limite diário")
async def custo(
    container: ContainerDep,
    dias: Annotated[int, Query(ge=1, le=60)] = 7,
) -> dict:
    config = container.settings.custo
    if not config.painel:
        raise InvalidGenerationRequest("o painel de custo está desligado (ASSETFLOW_PAINEL_CUSTO)")
    fila = container.pedidos.fila
    eventos = await asyncio.to_thread(fila.custos_desde, inicio_do_dia(dias - 1))
    por_pedido: dict[str | None, dict[str, int]] = defaultdict(
        lambda: {"entrada": 0, "saida_texto": 0, "saida_receita": 0, "imagens": 0}
    )
    for evento in eventos:
        soma = por_pedido[evento["pedido_id"]]
        for chave in soma:
            soma[chave] += evento[chave]
    pedidos = []
    for pedido_id, soma in por_pedido.items():
        if pedido_id is None:
            continue
        try:
            pedido = await asyncio.to_thread(fila.obter, pedido_id)
        except ErroDaFila:
            continue
        pedidos.append({
            "id": pedido.id,
            "texto": pedido.texto,
            "situacao": pedido.situacao.value,
            "projeto": pedido.projeto,
            "tokens": tokens_estimados(soma),
            "tokens_total": tokens_estimados(pedido.custo),
        })
    pedidos.sort(key=lambda p: -p["tokens"])
    linhas = por_dia(eventos, dias)
    hoje = linhas[0]
    limite = config.limite_diario or None
    return {
        "hoje": {
            **hoje,
            "limite": limite,
            "atingido": bool(limite and hoje["tokens"] >= limite),
        },
        "dias": linhas,
        "pedidos": pedidos[:15],
        "avulso": tokens_estimados(por_pedido[None]) if None in por_pedido else 0,
        "estimativa": "~3 caracteres por token em texto, ~2,3 na receita, 294 por imagem do olhar",
    }
