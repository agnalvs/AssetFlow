"""Lote 13: o estudo dos melhores sprites — bons exemplos e regras propostas."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from assetflow.pixel_knowledge import BaseDeConhecimento
from assetflow.pixel_knowledge.base import _ler_tema
from assetflow.referencias import ReferenciasAtivas
from assetflow.referencias.exemplo import fontes_do_exemplo
from tests.conftest import BACKEND_ROOT
from tests.test_ficha import COMANDOS_DA_RECEITA
from tests.test_olhar import _colecao, _config, _figura

CONHECIMENTO = BACKEND_ROOT / "config" / "pixel_knowledge"
PROPOSTA = CONHECIMENTO / "propostas" / "estudo_sprites.yaml"


def test_a_proposta_e_um_tema_valido_com_alvos_que_existem():
    dados = yaml.safe_load(PROPOSTA.read_text(encoding="utf-8"))
    tema = _ler_tema(dados, "propostas/estudo_sprites.yaml", "estudo_sprites")
    olhar = yaml.safe_load((CONHECIMENTO / "olhar.yaml").read_text(encoding="utf-8"))
    perguntas = {f"{forma}/{p['nome']}" for forma, lista in olhar["listas"].items() for p in lista}
    assert len(tema.regras) >= 10
    for regra in tema.regras:
        tipo, alvo = regra.tipo_de_verificacao, regra.alvo_da_verificacao
        if tipo == "olhar" and alvo.startswith("*/"):
            assert any(p.endswith("/" + alvo[2:]) for p in perguntas), regra.texto
        elif tipo == "olhar":
            assert alvo in perguntas, regra.texto
        elif tipo == "construcao":
            assert alvo in COMANDOS_DA_RECEITA, regra.texto
        else:
            assert tipo == "autora", regra.texto


def test_a_proposta_nao_entra_na_base():
    base = BaseDeConhecimento.do_diretorio(CONHECIMENTO)
    assert "estudo_sprites" not in base.temas
    textos = {r.texto for t in base.temas.values() for r in t.regras}
    assert "em 16 px, olhos de 1×1 ou 1×2 escuros; a boca é opcional" not in textos


def test_com_a_lista_o_exemplo_usa_so_os_bons(tmp_path: Path):
    colecao = _colecao(tmp_path, {
        "Idle/heroi.png": _figura(27, 10, (32, 32)),
        "Idle/vilao.png": _figura(28, 12, (32, 32)),
    })
    todos = fontes_do_exemplo(colecao, "character", "humanoid", 28)
    assert {q.arquivo for qs in todos.values() for q in qs} == {"Idle/heroi.png", "Idle/vilao.png"}

    vilao = next(q for qs in todos.values() for q in qs if q.arquivo == "Idle/vilao.png")
    raiz = tmp_path / "referencias"
    (raiz / "bons_exemplos.json").write_text(json.dumps({"quadros": [
        {"pacote": vilao.pacote, "arquivo": vilao.arquivo, "caixa": list(vilao.caixa)}]}), encoding="utf-8")
    com_lista = ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", "[heroi]"))
    assert len(com_lista.bons) == 1

    bons = fontes_do_exemplo(com_lista, "character", "humanoid", 28, so_bons=True)
    assert [q.arquivo for qs in bons.values() for q in qs] == ["Idle/vilao.png"]
    sem_filtro = fontes_do_exemplo(com_lista, "character", "humanoid", 28, so_bons=False)
    assert len([q for qs in sem_filtro.values() for q in qs]) == 2


def test_lista_ilegivel_e_ignorada_com_aviso(tmp_path: Path):
    _colecao(tmp_path, {"Idle/heroi.png": _figura(27, 10, (32, 32))})
    raiz = tmp_path / "referencias"
    (raiz / "bons_exemplos.json").write_text("{nada", encoding="utf-8")
    colecao = ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", "[heroi]"))
    assert colecao.bons == frozenset()
    assert any("bons_exemplos.json" in a for a in colecao.avisos)
