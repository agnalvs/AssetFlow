"""Lote F5: a ficha de verificação.

Nenhuma regra entra na base sem dizer como é conferida, e o alvo da
verificação precisa existir. Cada asset concluído ganha uma ficha com uma
linha por regra, as respostas do olhar e o cruzamento com as medidas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.mcp.ficha import (
    CONFERE,
    MEDIDAS_CONHECIDAS,
    montar_ficha,
    resultado_da_resposta,
)
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido
from assetflow.pixel_knowledge import BaseDeConhecimento, ConhecimentoInvalido
from assetflow.pixel_knowledge.base import _ler_regra
from assetflow.referencias.olho import _LINHA
from tests.conftest import BACKEND_ROOT, run
from tests.test_olhar_mcp import MESMO_VALOR

CONHECIMENTO = BACKEND_ROOT / "config" / "pixel_knowledge"
COMANDOS_DA_RECEITA = {
    "ret", "elipse", "linha", "poligono", "balde", "px", "sombrear", "brilho", "oclusao",
    "sombra_projetada", "capsula", "copiar", "rampas", "luz", "boneco", "material",
}


@pytest.fixture(scope="module")
def base() -> BaseDeConhecimento:
    return BaseDeConhecimento.do_diretorio(CONHECIMENTO)


def _todas_as_regras(base):
    for forma in base.formas.values():
        yield from forma.regras
    yield from base.luz.regras


def test_toda_regra_declara_a_verificacao_e_o_alvo_existe(base):
    olhar = yaml.safe_load((CONHECIMENTO / "olhar.yaml").read_text(encoding="utf-8"))
    perguntas = {
        f"{forma}/{p['nome']}" for forma, lista in olhar["listas"].items() for p in lista
    }
    regras = list(_todas_as_regras(base))
    assert regras
    for regra in regras:
        tipo, alvo = regra.tipo_de_verificacao, regra.alvo_da_verificacao
        if tipo == "medida":
            assert alvo in MEDIDAS_CONHECIDAS, regra.texto
        elif tipo == "olhar":
            assert alvo in perguntas, regra.texto
        elif tipo == "construcao":
            assert alvo in COMANDOS_DA_RECEITA, regra.texto
        else:
            assert tipo == "autora", regra.texto


def test_regra_sem_verificacao_e_recusada():
    with pytest.raises(ConhecimentoInvalido, match="toda regra declara como é conferida"):
        _ler_regra({"texto": "luz de um lado", "classe": "style", "secao": "§6"}, "teste")
    with pytest.raises(ConhecimentoInvalido, match="verificacao"):
        _ler_regra({"texto": "x", "classe": "style", "secao": "§6", "verificacao": "palpite"}, "teste")


def test_as_medidas_conhecidas_existem_no_olho_e_no_validador():
    fonte = (BACKEND_ROOT / "assetflow" / "referencias" / "olho.py").read_text(encoding="utf-8")
    do_olho = set(re.findall(r'Desvio\(\s*"([A-Z]+)"', fonte)) | set(
        re.findall(r'desvios, "([A-Z]+)"', fonte)
    )
    do_olho |= {codigo for codigo, _, _ in _LINHA}  # lote F1: códigos numa tabela
    assert MEDIDAS_CONHECIDAS - {"ORFAOS"} <= do_olho | {"TONS", "RAMPAS", "CONTORNO"}
    assert {m for medidas in CONFERE.values() for m in medidas} <= MEDIDAS_CONHECIDAS


def test_resultado_da_resposta():
    assert resultado_da_resposta("sim")[0] == "passou"
    assert resultado_da_resposta("não: braço some no manto")[0] == "nao_passou"
    assert resultado_da_resposta(None)[0] == "sem_resposta"


def test_montar_ficha_e_o_cruzamento(base):
    regras = list(base.formas["humanoid"].regras)
    ficha = montar_ficha(
        regras=regras,
        perguntas=["silhueta", "valores", "luz"],
        respostas={"silhueta": "sim", "valores": "sim"},
        olhar={"olho": {"desvios": [{"codigo": "VALOR", "texto": "partes vizinhas com o mesmo valor"}],
                        "medidas": {"contraste_por_camada": [{"a": "x", "b": "y", "dL": 0}]}}},
        validacao={},
        receita=None,
    )
    por_regra = {linha["regra"]: linha for linha in ficha["linhas"]}
    valor = next(l for t, l in por_regra.items() if t.startswith("partes vizinhas"))
    assert (valor["tipo"], valor["resultado"], valor["quem"]) == ("medida", "nao_passou", "app")
    assert ficha["sem_resposta"] == ["luz"]
    assert ficha["divergencias"][0]["pergunta"] == "valores"


def test_concluir_grava_a_ficha_e_aponta_a_divergencia(container):
    container.registry.enable(MOTOR)
    servico = ServicoDesenhista(container)
    pedido = run(container.pedidos.criar(CorpoDoPedido(
        prompt="caixa vermelha 16x16", profile="pixel_prop_64", modo_conceito="sem_conceito")))
    run(servico.desenhar(pedido_id=pedido.id, receita=MESMO_VALOR))

    resposta = run(servico.concluir(
        pedido.id, "duas metades iguais", respostas={"silhueta": "sim", "uma ideia": "sim"}))

    assert "ficha: sem resposta para faces, luz, limpeza" in resposta
    depois = container.pedidos.fila.obter(pedido.id)
    arquivo = (container.settings.storage_root / "projects" / depois.asset_projeto / "jobs"
               / depois.job_id / "000_ficha.json")
    ficha = json.loads(arquivo.read_text(encoding="utf-8"))
    assert ficha["pedido_id"] == pedido.id and len(ficha["linhas"]) == 5  # 3 de objeto + 2 de luz
    with TestClient(create_app(container=container)) as cliente:
        assert cliente.get(f"/api/pedidos/{pedido.id}/ficha").json()["respostas"]["silhueta"] == "sim"


def test_ficha_desligada_nao_grava(container, tmp_path: Path):
    container.registry.enable(MOTOR)
    container.settings.aprendizado.ficha = False
    servico = ServicoDesenhista(container)
    pedido = run(container.pedidos.criar(CorpoDoPedido(
        prompt="caixa vermelha 16x16", profile="pixel_prop_64", modo_conceito="sem_conceito")))
    run(servico.desenhar(pedido_id=pedido.id, receita=MESMO_VALOR))
    resposta = run(servico.concluir(pedido.id, "ok"))
    assert "ficha:" not in resposta
    depois = container.pedidos.fila.obter(pedido.id)
    assert not (container.settings.storage_root / "projects" / depois.asset_projeto / "jobs"
                / depois.job_id / "000_ficha.json").exists()


def test_a_rota_rele_a_opiniao_da_autora(container):
    container.registry.enable(MOTOR)
    servico = ServicoDesenhista(container)
    pedido = run(container.pedidos.criar(CorpoDoPedido(
        prompt="caixa vermelha 16x16", profile="pixel_prop_64", modo_conceito="sem_conceito")))
    run(servico.desenhar(pedido_id=pedido.id, receita=MESMO_VALOR))
    run(servico.concluir(pedido.id, "ok", respostas={"silhueta": "sim"}))
    depois = container.pedidos.fila.obter(pedido.id)
    arquivo = (container.settings.storage_root / "projects" / depois.asset_projeto / "jobs"
               / depois.job_id / "000_ficha.json")
    ficha = json.loads(arquivo.read_text(encoding="utf-8"))
    ficha["linhas"].append({"regra": "a forma combina", "verificacao": "autora", "tipo": "autora",
                            "resultado": "sem_resposta", "detalhe": "", "quem": "autora"})
    arquivo.write_text(json.dumps(ficha), encoding="utf-8")

    container.aprendizado.opinar(depois.asset_id, gostei=False, motivo="tampa torta")
    with TestClient(create_app(container=container)) as cliente:
        linha = cliente.get(f"/api/pedidos/{pedido.id}/ficha").json()["linhas"][-1]
    assert (linha["resultado"], linha["detalhe"]) == ("nao_passou", "tampa torta")
