"""Lote 1: a banca de teste (etapa K1 do plano da base, versão enxuta)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from assetflow.api.app import create_app
from assetflow.banca import (
    BancaInvalida,
    impressao_da_base,
    ler_banca,
    tokens_estimados,
)
from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from tests.conftest import BACKEND_ROOT, run

#: Um slime de 4 cores, 16×16, com contorno, para os pares da banca.
SLIME = {
    "grade": [16, 16],
    "paleta": {"k": "#181425", "g": "#3e8948", "G": "#63c74d", "w": "#ffffff"},
    "camadas": [
        {"nome": "corpo", "ops": [{"elipse": [2, 5, 12, 10], "cor": "g"}]},
        {"nome": "luz", "ops": [{"elipse": [4, 6, 6, 4], "cor": "G"}, {"px": ["w"], "em": [5, 7]}]},
        {"nome": "contorno", "ops": [{"elipse": [2, 5, 12, 10], "cor": "k", "contorno": True}]},
    ],
}


def test_a_banca_tem_os_seis_pedidos_do_plano():
    banca = ler_banca(BACKEND_ROOT / "config" / "banca.yaml")
    assert [i.id for i in banca.itens] == ["maga", "anao", "lobo", "slime", "machado", "bau"]
    assert banca.liberdade == "equilibrado"


def test_banca_torta_diz_o_que_falta(tmp_path: Path):
    caminho = tmp_path / "banca.yaml"
    caminho.write_text("itens:\n  - {id: a, texto: x}\n", encoding="utf-8")
    with pytest.raises(BancaInvalida, match="precisa de id, texto e perfil"):
        ler_banca(caminho)


def test_impressao_muda_com_a_base_e_com_os_interruptores(tmp_path: Path):
    (tmp_path / "luz.yaml").write_text("padrao: x\n", encoding="utf-8")
    antes = impressao_da_base(tmp_path, {"exemplo": False})
    assert impressao_da_base(tmp_path, {"exemplo": False}) == antes
    assert impressao_da_base(tmp_path, {"exemplo": True}) != antes
    (tmp_path / "luz.yaml").write_text("padrao: y\n", encoding="utf-8")
    assert impressao_da_base(tmp_path, {"exemplo": False}) != antes


def test_tokens_estimados():
    assert tokens_estimados({"entrada": 300, "saida_texto": 0, "saida_receita": 230, "imagens": 1}) == 100 + 100 + 294


def _desenhar_rodada(container: AppContainer, rodada) -> None:
    """Desenha o slime (16×16, a grade da poção de exemplo) e cancela o resto.

    Aqui se testa a banca, não o desenho: um par com os dois lados desenhados
    e cinco sem desenho bastam.
    """
    servico = ServicoDesenhista(container)
    receita = SLIME
    for entrada in rodada.itens:
        pid = entrada["pedido_id"]
        if entrada["item"] != "slime":
            container.pedidos.fila.cancelar(pid)
            continue
        container.pedidos.fila.reservar([pid], "lev_x")
        run(servico.desenhar(pedido_id=pid, receita=receita))
        run(servico.concluir(pid, "ok"))


def test_rodada_cria_os_seis_pedidos_no_projeto_da_banca(container: AppContainer):
    rodada = run(container.banca.criar_rodada("referência", "sem_conceito"))

    assert rodada.id == "R1" and len(rodada.itens) == 6
    assert rodada.interruptores["modo_conceito"] == "sem_conceito" and len(rodada.versao_base) == 12
    pedido = container.pedidos.fila.obter(rodada.itens[0]["pedido_id"])
    assert pedido.projeto == "banca"
    assert pedido.banca == {"rodada": "R1", "item": "maga", "ordem": 1, "total": 6}
    container.registry.enable(MOTOR)
    texto = run(ServicoDesenhista(container).pedidos_pendentes(limite=1))
    assert "banca R1 · maga (1 de 6): desenhe do zero" in texto


def test_comparar_esconde_o_lado_e_resume_depois_dos_votos(container: AppContainer):
    container.registry.enable(MOTOR)
    r1 = run(container.banca.criar_rodada("referência", "sem_conceito"))
    r2 = run(container.banca.criar_rodada("conceito", "sem_conceito"))
    for rodada in (r1, r2):
        _desenhar_rodada(container, rodada)

    dados = run(container.banca.comparar("R1", "R2"))
    assert len(dados["pares"]) == 6 and dados["resumo"] is None
    # Os lados são sorteados por par, e sempre os mesmos.
    assert dados["pares"] == run(container.banca.comparar("R1", "R2"))["pares"]

    with TestClient(create_app(container=container)) as cliente:
        vista = cliente.get("/api/banca/comparar", params={"a": "R1", "b": "R2"}).json()
        assert "R1" not in json.dumps(vista["pares"]) and "R2" not in json.dumps(vista["pares"])
        com_voto = [p for p in vista["pares"] if p["esquerda"]["asset"] and p["direita"]["asset"]]
        for par in com_voto:
            resposta = cliente.put(
                "/api/banca/votos",
                json={"a": "R1", "b": "R2", "item": par["item"], "escolha": "direita",
                      "nota_esquerda": 2, "nota_direita": 4},
            )
            assert resposta.status_code == 204
        final = cliente.get("/api/banca/comparar", params={"a": "R1", "b": "R2"}).json()
        assert final["avaliados"] == 6
        resumo = final["resumo"]
        assert resumo["nova"] == "R2" and set(resumo["lados"]) == {"maga", "anao", "lobo", "slime", "machado", "bau"}
        assert sum(resumo["vitorias"].values()) == 6
        assert resumo["veredito"].startswith(("mantém", "não mantém"))
        lista = cliente.get("/api/banca").json()
        assert [r["id"] for r in lista["rodadas"]] == ["R2", "R1"] and lista["rodadas"][0]["pronta"]

        ruim = cliente.put(
            "/api/banca/votos",
            json={"a": "R1", "b": "R2", "item": "maga", "escolha": "esquerda", "nota_esquerda": 6, "nota_direita": 1},
        )
        assert ruim.status_code == 422
        assert cliente.get("/api/banca/comparar", params={"a": "R1", "b": "R9"}).status_code == 404
