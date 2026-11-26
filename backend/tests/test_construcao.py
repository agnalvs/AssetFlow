"""Lote F3: construção na receita (capsula, copiar, boneco)."""

from __future__ import annotations

import pytest

from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ReceitaInvalida, ler_receita
from assetflow.mcp.laudo import formato_da_receita

PALETA = {"k": "#181425", "p": "#e4a672", "b": "#0099db", "r": "#a22633"}


def _linhas(receita, lado=16):
    return desenhar(ler_receita({"grade": [lado, lado], "paleta": PALETA, **receita}), lado, lado).grade.linhas()


def test_capsula_com_contorno_e_pontas_redondas():
    linhas = _linhas({"camadas": [{"nome": "braco", "ops": [
        {"capsula": [3, 3, 12, 3], "espessura": 3, "cor": "b", "contorno": "k"}]}]})
    assert linhas[3][7] == "b" and linhas[2][7] == "k" and linhas[4][7] == "k"
    assert linhas[3][1] == "k" or linhas[3][2] == "k", "a ponta fecha com contorno"


def test_capsula_com_cotovelo_e_vao_ate_o_tronco():
    linhas = _linhas({"camadas": [
        {"nome": "tronco", "ops": [{"ret": [6, 4, 4, 8], "cor": "r"}]},
        {"nome": "braco", "ops": [
            {"capsula": [5, 4, 3, 8, 4, 12], "espessura": 2, "cor": "b", "vao": "tronco"}]},
    ]})
    # Perto do ombro o braço encosta; mais abaixo, fica 1 px longe do tronco.
    assert linhas[11][5] == "."
    assert any(c == "b" for c in linhas[10])


def test_copiar_espelhado_faz_o_outro_braco():
    linhas = _linhas({"camadas": [
        {"nome": "esq", "ops": [{"px": ["bb", "b."], "em": [2, 2]}]},
        {"nome": "dir", "ops": [{"copiar": "esq", "desloca": [8, 0], "espelho": "x"}]},
    ]})
    assert linhas[2][10:12] == "bb" and linhas[3][10:12] == ".b"


@pytest.mark.parametrize("pose", ["parado", "andando", "ataque", "conjurando"])
def test_boneco_gera_camadas_nomeadas_em_cada_pose(pose):
    receita = ler_receita({
        "grade": [48, 48], "paleta": PALETA,
        "boneco": {"altura": 30, "cabecas": 3, "chao": 46, "centro": 24, "pose": pose,
                   "cores": {"pele": "p", "roupa": "b", "contorno": "k"}},
        "camadas": [{"nome": "chapeu", "ops": [{"ret": [20, 14, 8, 3], "cor": "r"}]}],
    })
    nomes = [c.nome for c in receita.camadas]
    assert nomes[:6] == ["boneco_braco_tras", "boneco_perna_tras", "boneco_perna_frente",
                         "boneco_tronco", "boneco_cabeca", "boneco_braco_frente"]
    assert nomes[-1] == "chapeu" and "construcao" in receita.usa
    linhas = desenhar(receita, 48, 48).grade.linhas()
    ocupadas = [y for y, l in enumerate(linhas) if l.strip(".")]
    assert max(ocupadas) <= 46 and min(ocupadas) >= 14


def test_poses_mudam_a_silhueta_e_cabecas_mudam_a_proporcao():
    def silhueta(**extra):
        receita = ler_receita({"grade": [48, 48], "paleta": PALETA, "boneco": {
            "altura": 30, "chao": 46, "centro": 24, "cores": {"pele": "p", "roupa": "b", "contorno": "k"}, **extra},
            "camadas": []})
        return desenhar(receita, 48, 48).grade.linhas()

    assert silhueta(pose="parado") != silhueta(pose="ataque")
    chibi = silhueta(cabecas=2)
    alto = silhueta(cabecas=5)
    def largura_da_cabeca(linhas):
        return max(len(linha.strip(".")) for linha in linhas[17:22])

    assert largura_da_cabeca(chibi) > largura_da_cabeca(alto)


def test_erros_de_construcao():
    with pytest.raises(ReceitaInvalida, match="'cabecas' vai de 1.5 a 8"):
        ler_receita({"paleta": PALETA, "boneco": {"altura": 30, "cabecas": 12, "chao": 46, "centro": 24,
                     "cores": {"pele": "p", "roupa": "b", "contorno": "k"}}})
    with pytest.raises(ReceitaInvalida, match="'pose' aceita"):
        ler_receita({"paleta": PALETA, "boneco": {"altura": 30, "chao": 46, "centro": 24, "pose": "dançando",
                     "cores": {"pele": "p", "roupa": "b", "contorno": "k"}}})
    with pytest.raises(ReceitaInvalida, match="2 ou 3 pontos"):
        ler_receita({"paleta": PALETA, "camadas": [{"ops": [{"capsula": [1, 1, 2], "cor": "b"}]}]})
    with pytest.raises(ReceitaInvalida, match="camada desenhada antes desta"):
        ler_receita({"paleta": PALETA, "camadas": [{"ops": [{"copiar": "nada"}]}]})


def test_formato_cita_construcao_quando_ligada():
    assert '"capsula"' in formato_da_receita({"construcao"})
    assert '"capsula"' not in formato_da_receita({"cor_e_luz"})
