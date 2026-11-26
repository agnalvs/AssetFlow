"""Lote F1: linha e contorno na receita, e as medidas de linha do olho do app."""

from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from assetflow.generation.engines.desenhista import linha
from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ReceitaInvalida, ler_receita
from assetflow.mcp.laudo import formato_da_receita
from assetflow.referencias.linha import medir_linha
from assetflow.referencias.olho import olhar_desenho
from assetflow.referencias.pacote import ConfiguracaoDoOlho

PALETA = {"k": "#181425", "r": "#b03a2e", "w": "#f0e0d0", "a": "#5a1f1a", "b": "#b03a2e", "c": "#e07a5f"}


def _desenho(camadas, **raiz):
    paleta = raiz.pop("paleta", {"k": "#181425", "r": "#b03a2e", "w": "#f0e0d0"})
    return desenhar(ler_receita({"paleta": paleta, "camadas": camadas, **raiz}), 16, 16)


def _passos(pontos, eixo=1):
    """Os tamanhos dos trechos de um caminho na mesma linha."""
    tamanhos = []
    for p in pontos:
        if tamanhos and tamanhos[-1][1] == p[eixo]:
            tamanhos[-1][0] += 1
        else:
            tamanhos.append([1, p[eixo]])
    return [t[0] for t in tamanhos]


# ----------------------------------------------------------------------
# reta e curva
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("fim", "passos"),
    [((5, 2), [2, 2, 2]), ((3, 3), [1, 1, 1, 1]), ((5, 1), [3, 3]), ((0, 4), [5])],
)
def test_a_reta_tem_degraus_iguais(fim, passos):
    pontos, chegou = linha.reta(0, 0, *fim)
    eixo = 0 if fim[0] == 0 else 1
    assert _passos(pontos, eixo) == passos
    assert chegou == pontos[-1]


def test_a_reta_que_nao_fecha_avisa_onde_terminou():
    desenho = _desenho([{"nome": "t", "ops": [{"reta": [0, 0, 6, 2], "cor": "k"}]}])
    assert any("a reta terminou em (5,2) em vez de (6,2)" in a for a in desenho.avisos)


def test_a_curva_passa_pelos_pontos_sem_canto_em_l():
    pontos = linha.curva([(1, 12), (6, 4), (14, 2)])
    assert (1, 12) in pontos and (6, 4) in pontos and (14, 2) in pontos
    assert linha.cantos_em_l(pontos) == []
    for a, b in pairwise(pontos):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1  # 8-conectada


def test_calombos_seguem_o_paragrafo_4():
    def caminho(passos):
        pontos, x = [], 0
        for y, n in enumerate(passos):
            pontos += [(x + i, y) for i in range(n)]
            x += n
        return pontos

    assert linha.calombos_do_caminho(caminho([5, 2, 2, 1, 1])) == []
    assert linha.calombos_do_caminho(caminho([5, 2, 1, 2, 1])) != []
    assert linha.calombos_do_caminho(caminho([3, 3, 3])) == []


# ----------------------------------------------------------------------
# limpar_linha
# ----------------------------------------------------------------------
def test_limpar_tira_o_canto_em_l_e_a_dobra_e_relata():
    desenho = _desenho([
        {"nome": "t", "ops": [
            {"px": ["kk....", ".kk...", "..kkk.", "..kk.."], "em": [2, 2]},
            {"limpar_linha": "k"},
        ]},
    ])
    linhas = desenho.grade.linhas()
    mascara = {(x, y) for y, l in enumerate(linhas) for x, c in enumerate(l) if c == "k"}
    assert linha.cantos_em_l(mascara) == [] and linha.dobras(mascara) == []
    aviso = next(a for a in desenho.avisos if "limpar_linha" in a)
    assert "de dobra em" in aviso and "de canto em L em" in aviso
    assert "sobraram 0 canto(s) em L e 0 dobra(s)" in aviso


def test_limpar_deixa_o_canto_proposital_e_a_mancha():
    caixa = [{"ret": [2, 2, 6, 6], "cor": "k", "contorno": True}]
    desenho = _desenho([{"nome": "c", "ops": [*caixa, {"limpar_linha": True}]}])
    assert sum(l.count("k") for l in desenho.grade.linhas()) == 20  # os quatro cantos ficam
    cheia = _desenho([{"nome": "c", "ops": [{"ret": [2, 2, 6, 6], "cor": "r"}, {"limpar_linha": True}]}])
    assert sum(l.count("r") for l in cheia.grade.linhas()) == 36
    assert any("dobras não conferidas em r" in a for a in cheia.avisos)


def test_o_pixel_tirado_volta_ao_que_estava_embaixo():
    desenho = _desenho([
        {"nome": "fundo", "ops": [{"ret": [0, 0, 16, 16], "cor": "w"}]},
        {"nome": "t", "ops": [{"px": ["kk.", ".kk"], "em": [2, 2]}, {"limpar_linha": "k"}]},
    ])
    linhas = desenho.grade.linhas()
    tirado = next((x, y) for y in (2, 3) for x in (2, 3, 4) if linhas[y][x] == "w" and (x, y) in
                  {(3, 2), (3, 3)})
    assert tirado  # o meio do L virou o fundo, não transparente


# ----------------------------------------------------------------------
# contorno
# ----------------------------------------------------------------------
def test_contorno_inteiro_seletivo_e_colorido():
    corpo = [{"nome": "corpo", "ops": [{"ret": [4, 4, 8, 8], "cor": "r"}]}]
    inteiro = _desenho(corpo, contorno={"tipo": "inteiro", "cor": "k"}).grade.linhas()
    assert inteiro[4][4:12] == "kkkkkkkk" and inteiro[8][4:12] == "krrrrrrk"

    seletivo = _desenho(corpo, contorno={"tipo": "seletivo", "cor": "k", "cor_luz": "w"}).grade.linhas()
    assert seletivo[4][6] == "w" and seletivo[8][4] == "w"  # topo e esquerda: a luz vem de cima-esquerda
    assert seletivo[11][6] == "k" and seletivo[8][11] == "k"

    colorido = desenhar(ler_receita({
        "paleta": {"k": "#181425"},
        "rampas": [{"chaves": "abc", "base": "#b03a2e"}],
        "contorno": {"tipo": "colorido", "cor": "k"},
        "camadas": [{"nome": "corpo", "ops": [{"ret": [4, 4, 8, 8], "cor": "b"}]}],
    }), 16, 16).grade.linhas()
    assert colorido[4][5] == "a" and colorido[8][8] == "b"  # o escuro da rampa na borda


def test_contorno_entra_por_ultimo_no_mapa_e_recusa_o_que_falta():
    receita = ler_receita({
        "paleta": {"k": "#181425", "r": "#b03a2e"},
        "contorno": {"tipo": "inteiro", "cor": "k"},
        "camadas": [{"nome": "corpo", "ops": [{"ret": [4, 4, 8, 8], "cor": "r"}]}],
    })
    assert receita.camadas[-1].nome == "contorno_auto" and "linha" in receita.usa
    with pytest.raises(ReceitaInvalida, match="cor_luz"):
        ler_receita({"paleta": {"k": "#000000"}, "contorno": {"tipo": "seletivo", "cor": "k"},
                     "camadas": [{"ops": [{"ret": [0, 0, 2, 2], "cor": "k"}]}]})
    with pytest.raises(ReceitaInvalida, match="contorno_auto"):
        ler_receita({"paleta": {"k": "#000000"}, "contorno": {"cor": "k"},
                     "camadas": [{"nome": "contorno_auto", "ops": [{"ret": [0, 0, 2, 2], "cor": "k"}]}]})


def test_o_formato_do_mcp_cita_o_grupo_so_ligado():
    assert '"limpar_linha"' in formato_da_receita({"linha"})
    assert '"limpar_linha"' not in formato_da_receita({"cor_e_luz"})


def test_o_interruptor_desliga_o_grupo(container):
    from assetflow.mcp.servico import MOTOR

    container.registry.enable(MOTOR)
    gaveta = container.registry.get(MOTOR)
    gaveta.handle._config = gaveta.handle._config.model_copy(
        update={"options": {**gaveta.handle._config.options, "comandos_linha": False}}
    )
    from assetflow.mcp.servico import ErroDoPedido, ServicoDesenhista
    from tests.conftest import run

    servico = ServicoDesenhista(container)
    receita = {"paleta": {"k": "#181425"}, "camadas": [{"ops": [{"reta": [0, 0, 5, 5], "cor": "k"}]}]}
    with pytest.raises(ErroDoPedido, match="linha"):
        run(servico.desenhar(pedido="traço 16x16", receita=receita, perfil="pixel_prop_64"))


# ----------------------------------------------------------------------
# As medidas do olho
# ----------------------------------------------------------------------
def _rgba(linhas, cores):
    altura, largura = len(linhas), len(linhas[0])
    rgba = np.zeros((altura, largura, 4), dtype=np.uint8)
    for y, l in enumerate(linhas):
        for x, c in enumerate(l):
            if c != ".":
                h = cores[c]
                rgba[y, x] = (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255)
    return rgba


def test_o_olho_mede_cantos_dobras_e_degraus():
    linhas = [
        "kk..........",
        ".kk.........",
        "..kkk.......",
        "..kk........",
        ".....kkkkk..",
        "..........kk",
    ]
    medida = medir_linha(_rgba(linhas, {"k": "#181425"}), "#181425")
    assert medida["cantos"] and medida["dobras"] == [(2, 2)]
    assert medida["cantos_por_100"] > 0


def test_a_limpeza_da_gaveta_zera_o_que_o_olho_mede():
    px = ["kk......", ".kk.....", "..kkk...", "..kk....", "....kk..", ".....kkk"]
    desenho = _desenho([{"nome": "t", "ops": [{"px": px, "em": [1, 1]}, {"limpar_linha": "k"}]}])
    linhas = [l.replace("w", ".").replace("r", ".") for l in desenho.grade.linhas()]
    medida = medir_linha(_rgba(linhas, {"k": "#181425"}), "#181425")
    assert medida["cantos"] == [] and medida["dobras"] == []


def test_o_olho_acusa_acima_do_limite_do_tipo():
    linhas = [
        "kkkkkkkkkk",
        "k........k",
        "kk.......k",
        ".kk......k",
        "..kkkkkkkk",
    ]
    rgba = _rgba(linhas, {"k": "#181425"})
    preenchido = rgba.copy()
    preenchido[1:4, 1:9] = np.where(preenchido[1:4, 1:9, 3:4] > 0, preenchido[1:4, 1:9], (176, 58, 46, 255))
    config = ConfiguracaoDoOlho(linha={"prop": {"cantos": 0.0, "dobras": 99, "degraus": 99}})

    class Colecao:
        configuracao = type("C", (), {"olho": config})()
        esta_vazia = True

        def faixa(self, altura):
            return None

    relatorio = olhar_desenho(preenchido, Colecao(), tipo="prop", corpo=None, altura_do_corpo=None)
    assert any(d.codigo == "CANTOS" for d in relatorio.desvios)
    assert relatorio.medidas["linha"]["pixels"] > 0
