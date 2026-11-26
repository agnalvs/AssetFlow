"""Lote F2: cor e luz na receita (rampa, material, sombrear, brilho, oclusão, sombra projetada)."""

from __future__ import annotations

import colorsys

import pytest

from assetflow.generation.engines.desenhista.cor_e_luz import gerar_rampa
from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ReceitaInvalida, ler_receita
from assetflow.mcp.laudo import FORMATO_RECEITA, formato_da_receita


def _luminancia(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def test_rampa_do_escuro_ao_claro_com_desvio_de_matiz():
    rampa = gerar_rampa((0x3E, 0x89, 0x48), 5, desvio=15)
    assert len(rampa) == 5 and rampa[2] == (0x3E, 0x89, 0x48)
    luminancias = [_luminancia(c) for c in rampa]
    assert luminancias == sorted(luminancias), "do escuro ao claro"
    matiz = [colorsys.rgb_to_hsv(*(v / 255 for v in c))[0] * 360 for c in rampa]
    # Verde (~128°): ao escurecer caminha para o azul (240°), ao clarear para o amarelo (60°).
    assert matiz[0] > matiz[2] > matiz[4]


def _receita(camadas, **extra):
    return ler_receita(
        {"grade": [12, 12], "paleta": {"k": "#181425"}, "rampas": [{"chaves": "abcd", "base": "#0099db"}],
         "camadas": camadas, **extra}
    )


def test_rampa_cria_as_chaves_e_recusa_colisao():
    receita = _receita([{"nome": "c", "ops": [{"ret": [1, 1, 4, 4], "cor": "b"}]}])
    assert set("abcd") <= set(receita.paleta) and receita.usa == {"cor_e_luz"}
    with pytest.raises(ReceitaInvalida, match="já está na paleta"):
        ler_receita({"paleta": {"a": "#000000"}, "rampas": [{"chaves": "ab", "base": "#0099db"}],
                     "camadas": [{"ops": [{"ret": [0, 0, 1, 1], "cor": "a"}]}]})
    with pytest.raises(ReceitaInvalida, match="de 0 a 20 graus"):
        ler_receita({"paleta": {"k": "#000000"}, "rampas": [{"chaves": "ab", "base": "#0099db", "desvio": 30}],
                     "camadas": [{"ops": [{"ret": [0, 0, 1, 1], "cor": "k"}]}]})


def test_sombrear_esfera_clareia_o_lado_da_luz():
    receita = _receita([{"nome": "bola", "material": "metal", "ops": [
        {"elipse": [1, 1, 10, 10], "cor": "b"},
        {"sombrear": "esfera", "rampa": "abcd"},
    ]}])
    linhas = desenhar(receita, 12, 12).grade.linhas()
    # Com luz de cima e da esquerda, o canto de cima à esquerda é o mais claro.
    assert linhas[3][3] in "cd" and linhas[9][9] in "ab"


def test_sombrear_caixa_tem_topo_claro_e_lado_oposto_escuro():
    receita = _receita([{"nome": "bau", "ops": [
        {"ret": [1, 1, 10, 10], "cor": "b"},
        {"sombrear": "caixa", "rampa": "abcd"},
    ]}])
    linhas = desenhar(receita, 12, 12).grade.linhas()
    assert linhas[1][5] == "d" and linhas[6][10] == "a" and linhas[6][4] in "bc"


def test_brilho_fica_do_lado_da_luz_e_o_vidro_ganha_reflexo():
    receita = _receita([{"nome": "frasco", "material": "vidro", "ops": [
        {"elipse": [1, 1, 10, 10], "cor": "b"},
        {"brilho": "d", "sobre": "b"},
    ]}])
    linhas = desenhar(receita, 12, 12).grade.linhas()
    brilhos = [(x, y) for y, linha in enumerate(linhas) for x, c in enumerate(linha) if c == "d"]
    assert len(brilhos) == 3, "2 do lado da luz e 1 reflexo do lado oposto"
    assert min(x + y for x, y in brilhos) < 8 and max(x + y for x, y in brilhos) > 12


def test_oclusao_e_sombra_projetada():
    receita = _receita([
        {"nome": "corpo", "ops": [{"ret": [1, 1, 10, 10], "cor": "c"}]},
        {"nome": "braco", "ops": [
            {"ret": [3, 3, 3, 3], "cor": "b"},
            {"oclusao": "corpo", "cor": "a"},
            {"sombra_projetada": "corpo", "cor": "a"},
        ]},
    ])
    linhas = desenhar(receita, 12, 12).grade.linhas()
    assert linhas[3][3] == "a", "o braço escurece onde encosta no corpo"
    assert linhas[6][6] == "a" and linhas[6][2] == "c", "a sombra cai para baixo e para a direita"


def test_efeito_em_camada_espelhada_e_citacao_errada_sao_recusados():
    with pytest.raises(ReceitaInvalida, match="levaria a luz para o lado errado"):
        _receita([{"nome": "c", "espelho": "x", "ops": [
            {"ret": [1, 1, 4, 4], "cor": "b"}, {"sombrear": "esfera", "rampa": "abcd"}]}])
    with pytest.raises(ReceitaInvalida, match="camada desenhada antes desta"):
        _receita([{"nome": "c", "ops": [{"ret": [1, 1, 4, 4], "cor": "b"}, {"oclusao": "x", "cor": "a"}]}])
    with pytest.raises(ReceitaInvalida, match="'material' aceita"):
        _receita([{"nome": "c", "material": "ouro", "ops": [{"ret": [1, 1, 4, 4], "cor": "b"}]}])


def test_formato_cita_os_comandos_so_quando_ligados():
    assert formato_da_receita(set()) == FORMATO_RECEITA
    assert '"sombrear"' in formato_da_receita({"cor_e_luz"})


def test_gaveta_recusa_comandos_desligados(container):
    from assetflow.mcp.servico import MOTOR, ErroDoPedido, ServicoDesenhista
    from tests.conftest import run

    container.registry.enable(MOTOR)
    # A gaveta carrega na primeira chamada, com a configuração do handle.
    handle = container.registry.get(MOTOR).handle
    handle._config = handle._config.model_copy(update={"options": {"comandos_cor_e_luz": False}})
    receita = {"grade": [16, 16], "paleta": {"k": "#181425"}, "rampas": [{"chaves": "ab", "base": "#0099db"}],
               "camadas": [{"nome": "c", "ops": [{"ret": [2, 2, 6, 6], "cor": "a"}]}]}
    with pytest.raises(ErroDoPedido, match="comandos desligados nesta instalação"):
        run(ServicoDesenhista(container).desenhar(pedido="caixa 16x16", receita=receita, perfil="pixel_prop_64"))
