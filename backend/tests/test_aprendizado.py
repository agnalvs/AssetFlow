"""Lições, opiniões e exemplos mostrados (Fase B2 do plano do app).

A caixa é um SQLite em ``data/aprendizado/`` que a API e o servidor MCP
dividem. Aqui, a caixa sozinha e as rotas da tela.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.aprendizado import (
    MAX_REGRA,
    QUALQUER,
    CaixaDeAprendizado,
    LicaoInvalida,
    LicaoNaoEncontrada,
    Natureza,
    Origem,
    SituacaoDaOpiniao,
    Tema,
    ler_tema,
)
from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from tests.conftest import BACKEND_ROOT, run

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"


@pytest.fixture
def caixa(tmp_path: Path) -> CaixaDeAprendizado:
    return CaixaDeAprendizado(tmp_path / "aprendizado" / "aprendizado.sqlite3")


def _licao(caixa: CaixaDeAprendizado, regra: str, **campos):
    padrao = {
        "errou": "corpo e capa no mesmo valor",
        "porque": "usei o mesmo tom em tudo",
        "tema": "valor",
        "tipo": "character",
        "corpo": "humanoid",
        "porte": "48x48",
    }
    return caixa.registrar(regra=regra, **{**padrao, **campos})


# ---------------------------------------------------------------------------
# Lições
# ---------------------------------------------------------------------------
def test_temas_tem_natureza_e_acento_nao_importa():
    assert ler_tema("Proporção") is Tema.PROPORCAO
    assert Tema.LUZ.natureza is Natureza.TECNICA and Tema.POSE.natureza is Natureza.FORMA
    assert ler_tema("brilho") is None


def test_licao_nova_e_repetida_soma_no_contador(caixa):
    primeira = _licao(caixa, "partes vizinhas em valores diferentes: alterne claro e escuro", asset_id="a1")
    assert primeira.nova and primeira.licao.id == "L1" and primeira.licao.contador == 1

    # Quase a mesma frase, mesma origem, tipo e tema: soma.
    de_novo = _licao(caixa, "partes vizinhas em valores diferentes: alterne o claro e o escuro", asset_id="a2")
    assert not de_novo.nova and de_novo.licao.id == "L1" and de_novo.licao.contador == 2
    assert de_novo.licao.assets == ("a2", "a1")
    assert "contador agora 2" in de_novo.texto()

    # Dita de outro jeito, mas apontada: soma também.
    apontada = _licao(caixa, "nada de mancha única", mesma_que="L1")
    assert apontada.licao.contador == 3

    # Outro tema não é a mesma lição.
    outra = _licao(caixa, "partes vizinhas em valores diferentes: alterne claro e escuro", tema="luz")
    assert outra.nova and outra.licao.id == "L2"


def test_licao_recusa_tema_vazio_e_texto_longo(caixa):
    with pytest.raises(LicaoInvalida, match="tema 'brilho' não existe"):
        _licao(caixa, "x", tema="brilho")
    with pytest.raises(LicaoInvalida, match="falta 'porque'"):
        _licao(caixa, "x", porque="  ")
    with pytest.raises(LicaoInvalida, match=f"o teto é {MAX_REGRA}"):
        _licao(caixa, "a" * (MAX_REGRA + 1))
    with pytest.raises(LicaoNaoEncontrada):
        _licao(caixa, "x", mesma_que="L99")


def test_escolher_filtra_por_tipo_e_corpo_e_ordena_por_contador_e_peso(caixa):
    _licao(caixa, "capuz acima da linha dos olhos", tema="rosto")
    for _ in range(2):
        _licao(caixa, "corpo e capa em valores diferentes")
    _licao(caixa, "contorno sem degraus nas curvas", tema="contorno", tipo=QUALQUER, corpo=QUALQUER, porte=QUALQUER)
    _licao(caixa, "frasco com brilho de 1 px", tema="luz", tipo="prop", corpo=QUALQUER, porte="16x16")
    autora = caixa.registrar(
        errou="o cajado parece um cano", porque="desenhei um cilindro", regra="cajado com nós e ponta curva",
        tema="equipamento", tipo="character", corpo="humanoid", porte="48x48", origem=Origem.AUTORA,
        texto_da_autora="o cajado parece um cano",
    )

    escolhidas = caixa.escolher(tipo="character", corpo="humanoid", porte="48x48", peso_autora=3)
    # Autora: 1 × 3 = 3 > 2 (L2) > 1 (L1, L3).
    assert [l.id for l in escolhidas][:2] == [autora.licao.id, "L2"]
    assert {l.id for l in escolhidas} == {"L1", "L2", "L3", autora.licao.id}
    assert [l.id for l in caixa.escolher(tipo="prop", corpo=None, porte="16x16")] == ["L3", "L4"] or \
        {l.id for l in caixa.escolher(tipo="prop", corpo=None, porte="16x16")} == {"L3", "L4"}
    assert len(caixa.escolher(tipo="character", corpo="humanoid", porte="48x48", maximo=2)) == 2


def test_em_ousado_so_entram_as_de_tecnica(caixa):
    _licao(caixa, "capuz acima da linha dos olhos", tema="rosto")
    _licao(caixa, "corpo e capa em valores diferentes", tema="valor")
    temas = {l.tema for l in caixa.escolher(tipo="character", corpo="humanoid", porte="48x48", so_tecnica=True)}
    assert temas == {Tema.VALOR}


def test_editar_desligar_e_apagar(caixa):
    _licao(caixa, "corpo e capa em valores diferentes")
    editada = caixa.editar("L1", regra="roupa, capa e acessórios em valores diferentes", tema="cor")
    assert (editada.regra, editada.tema) == ("roupa, capa e acessórios em valores diferentes", Tema.COR)

    caixa.editar("L1", ligada=False)
    assert caixa.escolher(tipo="character", corpo="humanoid", porte="48x48") == []

    caixa.apagar("L1")
    with pytest.raises(LicaoNaoEncontrada):
        caixa.obter("L1")
    _licao(caixa, "outra")
    with pytest.raises(LicaoInvalida, match="vazia"):
        caixa.editar("L2", regra=" ")


# ---------------------------------------------------------------------------
# Opiniões
# ---------------------------------------------------------------------------
def test_so_nao_gostei_com_motivo_fica_pendente(caixa):
    assert caixa.opinar("a1", gostei=True, motivo="lindo").situacao is SituacaoDaOpiniao.NOTA
    assert caixa.opinar("a2", gostei=False).situacao is SituacaoDaOpiniao.NOTA
    pendente = caixa.opinar("a3", gostei=False, motivo="o cajado parece um cano")
    assert pendente.situacao is SituacaoDaOpiniao.PENDENTE
    assert [o.asset_id for o in caixa.pendentes()] == ["a3"]


def test_opiniao_convertida_fica_convertida_ate_mudar(caixa):
    caixa.opinar("a3", gostei=False, motivo="o cajado parece um cano")
    licao = caixa.registrar(
        errou="cajado reto", porque="cilindro", regra="cajado com nós", tema="equipamento",
        tipo="character", corpo="humanoid", porte="48x48", origem=Origem.AUTORA,
        texto_da_autora="o cajado parece um cano", asset_id="a3",
    )
    caixa.converter("a3", licao.licao.numero)
    assert caixa.pendentes() == []

    # Mesma opinião de novo: continua convertida. Motivo novo: pendente outra vez.
    assert caixa.opinar("a3", gostei=False, motivo="o cajado parece um cano").situacao is SituacaoDaOpiniao.CONVERTIDA
    assert caixa.opinar("a3", gostei=False, motivo="a capa some").situacao is SituacaoDaOpiniao.PENDENTE
    # A lição escrita não some quando a opinião muda.
    assert caixa.obter(licao.licao.numero).texto_da_autora == "o cajado parece um cano"


def test_gostei_lista_os_assets_do_mesmo_tipo_corpo_e_grade(caixa):
    caixa.opinar("a1", gostei=True, tipo="character", corpo="humanoid", porte="48x48")
    caixa.opinar("a2", gostei=True, tipo="prop", corpo=QUALQUER, porte="16x16")
    caixa.opinar("a3", gostei=False, tipo="character", corpo="humanoid", porte="48x48")
    assert [o.asset_id for o in caixa.gostei(tipo="character", corpo="humanoid", porte="48x48")] == ["a1"]


def test_rotacao_das_fontes_mostra_primeiro_a_nunca_vista(caixa):
    assert caixa.ordem_das_fontes(["pacote:b", "pacote:a"]) == ["pacote:a", "pacote:b"]
    caixa.exemplo_mostrado("pacote:a")
    assert caixa.ordem_das_fontes(["pacote:a", "pacote:b"]) == ["pacote:b", "pacote:a"]
    caixa.exemplo_mostrado("pacote:b")
    assert caixa.ordem_das_fontes(["pacote:a", "pacote:b"]) == ["pacote:a", "pacote:b"]


def test_arquivo_danificado_vira_erro_e_nao_e_apagado(tmp_path: Path):
    from assetflow.aprendizado import AprendizadoIndisponivel

    caminho = tmp_path / "aprendizado.sqlite3"
    caminho.write_bytes(b"isto nao e um banco")
    with pytest.raises(AprendizadoIndisponivel, match="danificado e não foi alterado"):
        CaixaDeAprendizado(caminho).listar()
    assert caminho.read_bytes() == b"isto nao e um banco"


# ---------------------------------------------------------------------------
# A tela: rotas de lições e opiniões
# ---------------------------------------------------------------------------
@pytest.fixture
def client(container: AppContainer):
    with TestClient(create_app(container=container)) as cliente:
        yield cliente


def _asset_desenhado(container: AppContainer) -> str:
    container.registry.enable(MOTOR)
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    laudo = run(ServicoDesenhista(container).desenhar(pedido="poção vermelha 16x16", receita=receita, perfil="pixel_prop_64"))
    linha = next(linha for linha in laudo.splitlines() if " · asset_" in linha)
    return linha.split(" · ")[1]


def test_tela_lista_edita_desliga_e_apaga_licoes(client, container):
    _licao(container.aprendizado, "corpo e capa em valores diferentes")

    lista = client.get("/api/aprendizado/licoes").json()
    assert [l["id"] for l in lista["items"]] == ["L1"]
    assert lista["items"][0]["natureza"] == "tecnica" and lista["temas"]["pose"] == "forma"

    editada = client.patch("/api/aprendizado/licoes/L1", json={"regra": "roupa e capa em valores diferentes", "ligada": False})
    assert editada.status_code == 200
    assert editada.json()["regra"] == "roupa e capa em valores diferentes" and editada.json()["ligada"] is False

    invalida = client.patch("/api/aprendizado/licoes/L1", json={"tema": "brilho"})
    assert invalida.status_code == 422 and "não existe" in invalida.json()["message"]

    assert client.delete("/api/aprendizado/licoes/L1").status_code == 204
    sumiu = client.delete("/api/aprendizado/licoes/L1")
    assert sumiu.status_code == 404 and sumiu.json()["message"] == "não há lição L1"


def test_tela_grava_opiniao_com_as_etiquetas_do_asset(client, container):
    asset = _asset_desenhado(container)

    resposta = client.put(f"/api/aprendizado/opinioes/{asset}", json={"gostei": False, "motivo": "a rolha some"})
    assert resposta.status_code == 200
    assert resposta.json()["situacao"] == "pendente"
    guardada = container.aprendizado.opiniao(asset)
    assert (guardada.tipo, guardada.corpo, guardada.porte) == ("prop", QUALQUER, "16x16")

    nota = client.put(f"/api/aprendizado/opinioes/{asset}", json={"gostei": True})
    assert nota.json()["situacao"] == "nota"
    lidas = client.get("/api/aprendizado/opinioes", params={"assets": f"{asset},asset_nada"}).json()
    assert set(lidas["items"]) == {asset} and lidas["items"][asset]["gostei"] is True

    sem_asset = client.put("/api/aprendizado/opinioes/asset_nada", json={"gostei": True})
    assert sem_asset.status_code == 400 and "não há asset 'asset_nada'" in sem_asset.json()["message"]
