"""Lote 1: a etapa de conceito antes do desenho.

Três modos por pedido: "eu escolho" (a autora escolhe na tela), "o Claude
escolhe" (propõe, escolhe e desenha na mesma rodada) e "sem conceito".
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.bootstrap import AppContainer
from assetflow.mcp.laudo import conceito_na_medida
from assetflow.mcp.servico import MOTOR, ErroDoPedido, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido, Etapa, ModoConceito, Situacao, agora_utc
from tests.conftest import BACKEND_ROOT, run

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"

MAGA = [
    {
        "traco": "o cabelo é gelo: mechas congeladas que sobem em pontas, como uma coroa de estalactites",
        "silhueta": "losango alto, cintura fina e saia em sino que abre embaixo",
        "objeto": "floco de neve hexagonal do tamanho da cabeça, flutuando sobre a palma",
        "pose": "de três quartos, um braço erguido sustentando o floco",
        "simplificar": "a saia vira um trapézio; o floco, uma estrela de 5 px",
    },
    {
        "traco": "a maga do gelo que sente frio, enterrada num casaco de pele com capuz",
        "silhueta": "triângulo largo e baixo, encolhida, quase sem pescoço",
        "objeto": "lanterna de cristal com chama azul congelada, alça curta de osso",
        "pose": "curvada para a frente, lanterna erguida com as duas mãos",
        "simplificar": "o capuz some; ficam o casaco e a lanterna",
    },
    {
        "traco": "braço direito e ombro de cristal, maiores que o resto do corpo",
        "silhueta": "assimétrica em L: ombro pontudo enorme de um lado, manto curto do outro",
        "objeto": "leque de cinco lâminas finas de gelo, aberto na mão de cristal",
        "pose": "de duelo, pés afastados, peso na perna de trás",
        "simplificar": "o leque vira três lâminas",
    },
]


@pytest.fixture
def servico(container: AppContainer) -> ServicoDesenhista:
    container.registry.enable(MOTOR)
    return ServicoDesenhista(container)


def _pedido(container: AppContainer, modo: str, texto: str = "poção azul 16x16", **campos):
    corpo = CorpoDoPedido(prompt=texto, profile="pixel_prop_64", modo_conceito=modo, **campos)
    return run(container.pedidos.criar(corpo))


def test_o_padrao_e_eu_escolho_e_ajuste_nao_tem_conceito(container):
    assert container.settings.pedidos.conceito == "eu_escolho"
    pedido = run(container.pedidos.criar(CorpoDoPedido(prompt="poção 16x16", profile="pixel_prop_64")))
    assert pedido.modo_conceito is ModoConceito.EU_ESCOLHO and pedido.precisa_conceito


def test_eu_escolho_vai_para_a_tela_e_volta_com_o_conceito(servico, container):
    pedido = _pedido(container, "eu_escolho", direcao_de_arte="vidro torto")
    texto = run(servico.pedidos_pendentes())
    assert f"== {pedido.id} · conceito (a autora escolhe)" in texto
    assert "conceito na medida da grade 16×16: um traço marcante só" in texto
    assert "receita: {" not in texto, "sem desenho na resposta, sem formato da receita"
    assert container.pedidos.fila.obter(pedido.id).etapa(agora_utc()) is Etapa.CONCEITUANDO

    with pytest.raises(ErroDoPedido, match="precisa de conceito antes do desenho"):
        run(servico.desenhar(pedido_id=pedido.id, receita=json.loads(POCAO.read_text(encoding="utf-8"))))

    resposta = run(servico.propor_conceitos(pedido.id, MAGA))
    assert "três conceitos na tela" in resposta and "Não desenhe agora" in resposta
    esperando = container.pedidos.fila.obter(pedido.id)
    assert esperando.situacao is Situacao.ESCOLHENDO and esperando.etapa(agora_utc()) is Etapa.ESCOLHA_CONCEITO
    assert esperando.reservado_ate is None and len(esperando.conceitos) == 3

    escolhido = container.pedidos.escolher_conceito(pedido.id, 2, {"objeto": "lanterna de vidro azul"})
    assert escolhido.situacao is Situacao.PENDENTE
    assert escolhido.conceito["objeto"] == "lanterna de vidro azul" and escolhido.conceito["editado"]
    assert escolhido.direcao_de_arte.startswith("vidro torto · conceito — traço: a maga do gelo que sente frio")

    bloco = run(servico.pedidos_pendentes())
    assert 'direção de arte (conceito escolhido pela autora): "vidro torto · conceito' in bloco
    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=json.loads(POCAO.read_text(encoding="utf-8"))))
    assert "conceito: o desenho entrega o traço marcante do conceito escolhido" in laudo


def test_outros_tres_e_nao_repetir_os_recusados(servico, container):
    pedido = _pedido(container, "eu_escolho")
    run(servico.pedidos_pendentes())
    run(servico.propor_conceitos(pedido.id, MAGA))
    container.pedidos.outros_conceitos(pedido.id)

    texto = run(servico.pedidos_pendentes())
    assert "conceitos já recusados pela autora (não repita): 1) o cabelo é gelo" in texto
    with pytest.raises(ErroDoPedido, match="repete um que a autora recusou"):
        run(servico.propor_conceitos(pedido.id, MAGA))
    assert container.pedidos.fila.obter(pedido.id).conceitos_recusados[0]["traco"].startswith("o cabelo")


def test_claude_escolhe_grava_os_tres_e_desenha_na_mesma_rodada(servico, container):
    pedido = _pedido(container, "claude_escolhe")
    run(servico.pedidos_pendentes())
    with pytest.raises(ErroDoPedido, match="quem escolhe é você"):
        run(servico.propor_conceitos(pedido.id, MAGA))

    resposta = run(servico.propor_conceitos(pedido.id, MAGA, escolhido=3, motivo="a assimetria lê de longe"))

    assert resposta.startswith(f"pedido {pedido.id}: conceito 3 escolhido — a assimetria lê de longe")
    assert "receita: {" in resposta and "conceito escolhido pelo Claude" in resposta
    depois = container.pedidos.fila.obter(pedido.id)
    assert depois.conceito["indice"] == 3 and depois.motivo_conceito == "a assimetria lê de longe"
    assert len(depois.conceitos) == 3 and depois.situacao is Situacao.EM_DESENHO
    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=json.loads(POCAO.read_text(encoding="utf-8"))))
    assert "aprovado no validador" in laudo.splitlines()[0]


def test_eu_escolho_recusa_escolha_do_claude_e_sem_conceito_recusa_conceitos(servico, container):
    eu = _pedido(container, "eu_escolho")
    sem = _pedido(container, "sem_conceito")
    with pytest.raises(ErroDoPedido, match="quem escolhe é a autora"):
        run(servico.propor_conceitos(eu.id, MAGA, escolhido=1, motivo="x"))
    with pytest.raises(ErroDoPedido, match="é sem conceito"):
        run(servico.propor_conceitos(sem.id, MAGA))


@pytest.mark.parametrize(
    ("conceitos", "trecho"),
    [
        (MAGA[:2], "exatamente 3"),
        ([MAGA[0], MAGA[0], MAGA[2]], "parecidos demais"),
        ([{**MAGA[0], "pose": ""}, MAGA[1], MAGA[2]], "falta 'pose' no conceito 1"),
        ([{**MAGA[0], "simplificar": "x" * 81}, MAGA[1], MAGA[2]], "o teto é 80"),
    ],
)
def test_conceitos_conferidos(servico, container, conceitos, trecho):
    pedido = _pedido(container, "eu_escolho")
    with pytest.raises(ErroDoPedido, match=trecho):
        run(servico.propor_conceitos(pedido.id, conceitos))


def test_conceito_na_medida_da_grade():
    assert "um traço marcante só" in conceito_na_medida(16, 16)
    assert "um traço marcante e um objeto simples" in conceito_na_medida(32, 32)
    assert "o conceito completo" in conceito_na_medida(48, 48)


def test_lista_curta_e_custo_por_pedido(container):
    container.registry.enable(MOTOR)
    container.settings.aprendizado.lista_curta = True
    servico = ServicoDesenhista(container)
    pedido = _pedido(container, "sem_conceito")
    run(servico.pedidos_pendentes())
    laudo = run(servico.desenhar(pedido_id=pedido.id, receita=json.loads(POCAO.read_text(encoding="utf-8"))))
    assert "Confira: silhueta, uma ideia, faces, luz, limpeza." in laudo and "1. silhueta" not in laudo
    custo = container.pedidos.fila.obter(pedido.id).custo
    assert custo["imagens"] == 1 and custo["saida_receita"] > 500 and custo["entrada"] > 1000


def test_tela_escolhe_e_pede_outros(container, servico):
    pedido = _pedido(container, "eu_escolho")
    run(servico.pedidos_pendentes())
    run(servico.propor_conceitos(pedido.id, MAGA))
    with TestClient(create_app(container=container)) as cliente:
        lista = cliente.get("/api/pedidos").json()["items"]
        vista = next(item for item in lista if item["id"] == pedido.id)
        assert vista["etapa"] == "escolha_conceito" and len(vista["conceitos"]) == 3

        fora = cliente.post(f"/api/pedidos/{pedido.id}/conceito", json={"indice": 4})
        assert fora.status_code == 422
        escolhido = cliente.post(f"/api/pedidos/{pedido.id}/conceito", json={"indice": 1}).json()
        assert escolhido["etapa"] == "na_fila" and escolhido["conceito"]["indice"] == 1
        de_novo = cliente.post(f"/api/pedidos/{pedido.id}/outros-conceitos")
        assert de_novo.status_code == 409
