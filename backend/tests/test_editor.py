"""Lote 5: o editor de pixels da tela.

A troca de pixels vira uma camada ``retoque_N`` no fim da receita da base, o
desenho passa pelo caminho de sempre, e o resultado aprovado vira um pedido de
ajuste já concluído. Nenhuma chamada ao Claude.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from assetflow.api.app import create_app
from assetflow.editor import (
    DESLIGADO,
    ServicoDoEditor,
    Troca,
    camada_de_retoque,
    grade_do_png,
)
from assetflow.generation.kernel.exceptions import InvalidGenerationRequest
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido, Situacao, Tipo
from tests.conftest import run
from tests.test_olhar_mcp import MESMO_VALOR

PALETA = {"k": "#181425", "r": "#b03a2e"}
VERMELHO, ESCURO = "#b03a2e", "#181425"


# ----------------------------------------------------------------------
# A camada
# ----------------------------------------------------------------------
def test_a_camada_cobre_o_retangulo_do_que_mudou():
    camada, finais = camada_de_retoque(
        {"camadas": [{"nome": "corpo"}]},
        [Troca(3, 4, "k"), Troca(5, 4, None), Troca(4, 6, "r"), Troca(3, 4, "r")],
        largura=16,
        altura=16,
        paleta=PALETA,
    )
    assert camada == {"nome": "retoque_1", "ops": [{"px": ["r.-", "...", ".r."], "em": [3, 4]}]}
    assert finais == {(3, 4): "r", (5, 4): None, (4, 6): "r"}  # a troca repetida vale a última


def test_editar_uma_edicao_numera_a_camada():
    receita = {"camadas": [{"nome": "corpo"}, {"nome": "retoque_1"}]}
    camada, _ = camada_de_retoque(receita, [Troca(0, 0, "k")], largura=4, altura=4, paleta=PALETA)
    assert camada["nome"] == "retoque_2"


@pytest.mark.parametrize(
    ("trocas", "trecho"),
    [
        ([], "nenhum pixel mudou"),
        ([Troca(16, 0, "k")], "fora da grade 16×16"),
        ([Troca(0, 0, "z")], "não está na paleta"),
    ],
)
def test_troca_impossivel_e_recusada_em_portugues(trocas, trecho):
    with pytest.raises(InvalidGenerationRequest, match=trecho):
        camada_de_retoque({}, trocas, largura=16, altura=16, paleta=PALETA)


def test_a_grade_amostra_o_png_ampliado():
    logica = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    logica.putpixel((1, 0), (176, 58, 46, 255))
    ampliada = logica.resize((8, 8), Image.Resampling.NEAREST)
    bruto = BytesIO()
    ampliada.save(bruto, format="PNG")
    assert grade_do_png(bruto.getvalue(), 2, 2) == [[None, VERMELHO], [None, None]]


# ----------------------------------------------------------------------
# Pelo app
# ----------------------------------------------------------------------
def _pronto(container):
    """Um pedido desenhado e concluído pelo caminho do MCP."""
    container.registry.enable(MOTOR)
    servico = ServicoDesenhista(container)
    pedido = run(container.pedidos.criar(CorpoDoPedido(
        prompt="caixa vermelha 16x16", profile="pixel_prop_64", modo_conceito="sem_conceito")))
    run(servico.desenhar(pedido_id=pedido.id, receita=MESMO_VALOR))
    run(servico.concluir(pedido.id, "duas metades"))
    return container.pedidos.fila.obter(pedido.id)


def test_abrir_mostra_a_grade_e_a_paleta_da_gaveta(container):
    pedido = _pronto(container)
    with TestClient(create_app(container=container)) as cliente:
        dados = cliente.get(f"/api/pedidos/{pedido.id}/editor").json()
    assert (dados["largura"], dados["altura"], dados["asset_id"]) == (16, 16, pedido.asset_id)
    assert dados["paleta"] == PALETA
    assert dados["pixels"][5][3] == VERMELHO and dados["pixels"][0][0] is None


def test_salvar_cria_um_ajuste_pronto_com_o_remendo(container):
    pedido = _pronto(container)
    editor = ServicoDoEditor(container)
    trocas = [Troca(7, y, "k") for y in (6, 7, 8)]

    resultado = run(editor.salvar(pedido.id, trocas, motivo="faltava a divisão no meio"))

    assert resultado.aprovado, resultado.motivo
    assert (resultado.mudados, resultado.ficaram, resultado.camada) == (3, 3, "retoque_1")
    ajuste = resultado.pedido
    assert (ajuste.tipo, ajuste.situacao) == (Tipo.AJUSTE, Situacao.CONCLUIDO)
    assert ajuste.origem_asset_id == pedido.asset_id and ajuste.asset_id == resultado.asset_id
    assert "editor" in ajuste.olhar

    # O PNG novo tem a divisão; o original ficou como era.
    novo = run(editor.abrir(ajuste.id))
    assert [novo.pixels[y][7] for y in (6, 7, 8)] == [ESCURO] * 3
    assert run(editor.abrir(pedido.id)).pixels[6][7] == VERMELHO
    registro = run(container.pedidos.registro(resultado.asset_id))
    camadas = registro.engine_options[MOTOR]["receita"]["camadas"]
    assert camadas[-1]["nome"] == "retoque_1" and len(camadas) == len(MESMO_VALOR["camadas"]) + 1

    # "O que estava errado" vira um "não gostei" pendente no asset original.
    opiniao = container.aprendizado.opiniao(pedido.asset_id)
    assert (opiniao.gostei, opiniao.situacao.value) == (False, "pendente")
    assert "faltava a divisão" in opiniao.motivo

    # Editar a edição numera a camada seguinte.
    de_novo = run(editor.salvar(ajuste.id, [Troca(0, 0, None)]))
    assert de_novo.camada == "retoque_2"


def test_salvar_pela_api(container):
    pedido = _pronto(container)
    corpo = {"pixels": [{"x": 7, "y": 6, "cor": "k"}, {"x": 1, "y": 2, "cor": None}]}
    with TestClient(create_app(container=container)) as cliente:
        resposta = cliente.post(f"/api/pedidos/{pedido.id}/editor", json=corpo)
        assert resposta.status_code == 200, resposta.text
        dados = resposta.json()
        assert dados["aprovado"] and dados["pedido"]["tipo"] == "ajuste"
        assert dados["pedido"]["etapa"] == "pronto"
        lista = cliente.get("/api/pedidos").json()["items"]
    assert dados["pedido"]["id"] in {item["id"] for item in lista}


def test_so_pedido_pronto_abre_no_editor(container):
    container.registry.enable(MOTOR)
    pedido = run(container.pedidos.criar(CorpoDoPedido(
        prompt="caixa vermelha 16x16", profile="pixel_prop_64", modo_conceito="sem_conceito")))
    with pytest.raises(InvalidGenerationRequest, match="só um pedido pronto"):
        run(ServicoDoEditor(container).abrir(pedido.id))


def test_editor_desligado_recusa(container):
    pedido = _pronto(container)
    container.settings.pedidos.editor = False
    with TestClient(create_app(container=container)) as cliente:
        resposta = cliente.get(f"/api/pedidos/{pedido.id}/editor")
    assert resposta.status_code == 400
    assert resposta.json()["message"] == DESLIGADO
