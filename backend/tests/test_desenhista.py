"""Gaveta `desenhista-v1`: receita, rasterizador e o caminho até o asset.

Plano desenhista, Fase 1. O contrato de gavetas (``tests/contract``) já cobra
o básico desta gaveta sozinho, com a receita de ``exemplo_contrato.json``.
Aqui fica o que é dela: cada forma com um resultado conhecido, o espelho por
camada, as mensagens de erro em português e o pedido indo da API ao PNG.

Os resultados são escritos como texto — uma linha por linha da grade, a chave
da paleta em cada célula e ``.`` no transparente — porque é assim que um
erro de um pixel aparece na hora de ler a falha.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.generation.engines.desenhista.engine import (
    MENSAGEM_SEM_RECEITA,
    DesenhistaEngine,
)
from assetflow.generation.engines.desenhista.rasterizador import desenhar
from assetflow.generation.engines.desenhista.receita import ReceitaInvalida, ler_receita
from assetflow.generation.kernel.contracts import (
    CancellationToken,
    EngineExecutionContext,
)
from assetflow.generation.kernel.exceptions import InvalidGenerationRequest
from assetflow.generation.schemas import (
    AssetGenerationRequest,
    AssetOutputOverrides,
    Capability,
    EngineRuntimeConfig,
    EngineSelector,
    ImageGenerationRequest,
    OutputSpec,
    PromptSpec,
)
from tests.conftest import BACKEND_ROOT, process_next_job, run

PASTA = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista"
POCAO = PASTA / "exemplos" / "pocao_16x16.json"
ID = "desenhista-v1"

PALETA = {"a": "#3a6ea5", "b": "#ffffff", "c": "#d4a017", "k": "#2d3436"}


def _receita(*camadas: dict, paleta: dict | None = None, **extra) -> dict:
    return {"paleta": paleta or PALETA, "camadas": list(camadas), **extra}


def _camada(*ops: dict, **extra) -> dict:
    return {"ops": list(ops), **extra}


def _grade(receita: dict, largura: int, altura: int) -> list[str]:
    return desenhar(ler_receita(receita), largura, altura).grade.linhas()


def _uma_op(op: dict, largura: int, altura: int) -> list[str]:
    return _grade(_receita(_camada(op)), largura, altura)


# ---------------------------------------------------------------------------
# Formas, com resultado conhecido
# ---------------------------------------------------------------------------
def test_ret_cheio():
    assert _uma_op({"ret": [1, 1, 3, 2], "cor": "a"}, 5, 4) == [
        ".....",
        ".aaa.",
        ".aaa.",
        ".....",
    ]


def test_ret_so_contorno():
    assert _uma_op({"ret": [0, 0, 5, 4], "cor": "a", "contorno": True}, 5, 4) == [
        "aaaaa",
        "a...a",
        "a...a",
        "aaaaa",
    ]


def test_elipse_usa_o_centro_de_cada_celula():
    """Num 4×4, os cantos ficam de fora: o centro deles cai fora da elipse."""
    assert _uma_op({"elipse": [0, 0, 4, 4], "cor": "a"}, 4, 4) == [
        ".aa.",
        "aaaa",
        "aaaa",
        ".aa.",
    ]


def test_elipse_so_contorno():
    assert _uma_op({"elipse": [0, 0, 4, 4], "cor": "a", "contorno": True}, 4, 4) == [
        ".aa.",
        "a..a",
        "a..a",
        ".aa.",
    ]


def test_linha_em_degraus_regulares():
    """2:1 — degraus de dois pixels, como uma linha limpa de pixel art."""
    assert _uma_op({"linha": [0, 0, 4, 2], "cor": "a"}, 5, 3) == [
        "a....",
        ".aa..",
        "...aa",
    ]


def test_linha_com_varios_pontos_vira_polilinha():
    assert _uma_op({"linha": [0, 0, 4, 0, 4, 4], "cor": "a"}, 5, 5) == [
        "aaaaa",
        "....a",
        "....a",
        "....a",
        "....a",
    ]


def test_linha_e_a_mesma_nos_dois_sentidos():
    """Sem isso, a aresta de um polígono e uma linha sobre ela não coincidem."""
    ida = _uma_op({"linha": [0, 0, 6, 3], "cor": "a"}, 7, 4)
    volta = _uma_op({"linha": [6, 3, 0, 0], "cor": "a"}, 7, 4)
    assert ida == volta


def test_poligono_cheio():
    assert _uma_op({"poligono": [0, 0, 4, 0, 0, 4], "cor": "a"}, 5, 5) == [
        "aaaaa",
        "aaaa.",
        "aaa..",
        "aa...",
        "a....",
    ]


def test_poligono_so_contorno():
    assert _uma_op({"poligono": [0, 0, 4, 0, 0, 4], "cor": "a", "contorno": True}, 5, 5) == [
        "aaaaa",
        "a..a.",
        "a.a..",
        "aa...",
        "a....",
    ]


def test_balde_preenche_a_regiao_fechada():
    receita = _receita(
        _camada({"ret": [0, 0, 5, 5], "cor": "k", "contorno": True}),
        _camada({"balde": [2, 2], "cor": "a"}),
    )
    assert _grade(receita, 5, 5) == [
        "kkkkk",
        "kaaak",
        "kaaak",
        "kaaak",
        "kkkkk",
    ]


def test_balde_no_transparente_para_na_linha():
    receita = _receita(_camada({"linha": [2, 0, 2, 2], "cor": "k"}, {"balde": [0, 0], "cor": "a"}))
    assert _grade(receita, 5, 3) == ["aak..", "aak..", "aak.."]


def test_px_mantem_com_ponto_e_apaga_com_hifen():
    receita = _receita(_camada({"ret": [0, 0, 4, 2], "cor": "a"}, {"px": ["b.-b"], "em": [0, 0]}))
    assert _grade(receita, 4, 2) == ["ba.b", "aaaa"]


def test_camadas_seguintes_pintam_por_cima():
    receita = _receita(
        _camada({"ret": [0, 0, 3, 1], "cor": "a"}, nome="fundo"),
        _camada({"ret": [1, 0, 1, 1], "cor": "b"}, nome="detalhe"),
    )
    assert _grade(receita, 3, 1) == ["aba"]


# ---------------------------------------------------------------------------
# Espelho por camada
# ---------------------------------------------------------------------------
def test_espelho_x_em_largura_par():
    receita = _receita(_camada({"px": ["ab"], "em": [0, 0]}, espelho="x"))
    assert _grade(receita, 6, 1) == ["ab..ba"]


def test_espelho_x_em_largura_impar_mantem_a_coluna_do_meio():
    """Com largura 5 o centro é a coluna 2, que é o próprio espelho."""
    receita = _receita(_camada({"px": ["abc"], "em": [0, 0]}, espelho="x"))
    assert _grade(receita, 5, 1) == ["abcba"]


def test_espelho_x_de_uma_forma_em_largura_impar():
    receita = _receita(_camada({"linha": [0, 0, 2, 2], "cor": "a"}, espelho="x"))
    assert _grade(receita, 5, 3) == [
        "a...a",
        ".a.a.",
        "..a..",
    ]


def test_espelho_y_em_altura_impar():
    receita = _receita(_camada({"px": ["a", "b", "c"], "em": [0, 0]}, espelho="y"))
    assert _grade(receita, 1, 5) == ["a", "b", "c", "b", "a"]


def test_espelho_xy_preenche_os_quatro_quadrantes():
    receita = _receita(_camada({"px": ["ab", "c."], "em": [0, 0]}, espelho="xy"))
    assert _grade(receita, 4, 4) == [
        "abba",
        "c..c",
        "c..c",
        "abba",
    ]


def test_espelho_nao_apaga_o_que_a_camada_pintou_do_outro_lado():
    """O espelho completa o desenho; um detalhe assimétrico explícito fica."""
    receita = _receita(_camada({"px": ["a....b"], "em": [0, 0]}, espelho="x"))
    assert _grade(receita, 6, 1) == ["a....b"]


def test_espelho_so_vale_para_a_propria_camada():
    receita = _receita(
        _camada({"px": ["a"], "em": [0, 0]}, nome="espelhada", espelho="x"),
        _camada({"px": ["b"], "em": [1, 0]}, nome="solta"),
    )
    assert _grade(receita, 4, 1) == ["ab.a"]


def test_balde_em_camada_espelhada_e_erro():
    """O balde preenche antes da cópia: vazaria pelo lado ainda vazio."""
    receita = _receita(
        _camada(
            {"ret": [0, 0, 3, 3], "cor": "k", "contorno": True},
            {"balde": [1, 1], "cor": "a"},
            nome="corpo",
            espelho="x",
        )
    )
    with pytest.raises(ReceitaInvalida) as erro:
        ler_receita(receita)
    mensagem = str(erro.value)
    assert "camadas[0] ('corpo').ops[1] (balde)" in mensagem
    assert "não pode ficar em camada com 'espelho'" in mensagem


def test_balde_depois_da_camada_espelhada_funciona():
    """O caminho que a mensagem de erro indica: o balde numa camada seguinte."""
    receita = _receita(
        _camada({"linha": [0, 0, 0, 2, 2, 2], "cor": "k"}, {"linha": [0, 0, 2, 0], "cor": "k"},
                nome="borda", espelho="x"),
        _camada({"balde": [2, 1], "cor": "a"}, nome="miolo"),
    )
    assert _grade(receita, 5, 3) == ["kkkkk", "kaaak", "kkkkk"]


def test_a_pocao_de_exemplo():
    """O exemplo que a documentação mostra é o que a gaveta desenha."""
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    assert _grade(receita, 16, 16) == [
        "................",
        "......mmmm......",
        "......mmmm......",
        "......kvvk......",
        "......kvvk......",
        "......kvvk......",
        "....kkvvvvkk....",
        "....kbvvvvvk....",
        "...kvvbvvvvvk...",
        "...kRRRRRRRRk...",
        "...krrrrrrrrk...",
        "...krrrrrrrrk...",
        "....krrrrrrk....",
        "....kkrrrrkk....",
        "......kkkk......",
        "................",
    ]


# ---------------------------------------------------------------------------
# Fora da grade
# ---------------------------------------------------------------------------
def test_operacao_parcialmente_fora_e_recortada_com_aviso():
    desenho = desenhar(ler_receita(_receita(_camada({"ret": [2, 2, 4, 4], "cor": "a"}))), 4, 4)

    assert desenho.grade.linhas() == ["....", "....", "..aa", "..aa"]
    assert len(desenho.avisos) == 1
    assert "12 pixel(s) fora da grade 4×4" in desenho.avisos[0]
    assert "camadas[0]" in desenho.avisos[0]


def test_operacao_inteira_fora_da_grade_e_erro():
    with pytest.raises(ReceitaInvalida, match="inteira fora da grade 4×4"):
        desenhar(ler_receita(_receita(_camada({"ret": [10, 10, 2, 2], "cor": "a"}))), 4, 4)


def test_balde_fora_da_grade_e_erro():
    with pytest.raises(ReceitaInvalida, match=r"\(9, 0\) está fora da grade"):
        desenhar(ler_receita(_receita(_camada({"balde": [9, 0], "cor": "a"}))), 4, 4)


def test_grade_declarada_diferente_do_pedido_e_erro():
    receita = _receita(_camada({"ret": [0, 0, 1, 1], "cor": "a"}), grade=[16, 16])
    with pytest.raises(ReceitaInvalida, match="desenhada para 16×16, mas o pedido é 32×32"):
        desenhar(ler_receita(receita), 32, 32)


# ---------------------------------------------------------------------------
# Formato: cada erro diz onde e o que era esperado
# ---------------------------------------------------------------------------
_RET = {"ret": [0, 0, 1, 1], "cor": "a"}


@pytest.mark.parametrize(
    ("receita", "trecho"),
    [
        ("não é objeto", "precisa ser um objeto JSON"),
        ({"camadas": [_camada(_RET)]}, "precisa de 'paleta'"),
        (_receita(_camada(_RET), paleta={"ab": "#000000"}), "exatamente um caractere"),
        (_receita(_camada(_RET), paleta={".": "#000000"}), "é reservada"),
        (_receita(_camada(_RET), paleta={"a": "azul"}), "não é uma cor no formato"),
        ({"paleta": PALETA, "camada": []}, "chave desconhecida 'camada'"),
        ({"paleta": PALETA, "camadas": []}, "pelo menos uma camada"),
        (_receita(_camada({"ret": [0, 0, 1, 1], "cor": "z"})), "a cor 'z' não está na paleta"),
        (_receita(_camada({"ret": [0, 0, 1], "cor": "a"})), "[x, y, largura, altura]"),
        (_receita(_camada({"ret": [0, 0, 0, 1], "cor": "a"})), "pelo menos 1"),
        (_receita(_camada({"ret": [True, 0, 1, 1], "cor": "a"})), "esperava"),
        (_receita(_camada({"ret": [0, 0, 1, 1]})), "falta 'cor'"),
        (_receita(_camada({"circulo": [0, 0, 1], "cor": "a"})), "exatamente uma forma"),
        (_receita(_camada({"ret": [0, 0, 1, 1], "linha": [0, 0, 1, 1], "cor": "a"})), "exatamente uma forma"),
        (_receita(_camada({"ret": [0, 0, 1, 1], "cor": "a", "grossura": 2})), "chave desconhecida 'grossura'"),
        (_receita(_camada({"linha": [0, 0, 1], "cor": "a"})), "pelo menos 2 pontos"),
        (_receita(_camada({"poligono": [0, 0, 1, 1], "cor": "a"})), "pelo menos 3 pontos"),
        (_receita(_camada({"px": ["az"], "em": [0, 0]})), "caractere 'z'"),
        (_receita(_camada({"px": ["..."], "em": [0, 0]})), "não pintam nada"),
        (_receita(_camada({"px": ["a"]})), "falta 'em'"),
        (_receita(_camada(_RET, espelho="z")), "'espelho' aceita"),
        (_receita(_camada(_RET, nome="a"), _camada(_RET, nome="a")), "nome 'a' já foi usado"),
    ],
)
def test_receita_invalida_diz_o_que_esta_errado(receita, trecho):
    with pytest.raises(ReceitaInvalida) as erro:
        ler_receita(receita)
    assert trecho in str(erro.value)


def test_o_erro_aponta_a_camada_e_a_operacao():
    receita = _receita(
        _camada(_RET, nome="silhueta"),
        _camada(_RET, {"ret": [0, 0, 1, 1], "cor": "z"}, nome="vidro"),
    )
    with pytest.raises(ReceitaInvalida, match=r"camadas\[1\] \('vidro'\)\.ops\[1\] \(ret\)"):
        ler_receita(receita)


# ---------------------------------------------------------------------------
# A gaveta, chamada direto
# ---------------------------------------------------------------------------
def _pedido(receita: dict | None, *, lado: int = 16, variacoes: int = 1, max_cores=None):
    opcoes = {ID: {"receita": receita}} if receita is not None else {}
    return ImageGenerationRequest(
        capability=Capability.parse("prop.pixel"),
        prompt=PromptSpec(positive="poção"),
        output=OutputSpec(
            width=512,
            height=512,
            variations=variacoes,
            logical_width=lado,
            logical_height=lado,
            max_colors=max_cores,
        ),
        engine_options=opcoes,
    )


def _gerar(pedido: ImageGenerationRequest):
    async def cenario():
        motor = DesenhistaEngine()
        await motor.initialize(EngineRuntimeConfig(engine_id=ID))
        contexto = EngineExecutionContext(job_id="job_teste", cancellation=CancellationToken())
        return await motor.generate(pedido, contexto)

    return run(cenario())


def test_entrega_a_grade_logica_com_as_cores_exatas():
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    resultado = _gerar(_pedido(receita))

    artefato = resultado.artifacts[0]
    imagem = Image.open(io.BytesIO(artefato.data)).convert("RGBA")
    assert imagem.size == (16, 16) == (artefato.width, artefato.height)

    alfas = {pixel[3] for pixel in imagem.getdata()}
    assert alfas == {0, 255}, "alpha binário: pintado ou transparente"
    cores = {pixel[:3] for pixel in imagem.getdata() if pixel[3] == 255}
    esperadas = {
        tuple(int(valor[i : i + 2], 16) for i in (1, 3, 5))
        for valor in receita["paleta"].values()
    }
    assert cores == esperadas
    # A rolha é o pixel (6, 1); "m" é "#8b5a2b".
    assert imagem.getpixel((6, 1)) == (0x8B, 0x5A, 0x2B, 255)
    assert artefato.seed is None
    assert artefato.metadata["camadas"] == [c["nome"] for c in receita["camadas"]]


def test_sem_receita_falha_dizendo_como_usar():
    with pytest.raises(InvalidGenerationRequest) as erro:
        _gerar(_pedido(None))
    assert erro.value.message == MENSAGEM_SEM_RECEITA
    assert "MCP" in erro.value.message


def test_receita_invalida_vira_erro_do_pedido():
    with pytest.raises(InvalidGenerationRequest, match="receita inválida: .*cor 'z'"):
        _gerar(_pedido(_receita(_camada({"ret": [0, 0, 1, 1], "cor": "z"}))))


def test_mais_de_uma_variacao_e_recusada():
    receita = _receita(_camada(_RET))
    with pytest.raises(InvalidGenerationRequest, match="uma imagem por receita"):
        _gerar(_pedido(receita, variacoes=2))


def test_cores_alem_do_limite_do_pedido_sao_recusadas():
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    with pytest.raises(InvalidGenerationRequest, match="usa 6 cores .* permite 4"):
        _gerar(_pedido(receita, max_cores=4))


def test_avisos_de_recorte_chegam_ao_resultado():
    receita = _receita(_camada({"ret": [14, 0, 4, 1], "cor": "a"}))
    resultado = _gerar(_pedido(receita))
    assert any("recortados" in aviso for aviso in resultado.warnings)


def test_manifesto_declara_o_que_o_codigo_cumpre():
    manifesto = DesenhistaEngine().manifest()
    assert manifesto.id == ID
    assert manifesto.catalog.family.value == "agentic"
    assert manifesto.catalog.exact_resolution is True
    assert manifesto.catalog.hidden is False
    assert manifesto.catalog.dev_only is False
    assert manifesto.supports.seed is False
    assert manifesto.limits.max_variations == 1
    assert manifesto.resources.gpu_required is False


# ---------------------------------------------------------------------------
# Pelo sistema inteiro: job, kernel, Pixel Exact, Optimizer
# ---------------------------------------------------------------------------
def _pedido_de_asset(
    receita: dict | None, *, motor: EngineSelector | None = None, variacoes: int = 1
) -> AssetGenerationRequest:
    return AssetGenerationRequest(
        project_id="project_desenhista",
        profile="pixel_prop_64",
        prompt="poção vermelha 16x16",
        output=AssetOutputOverrides(variations=variacoes),
        engine=motor or EngineSelector(mode="manual", engine_id=ID),
        engine_options={ID: {"receita": receita}} if receita is not None else {},
    )


def _rodar(container: AppContainer, pedido: AssetGenerationRequest):
    job = run(container.service.submit(pedido))
    run(process_next_job(container))
    return run(container.service.get_job(job.id))


def test_a_desenhista_aparece_no_catalogo(container: AppContainer):
    entradas = {e.engine_id: e for e in run(container.service.engine_catalog())}
    assert ID in entradas
    assert entradas[ID].supports_exact_resolution is True
    assert entradas[ID].engine_family == "agentic"


def test_receita_vira_asset_pixel_exact_aprovado(container: AppContainer):
    container.registry.enable(ID)
    receita = json.loads(POCAO.read_text(encoding="utf-8"))

    job = _rodar(container, _pedido_de_asset(receita))

    assert job.status.value == "completed", job.error
    assert job.engine.id == ID
    variante = job.asset.variants[0]
    assert (variante.logical_width, variante.logical_height) == (16, 16)
    assert variante.pixel_exact is True
    assert variante.status == "approved"
    assert variante.color_count == 6


def test_sem_receita_o_job_falha_com_a_mensagem(container: AppContainer):
    """Escolhida à mão, a gaveta não vira outra: o job falha dizendo por quê."""
    container.registry.enable(ID)
    job = _rodar(container, _pedido_de_asset(None))

    assert job.status.value == "failed"
    assert job.error.code == "invalid_request"
    assert job.error.message == MENSAGEM_SEM_RECEITA


def test_varias_variacoes_sao_recusadas_antes_dos_lotes(container: AppContainer):
    """Com max_variations 1 o kernel dividiria em lotes — e cada lote seria a
    mesma receita, a mesma imagem. A regra genérica do kernel recusa antes."""
    container.registry.enable(ID)
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    job = _rodar(container, _pedido_de_asset(receita, variacoes=3))

    assert job.status.value == "failed"
    assert job.error.code == "invalid_request"
    assert "cópias idênticas" in job.error.message
    assert "3" in job.error.message


def test_o_exemplo_do_contrato_e_uma_receita_valida():
    exemplo = json.loads((PASTA / "exemplo_contrato.json").read_text(encoding="utf-8"))
    desenho = desenhar(ler_receita(exemplo["receita"]), 32, 32)
    assert not desenho.avisos
    linhas = desenho.grade.linhas()
    # Espelhado em x: cada linha é um palíndromo, salvo o brasão (camada solta).
    assert linhas[20] == linhas[20][::-1]


def test_exemplos_sao_json_valido():
    for caminho in Path(PASTA / "exemplos").glob("*.json"):
        ler_receita(json.loads(caminho.read_text(encoding="utf-8")))
