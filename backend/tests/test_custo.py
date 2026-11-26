"""Lote 12: o painel de custo e o limite diário."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.mcp.servico import ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido
from assetflow.pedidos.custo import por_dia, tokens_estimados, tokens_hoje
from tests.conftest import run


def _pedido(container, texto="poção 16x16"):
    return run(container.pedidos.criar(CorpoDoPedido(prompt=texto, profile="pixel_prop_64",
                                                     modo_conceito="sem_conceito")))


def test_a_estimativa_e_a_do_lote_1():
    assert tokens_estimados({"entrada": 300, "saida_texto": 300, "saida_receita": 230, "imagens": 2}) == 888
    assert tokens_estimados(None) == 0


def test_cada_soma_vira_evento_datado_e_o_dia_soma_os_eventos(container):
    fila = container.pedidos.fila
    pedido = _pedido(container)
    ontem = datetime.now(UTC) - timedelta(days=1)
    fila.somar_custo(pedido.id, entrada=3000, agora=ontem)
    fila.somar_custo(pedido.id, entrada=300, imagens=1)
    fila.somar_custo(None, entrada=600)  # consulta avulsa

    assert fila.obter(pedido.id).custo["entrada"] == 3300  # o pedido soma tudo
    eventos = fila.custos_desde(ontem - timedelta(hours=1))
    assert len(eventos) == 3
    dias = por_dia(eventos, 2)
    assert dias[0]["tokens"] == 100 + 294 + 200 and dias[0]["consultas"] == 2
    assert dias[1]["tokens"] == 1000
    assert tokens_hoje(fila) == 594


def test_por_dia_usa_o_dia_local_e_preenche_os_vazios():
    eventos = [{"em": "2026-11-20T12:00:00+00:00", "entrada": 30}]
    dias = por_dia(eventos, 3, hoje=date(2026, 11, 22))
    assert [d["data"] for d in dias] == ["2026-11-22", "2026-11-21", "2026-11-20"]
    assert [d["tokens"] for d in dias] == [0, 0, 10]


def test_o_mcp_registra_a_consulta_avulsa_e_avisa_o_limite(container):
    servico = ServicoDesenhista(container)
    servico.consultar("poção 16x16", "pixel_prop_64")
    assert tokens_hoje(container.pedidos.fila) > 0
    container.settings.custo.limite_diario = 1
    resposta = servico.consultar("poção 16x16", "pixel_prop_64")
    assert resposta.startswith("aviso: hoje já passaram ~") and "ASSETFLOW_LIMITE_DIARIO_TOKENS" in resposta
    container.settings.custo.limite_diario = 0
    assert not servico.consultar("poção 16x16", "pixel_prop_64").startswith("aviso:")


def test_o_painel_por_dia_por_pedido_e_o_interruptor(container):
    pedido = _pedido(container)
    container.pedidos.fila.somar_custo(pedido.id, entrada=3000, imagens=1)
    container.pedidos.fila.somar_custo(None, entrada=300)
    container.settings.custo.limite_diario = 1000
    with TestClient(create_app(container=container)) as cliente:
        painel = cliente.get("/api/custo?dias=3").json()
        assert painel["hoje"]["tokens"] == 1000 + 294 + 100
        assert painel["hoje"]["atingido"] and painel["hoje"]["limite"] == 1000
        assert len(painel["dias"]) == 3
        assert painel["pedidos"][0]["id"] == pedido.id and painel["pedidos"][0]["tokens"] == 1294
        assert painel["avulso"] == 100
        container.settings.custo.painel = False
        assert cliente.get("/api/custo").status_code == 400
