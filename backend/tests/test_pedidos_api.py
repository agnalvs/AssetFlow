"""As rotas de pedidos (Fase B do plano do app): prévia, criar, listar, ler,
cancelar e devolver — e os erros, no formato normalizado e em português."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from tests.conftest import BACKEND_ROOT, run

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"
CORPO = {
    "capability": "text_to_image.pixel",
    "profile": "pixel_prop_64",
    "prompt": "poção azul 16x16",
}


@pytest.fixture
def client(container: AppContainer):
    with TestClient(create_app(container=container)) as cliente:
        yield cliente


def test_previa_e_criacao_gravam_o_mesmo_spec(client: TestClient):
    """O que a tela mostra é o que fica gravado: mesma montagem, mesmo hash."""
    previa = client.post("/api/pedidos/previa", json=CORPO).json()
    criado = client.post("/api/pedidos", json=CORPO)

    assert criado.status_code == 201
    gravado = criado.json()["leitura"]["resolved"]
    assert gravado["spec_hash"] == previa["resolved"]["spec_hash"]
    # O gerador do app, pelo nome e sem fallback — a tela não escolhe motor.
    assert previa["resolved"]["engine"] == {
        "selection_mode": "manual",
        "engine_id": MOTOR,
        "allow_fallback": False,
        "reason": "",
    }


def test_criar_grava_liberdade_direcao_e_o_projeto_do_app(client: TestClient):
    resposta = client.post(
        "/api/pedidos",
        json={**CORPO, "liberdade": "ousado", "direcao_de_arte": "  frasco torto, vidro verde  "},
    ).json()

    assert resposta["situacao"] == "pendente" and resposta["etapa"] == "na_fila"
    assert resposta["liberdade"] == "ousado"
    assert resposta["direcao_de_arte"] == "frasco torto, vidro verde"
    assert resposta["projeto"] == "principal"
    assert resposta["resumo"] == {"tipo_asset": "prop", "grade": "16×16", "cores": 16, "fundo": "transparent"}
    assert resposta["corpo"]["prompt"] == "poção azul 16x16"
    assert [e["situacao"] for e in resposta["eventos"]] == ["pendente"]


def test_liberdade_e_direcao_nao_mudam_o_spec(client: TestClient):
    fiel = client.post("/api/pedidos", json={**CORPO, "liberdade": "fiel"}).json()
    ousado = client.post(
        "/api/pedidos", json={**CORPO, "liberdade": "ousado", "direcao_de_arte": "xilogravura"}
    ).json()
    assert fiel["leitura"]["resolved"]["spec_hash"] == ousado["leitura"]["resolved"]["spec_hash"]


def test_listar_do_mais_novo_no_projeto_padrao(client: TestClient):
    primeiro = client.post("/api/pedidos", json=CORPO).json()["id"]
    segundo = client.post("/api/pedidos", json={**CORPO, "prompt": "espada curta 32x32"}).json()["id"]

    lista = client.get("/api/pedidos").json()
    assert lista["projeto"] == "principal"
    assert [item["id"] for item in lista["items"]] == [segundo, primeiro]
    assert client.get("/api/pedidos", params={"situacao": "cancelado"}).json()["items"] == []


def test_cancelar_e_devolver(client: TestClient, container: AppContainer):
    pedido = client.post("/api/pedidos", json=CORPO).json()["id"]

    recusa = client.post(f"/api/pedidos/{pedido}/devolver")
    assert recusa.status_code == 409
    assert recusa.json()["code"] == "pedido_em_outra_situacao"
    assert recusa.json()["detail"] == {"situacao": "pendente"}

    container.pedidos.fila.reservar([pedido], "lev_teste")
    # O padrão da instalação é "eu escolho": reservado, o pedido espera os conceitos.
    assert client.get(f"/api/pedidos/{pedido}").json()["etapa"] == "conceituando"
    devolvido = client.post(f"/api/pedidos/{pedido}/devolver").json()
    assert devolvido["situacao"] == "pendente"

    assert client.post(f"/api/pedidos/{pedido}/cancelar").json()["etapa"] == "cancelado"
    de_novo = client.post(f"/api/pedidos/{pedido}/cancelar")
    assert de_novo.status_code == 409
    assert "já está cancelado" in de_novo.json()["message"]


def test_pedido_que_nao_existe(client: TestClient):
    resposta = client.get("/api/pedidos/ped_nada")
    assert resposta.status_code == 404
    assert resposta.json()["code"] == "pedido_nao_encontrado"


@pytest.mark.parametrize(
    ("corpo", "status", "trecho"),
    [
        ({**CORPO, "engine": {"mode": "auto"}}, 422, "contrato da API"),
        ({**CORPO, "project_id": "outro"}, 422, "contrato da API"),
        ({**CORPO, "prompt": "   "}, 400, "precisa de uma descrição"),
        ({**CORPO, "output": {"variations": 3}}, 400, "um pedido é um desenho"),
        ({**CORPO, "liberdade": "solta"}, 422, "contrato da API"),
        ({"origem_asset_id": "asset_nada", "texto": "mais verde"}, 400, "não há asset"),
        ({"origem_asset_id": "asset_nada"}, 400, "dizer o que mudar"),
    ],
)
def test_pedidos_recusados_dizem_por_que(client: TestClient, corpo: dict, status: int, trecho: str):
    resposta = client.post("/api/pedidos", json=corpo)
    assert resposta.status_code == status
    assert trecho in resposta.json()["message"]


def test_ajuste_grava_o_spec_do_asset_de_origem(client: TestClient, container: AppContainer):
    container.registry.enable(MOTOR)
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    laudo = run(
        ServicoDesenhista(container).desenhar(
            pedido="poção vermelha 16x16", receita=receita, perfil="pixel_prop_64"
        )
    )
    origem = laudo.splitlines()[0].split(" · ")[1]
    spec_da_origem = run(container.pedidos.spec_do_asset(run(container.pedidos.registro(origem))))

    resposta = client.post(
        "/api/pedidos", json={"origem_asset_id": origem, "texto": "rolha dourada", "liberdade": "fiel"}
    )

    assert resposta.status_code == 201
    ajuste = resposta.json()
    assert ajuste["tipo"] == "ajuste" and ajuste["origem_asset_id"] == origem
    assert ajuste["texto"] == "rolha dourada"
    assert ajuste["leitura"]["resolved"]["spec_hash"] == spec_da_origem.spec_hash


def test_fila_danificada_vira_503_com_a_frase_e_o_arquivo_fica(
    client: TestClient, container: AppContainer
):
    caminho = container.pedidos.fila.caminho
    caminho.parent.mkdir(parents=True, exist_ok=True)
    lixo = b"nao sou um banco " * 300
    caminho.write_bytes(lixo)

    resposta = client.get("/api/pedidos")

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["code"] == "fila_corrompida"
    assert "danificado e não foi alterado" in corpo["message"]
    assert client.post("/api/pedidos", json=CORPO).status_code == 503
    assert caminho.read_bytes() == lixo
