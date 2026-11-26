"""Fase B2: a imagem do olhar, o exemplo de construção, o olho do app e o mapa de camadas.

Só imagens geradas no próprio teste (a regra da biblioteca de referências).
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from assetflow.generation.engines.desenhista.rasterizador import (
    SIMBOLOS_DE_CAMADA,
    desenhar,
)
from assetflow.generation.engines.desenhista.receita import ler_receita
from assetflow.mcp.imagem import imagem_do_olhar, tokens_da_imagem
from assetflow.referencias import Parte, ReferenciasAtivas
from assetflow.referencias import olho as modulo_olho
from assetflow.referencias.exemplo import (
    FONTE_GOSTEI,
    TETO_EXEMPLO,
    CandidatoDeGostei,
    converter,
    escolher_exemplo,
    fontes_do_exemplo,
)
from assetflow.referencias.olho import (
    contraste_por_camada,
    iou_com_o_exemplo,
    olhar_desenho,
    repete_o_exemplo,
)
from tests.test_referencias import _figura, _pacote, _png

ESCURO = (20, 20, 30)


def _config(caminho: Path, ativos: str, *, olho: bool = True) -> Path:
    texto = (
        f"ativos: {ativos}\n"
        "porte:\n"
        "  faixa_altura: {valor: 0.2, classe: style, secao: \"§2\", a_calibrar: true}\n"
        "  minimo_de_quadros: {valor: 1, classe: style, secao: \"§2\", a_calibrar: true}\n"
    )
    if olho:
        texto += (
            "olho:\n"
            "  p_baixo: {valor: 0.1, classe: style, secao: \"§17\", a_calibrar: true}\n"
            "  p_alto: {valor: 0.9, classe: style, secao: \"§17\", a_calibrar: true}\n"
            "  contraste_minimo: {valor: 8, classe: style, secao: \"§3\", a_calibrar: true}\n"
            "  iou_copia: {valor: 0.85, classe: semantic, secao: \"§3\", a_calibrar: true}\n"
        )
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _colecao(tmp_path: Path, arquivos: dict[str, np.ndarray], pacote: str = "heroi", **extra) -> ReferenciasAtivas:
    origem = tmp_path / f"origem-{pacote}"
    for nome, rgba in arquivos.items():
        _png(rgba, origem / nome)
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem, pacote, (Parte("**", "character", "humanoid"),), **extra)
    return ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", f"[{pacote}]"))


# ---------------------------------------------------------------------------
# A imagem do olhar
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("lado", "ampliacao"), [(16, 24), (32, 12), (48, 8)])
def test_imagem_do_olhar_tem_o_mesmo_tamanho_e_custo_em_qualquer_grade(lado, ampliacao):
    sprite = _figura(lado - 4, lado // 2, (lado, lado))
    buffer = io.BytesIO()
    Image.fromarray(sprite, "RGBA").save(buffer, format="PNG")

    png, escala, tamanho = imagem_do_olhar(buffer.getvalue())

    assert escala == ampliacao
    assert tamanho == (588, 384) == Image.open(io.BytesIO(png)).size
    assert tokens_da_imagem(*tamanho) == 294, "⌈588/28⌉ × ⌈384/28⌉"


# ---------------------------------------------------------------------------
# O mapa de camadas da gaveta
# ---------------------------------------------------------------------------
def test_o_mapa_diz_de_qual_camada_e_cada_pixel():
    receita = ler_receita(
        {
            "grade": [6, 3],
            "paleta": {"k": "#101010", "r": "#c03030"},
            "camadas": [
                {"nome": "fundo", "ops": [{"ret": [0, 0, 6, 3], "cor": "r"}]},
                {"nome": "frente", "ops": [{"px": ["kk", "--"], "em": [2, 1]}]},
            ],
        }
    )
    desenho = desenhar(receita, 6, 3)
    assert desenho.mapa_de_camadas == ("000000", "001100", "00..00")


def test_simbolos_do_mapa_sao_os_mesmos_no_olho():
    assert modulo_olho.SIMBOLOS_DE_CAMADA == SIMBOLOS_DE_CAMADA


# ---------------------------------------------------------------------------
# Exemplo de construção
# ---------------------------------------------------------------------------
def test_converter_pela_luminancia_e_sem_pontos_no_fim():
    rgba = np.zeros((2, 4, 4), dtype=np.uint8)
    rgba[0, 0] = (250, 250, 250, 255)
    rgba[0, 1] = (10, 10, 10, 255)
    rgba[1, 1] = (120, 120, 120, 255)
    paleta, px = converter(rgba)
    assert paleta == {"a": "#0a0a0a", "b": "#787878", "c": "#fafafa"}
    assert px == ("ca", ".b")


def test_converter_recusa_mais_cores_que_chaves():
    rgba = np.zeros((1, 63, 4), dtype=np.uint8)
    rgba[0, :, 3] = 255
    rgba[0, :, 0] = np.arange(63) * 4
    assert converter(rgba) is None


def test_exemplo_prefere_quadro_parado_e_pula_pulo_e_ataque(tmp_path: Path):
    colecao = _colecao(
        tmp_path,
        {
            "Jump/heroi.png": _figura(28, 12, (32, 32)),
            "Attack/heroi.png": _figura(28, 13, (32, 32)),
            "Idle/heroi.png": _figura(27, 10, (32, 32)),
        },
    )
    fontes = fontes_do_exemplo(colecao, "character", "humanoid", 28)
    (quadros,) = fontes.values()
    assert quadros[0].arquivo == "Idle/heroi.png"

    exemplo = escolher_exemplo(colecao, fontes, list(fontes))
    assert exemplo.arquivo == "Idle/heroi.png" and exemplo.origem == "cc0"
    assert exemplo.texto.startswith("exemplo de construção (CC0 · ")
    assert "não é base nem entra em remendo" in exemplo.texto
    assert len(exemplo.texto) <= TETO_EXEMPLO


def test_sem_quadro_parado_vem_o_neutro_antes_da_acao(tmp_path: Path):
    colecao = _colecao(
        tmp_path,
        {"Jump/a.png": _figura(28, 12, (32, 32)), "Walk/a.png": _figura(28, 11, (32, 32))},
    )
    (quadros,) = fontes_do_exemplo(colecao, "character", "humanoid", 28).values()
    assert [q.arquivo for q in quadros] == ["Walk/a.png", "Jump/a.png"]


def test_quadro_que_passa_do_teto_e_pulado(tmp_path: Path):
    colecao = _colecao(tmp_path, {"Idle/a.png": _figura(28, 12, (32, 32))})
    fontes = fontes_do_exemplo(colecao, "character", "humanoid", 28)
    assert escolher_exemplo(colecao, fontes, list(fontes), teto=100) is None


def test_a_ordem_das_fontes_decide_e_gostei_entra_na_rotacao(tmp_path: Path):
    origem_a, origem_b = tmp_path / "a", tmp_path / "b"
    _png(_figura(28, 12, (32, 32)), origem_a / "Idle/a.png")
    _png(_figura(28, 9, (32, 32)), origem_b / "Idle/b.png")
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem_a, "pacote-a", (Parte("**", "character", "humanoid"),))
    _pacote(raiz, origem_b, "pacote-b", (Parte("**", "character", "humanoid"),))
    colecao = ReferenciasAtivas.carregar(raiz, _config(tmp_path / "r.yaml", "[pacote-a, pacote-b]"))
    fontes = fontes_do_exemplo(colecao, "character", "humanoid", 28)

    assert escolher_exemplo(colecao, fontes, ["pacote:pacote-b", "pacote:pacote-a"]).pacote == "pacote-b"
    assert escolher_exemplo(colecao, fontes, ["pacote:pacote-a"]).pacote == "pacote-a"

    meu = CandidatoDeGostei(asset_id="asset_meu", rgba=_figura(30, 14, (48, 48)))
    gostei = escolher_exemplo(colecao, fontes, [FONTE_GOSTEI, "pacote:pacote-a"], gostei=[meu])
    assert (gostei.origem, gostei.asset_id) == ("gostei", "asset_meu")
    assert "um asset seu marcado com \"gostei\": asset_meu" in gostei.texto


def test_em_ousado_o_exemplo_sai_do_estilo_de_qualquer_altura(tmp_path: Path):
    colecao = _colecao(
        tmp_path,
        {"Idle/gigante.png": _figura(50, 20, (56, 56)), "Idle/heroi.png": _figura(28, 12, (32, 32))},
    )
    (porte,) = fontes_do_exemplo(colecao, "character", "humanoid", 28).values()
    assert [q.arquivo for q in porte] == ["Idle/heroi.png"], "o porte só traz o da altura do corpo"
    (estilo,) = fontes_do_exemplo(colecao, "character", "humanoid", 28, por_estilo=True).values()
    assert {q.arquivo for q in estilo} == {"Idle/heroi.png", "Idle/gigante.png"}


def test_pacote_que_exige_atribuicao_nao_vira_exemplo(tmp_path: Path):
    origem = tmp_path / "origem"
    _png(_figura(28, 12, (32, 32)), origem / "Idle/a.png")
    raiz = tmp_path / "referencias"
    _pacote(raiz, origem, "cc-by", (Parte("**", "character", "humanoid"),), licenca="CC-BY-4.0")
    config = tmp_path / "r.yaml"
    _config(config, "[{cc-by: {aceitar_atribuicao: true}}]")
    colecao = ReferenciasAtivas.carregar(raiz, config)
    assert colecao.quadros, "aceito como referência de estilo"
    assert fontes_do_exemplo(colecao, "character", "humanoid", 28) == {}, "mas só CC0 vira exemplo"


# ---------------------------------------------------------------------------
# O olho do app
# ---------------------------------------------------------------------------
def test_olho_aponta_so_os_desvios_com_posicao(tmp_path: Path):
    colecao = _colecao(tmp_path, {f"Idle/h{i}.png": _figura(26 + i % 3, 9 + i, (32, 32)) for i in range(6)})

    parecido = _figura(28, 11, (48, 48))
    assert olhar_desenho(parecido, colecao, tipo="character", corpo="humanoid", altura_do_corpo=28).desvios == ()

    # Um desenho largo e vazado: preenchimento baixo e proporção fora.
    largo = np.zeros((48, 48, 4), dtype=np.uint8)
    largo[18:46, 4:44] = (*ESCURO, 255)
    largo[19:45, 5:43] = 0
    relatorio = olhar_desenho(largo, colecao, tipo="character", corpo="humanoid", altura_do_corpo=28)
    codigos = {d.codigo for d in relatorio.desvios}
    assert {"PREENCHIMENTO", "PROPORCAO"} <= codigos
    texto = "\n".join(relatorio.linhas())
    assert texto.startswith("olho do app (contra 6 quadros de 1 pacotes do mesmo porte, 23–33 px de altura):")
    assert "caixa x4–43 y18–45" in texto and "referências" in texto


def test_olho_sem_referencias_diz_isso_e_ainda_mede_o_contraste():
    rgba = np.zeros((8, 8, 4), dtype=np.uint8)
    rgba[2:6, 2:6] = (200, 50, 50, 255)
    relatorio = olhar_desenho(rgba, None, tipo="prop", corpo=None, altura_do_corpo=None)
    assert relatorio.cabecalho.startswith("olho do app (sem referências ativas de prop")
    assert relatorio.linhas() == [f"{relatorio.cabecalho}: nada fora da faixa"]


def test_contraste_por_camada_atravessa_o_contorno():
    # Duas camadas do mesmo vermelho separadas por uma coluna de contorno, e
    # uma terceira, clara, encostada na segunda.
    rgba = np.zeros((4, 9, 4), dtype=np.uint8)
    rgba[:, 0:3] = (180, 40, 40, 255)
    rgba[:, 3] = (*ESCURO, 255)
    rgba[:, 4:7] = (180, 40, 40, 255)
    rgba[:, 7:9] = (250, 230, 200, 255)
    linhas = ["000111122"] * 4
    pares = contraste_por_camada(rgba, ["capa", "tronco", "rosto"], linhas, "#14141e")

    por_par = {(p["a"], p["b"]): round(p["dL"]) for p in pares}
    assert por_par[("capa", "tronco")] == 0, "o contorno de 1 px não separa os valores"
    assert por_par[("tronco", "rosto")] > 8


def test_iou_acha_a_copia_em_qualquer_posicao():
    px = ["..aa..", ".abba.", "abbbba", ".abba.", "..aa.."]
    rgba = np.zeros((20, 20, 4), dtype=np.uint8)
    for y, linha in enumerate(px):
        for x, c in enumerate(linha):
            if c != ".":
                rgba[7 + y, 9 + x] = (90, 90, 200, 255)
    assert iou_com_o_exemplo(rgba, px) == pytest.approx(1.0)
    assert repete_o_exemplo(rgba, px, 0.85) == pytest.approx(1.0)
    assert repete_o_exemplo(rgba, ["aaaaaa"], 0.85) is None
    assert repete_o_exemplo(rgba, px, None) is None, "sem limiar configurado, a guarda não roda"
