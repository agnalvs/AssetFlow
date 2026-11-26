"""Lote F4: detalhes e acabamento na receita, e o pontilhado no olho do app."""

from __future__ import annotations

import numpy as np
import pytest

from assetflow.generation.engines.desenhista import acabamento
from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ReceitaInvalida, ler_receita
from assetflow.mcp.laudo import formato_da_receita
from assetflow.referencias.linha import medir_pontilhado

PALETA = {
    "k": "#181425", "p": "#e8b796", "m": "#a05b53", "w": "#ffffff",
    "r": "#b03a2e", "c": "#e07a5f", "a": "#3e2731", "b": "#6b4d5b",
}


def _desenho(camadas, lado=32):
    return desenhar(ler_receita({"paleta": PALETA, "camadas": camadas}), lado, lado)


def _onde(linhas, chave):
    return {(x, y) for y, l in enumerate(linhas) for x, c in enumerate(l) if c == chave}


# ----------------------------------------------------------------------
# Rosto
# ----------------------------------------------------------------------
@pytest.mark.parametrize(("cabeca", "olho"), [(5, 1), (10, 2), (14, 4), (20, 6)])
def test_o_olho_cresce_com_a_cabeca(cabeca, olho):
    pixels = acabamento.rosto((15, 10), cabeca, expressao="neutro", olhar="frente", vista="frente",
                              cor="k", boca="m", reflexo=None)
    olhos = [p for p, c in pixels.items() if c == "k"]
    assert len(olhos) == 2 * olho  # dois olhos do tamanho da cabeça
    if cabeca <= 5:
        assert "m" not in pixels.values()  # cabeça pequena demais para boca


def test_expressoes_mudam_olhos_sobrancelhas_e_boca():
    def rosto(expressao):
        return acabamento.rosto((15, 10), 12, expressao=expressao, olhar="frente", vista="frente",
                                cor="k", boca="m", reflexo=None)

    neutro, feliz, triste, bravo, surpreso = (rosto(e) for e in acabamento.EXPRESSOES)
    acima = min(y for _, y in neutro)
    assert any(y < acima for _, y in triste) and any(y < acima for _, y in bravo)  # sobrancelhas
    boca_neutra = [p for p, c in neutro.items() if c == "m"]
    boca_feliz = [p for p, c in feliz.items() if c == "m"]
    assert len(boca_feliz) > len(boca_neutra)  # os cantos da boca sobem
    assert min(y for (_, y), c in feliz.items() if c == "m") < max(y for (_, y), c in feliz.items() if c == "m")
    assert sum(1 for c in surpreso.values() if c == "k") > sum(1 for c in neutro.values() if c == "k")


def test_o_olhar_desloca_os_olhos_e_o_perfil_tem_um_olho():
    def olhos(**extra):
        base = {"expressao": "neutro", "olhar": "frente", "vista": "frente"} | extra
        pixels = acabamento.rosto((15, 10), 12, cor="k", boca=None, reflexo=None, **base)
        return sorted(p for p, c in pixels.items() if c == "k" and p[1] <= 11)  # só os olhos

    frente, direita = olhos(), olhos(olhar="direita")
    assert [x + 1 for x, _ in frente] == [x for x, _ in direita]
    assert len(olhos(vista="perfil", olhar="direita")) == len(frente) // 2


def test_rosto_e_luz_de_borda_nao_ficam_em_camada_espelhada():
    for op in ({"rosto": [8, 8], "cabeca": 8, "cor": "k"}, {"luz_de_borda": "c", "sobre": "r"}):
        with pytest.raises(ReceitaInvalida, match="espelho"):
            ler_receita({"paleta": PALETA, "camadas": [{"espelho": "x", "ops": [op]}]})


# ----------------------------------------------------------------------
# Mão e pé
# ----------------------------------------------------------------------
def test_o_pe_vira_para_o_lado_pedido():
    direita = acabamento.extremidade((10, 10), tipo="pe", forma="fechada", lado="direita",
                                     tamanho=3, cor="p", contorno=None)
    esquerda = acabamento.extremidade((10, 10), tipo="pe", forma="fechada", lado="esquerda",
                                      tamanho=3, cor="p", contorno=None)
    assert max(x for x, _ in direita) > 10 and min(x for x, _ in esquerda) < 10
    assert {(20 - x, y) for x, y in direita} == set(esquerda)


def test_a_mao_aberta_e_maior_que_a_fechada_e_o_contorno_so_no_tamanho_4():
    def mao(forma, tamanho, contorno=None):
        return acabamento.extremidade((10, 10), tipo="mao", forma=forma, lado="direita",
                                      tamanho=tamanho, cor="p", contorno=contorno)

    assert len(mao("aberta", 3)) > len(mao("fechada", 3)) - 1
    assert set(mao("fechada", 3, "k").values()) == {"p"}  # pequena demais para contorno
    assert set(mao("fechada", 4, "k").values()) == {"p", "k"}


# ----------------------------------------------------------------------
# Suavizar, pontilhar, textura, luz de borda
# ----------------------------------------------------------------------
def test_suavizar_poe_o_tom_por_dentro_da_curva():
    desenho = _desenho([
        {"nome": "corpo", "ops": [{"elipse": [4, 4, 24, 20], "cor": "r"}]},
        {"nome": "linha", "ops": [{"elipse": [4, 4, 24, 20], "cor": "k", "contorno": True}]},
        {"nome": "aa", "ops": [{"suavizar": "c", "traco": "k"}]},
    ])
    linhas = desenho.grade.linhas()
    tons = _onde(linhas, "c")
    assert tons
    for x, y in tons:  # dentro da silhueta: nenhum vizinho transparente
        assert all(linhas[y + dy][x + dx] != "." for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))


def test_suavizar_e_pontilhar_recusam_sprite_pequeno_sem_derrubar_o_desenho():
    desenho = _desenho([
        {"nome": "corpo", "ops": [{"ret": [2, 2, 12, 12], "cor": "r"}]},
        {"nome": "fim", "ops": [
            {"suavizar": "c", "traco": "k"},
            {"pontilhar": [2, 2, 12, 12], "cores": "rc"},
        ]},
    ], lado=16)
    assert sum(1 for a in desenho.avisos if "recusado" in a) == 2
    assert _onde(desenho.grade.linhas(), "c") == set()


def test_reta_nao_se_suaviza():
    desenho = _desenho([
        {"nome": "corpo", "ops": [{"ret": [4, 4, 20, 20], "cor": "r"}, {"ret": [4, 4, 20, 20], "cor": "k", "contorno": True}]},
        {"nome": "aa", "ops": [{"suavizar": "c", "traco": "k"}]},
    ])
    assert any("nada a suavizar" in a for a in desenho.avisos)


def test_pontilhar_fica_na_pintura_e_avisa_o_teto():
    desenho = _desenho([
        {"nome": "ceu", "ops": [{"ret": [0, 0, 48, 20], "cor": "a"}]},
        {"nome": "degrade", "ops": [{"pontilhar": [0, 10, 60, 30], "cores": "ab"}]},
    ], lado=48)
    linhas = desenho.grade.linhas()
    assert _onde(linhas, "b") and all(y < 20 for _, y in _onde(linhas, "b"))
    assert any("é melhor uma cor a mais" in a for a in desenho.avisos)
    assert medir_pontilhado(_rgba(linhas))["pixels"] > 0


def test_textura_fica_no_miolo_e_luz_de_borda_no_lado_oposto():
    desenho = _desenho([{"nome": "tronco", "ops": [
        {"ret": [6, 6, 16, 16], "cor": "r"},
        {"textura": "veio", "cor": "m", "sobre": "r"},
        {"luz_de_borda": "c", "sobre": "r"},
    ]}])
    linhas = desenho.grade.linhas()
    veio = _onde(linhas, "m")
    assert veio and all(7 <= x <= 20 and 7 <= y <= 20 for x, y in veio)
    borda = _onde(linhas, "c")  # a luz vem de cima-esquerda: borda na direita e embaixo
    assert {x for x, _ in borda} >= {21} and {y for _, y in borda} >= {21}
    assert (6, 12) not in borda and (12, 6) not in borda  # o meio da esquerda e do topo, não


def test_o_formato_e_o_interruptor():
    assert '"rosto"' in formato_da_receita({"acabamento"})
    assert '"rosto"' not in formato_da_receita({"linha"})
    receita = ler_receita({"paleta": PALETA, "camadas": [{"ops": [{"rosto": [8, 8], "cabeca": 8, "cor": "k"}]}]})
    assert receita.usa == frozenset({"acabamento"})


# ----------------------------------------------------------------------
# O pontilhado no olho
# ----------------------------------------------------------------------
def _rgba(linhas):
    altura, largura = len(linhas), len(linhas[0])
    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    for y, l in enumerate(linhas):
        for x, c in enumerate(l):
            if c != ".":
                h = PALETA[c]
                rgba[y, x] = (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)
    return rgba


def test_janela_solta_nao_e_pontilhado_e_a_mancha_e():
    solta = ["rrrr", "rkrr", "rrkr", "rrrr"]  # um xadrez 2×2 (um olho)
    assert medir_pontilhado(_rgba(solta))["pixels"] == 0
    mancha = ["abab", "baba", "abab", "baba"]
    medida = medir_pontilhado(_rgba(mancha))
    assert medida["pixels"] == 16 and medida["fracao"] == 1.0


# ----------------------------------------------------------------------
# O formato dos opcionais, uma vez por conversa (ajuste de custo)
# ----------------------------------------------------------------------
def test_o_formato_dos_opcionais_vai_uma_vez_por_conversa(container):
    from assetflow.mcp.servico import ServicoDesenhista

    servico = ServicoDesenhista(container)
    primeira = servico.consultar("poção 16x16", "pixel_prop_64")
    segunda = servico.consultar("poção 16x16", "pixel_prop_64")
    repetida = servico.consultar("poção 16x16", "pixel_prop_64", formato=True)
    assert '"rosto"' in primeira and '"rosto"' not in segunda and '"rosto"' in repetida
    assert "comandos opcionais ligados: cor e luz, construção, linha, acabamento" in segunda
    assert len(primeira) - len(segunda) > 1_500

    container.settings.aprendizado.formato_uma_vez = False
    sempre = ServicoDesenhista(container)
    sempre.consultar("poção 16x16", "pixel_prop_64")
    assert '"rosto"' in sempre.consultar("poção 16x16", "pixel_prop_64")
