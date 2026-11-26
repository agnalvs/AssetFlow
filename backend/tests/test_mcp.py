"""Servidor MCP, sem o protocolo: remendo, laudo e as três ferramentas.

Plano desenhista, Fase 2. Estes testes não precisam do SDK do MCP (que é
opcional): exercitam :mod:`assetflow.mcp.servico`, que faz todo o trabalho, e
os textos que o Claude lê. O protocolo em si — nomes, descrições, imagem,
erro — fica em ``test_mcp_servidor.py``, pulado sem o SDK.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

from assetflow.bootstrap import AppContainer
from assetflow.mcp.laudo import FORMATO_RECEITA, MAX_POSICOES, _onde, formatar_laudo
from assetflow.mcp.remendo import RemendoInvalido, aplicar_remendo
from assetflow.mcp.servico import MOTOR, ErroDoPedido, ServicoDesenhista
from assetflow.pixel_knowledge import SEM_CORPO, USO_DO_MOLDE, BaseDeConhecimento
from tests.conftest import BACKEND_ROOT, run

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"

#: Um sprite feito para não passar: 48 pixels soltos, encostando nas laterais.
RUIDO = {
    "paleta": {"k": "#2d3436", "a": "#3a6ea5", "c": "#d4a017", "r": "#b03a2e"},
    "camadas": [{"nome": "ruido", "ops": [{"px": [
        "k.a.c.r.k.a.c.r.",
        ".r.k.a.c.r.k.a.c",
        "a.c.r.k.a.c.r.k.",
        "................",
        "c.r.k.a.c.r.k.a.",
        ".k.a.c.r.k.a.c.r",
        "................",
        "r.k.a.c.r.k.a.c.",
    ], "em": [0, 4]}]}],
}


def _pocao() -> dict:
    return json.loads(POCAO.read_text(encoding="utf-8"))


@pytest.fixture
def servico(container: AppContainer) -> ServicoDesenhista:
    # A suíte desliga tudo fora das gavetas de referência; o MCP pede a
    # desenhista pelo nome, então ela precisa estar ligada.
    container.registry.enable(MOTOR)
    return ServicoDesenhista(container)


def _id(laudo: str) -> str:
    """O id do asset, que a linha do veredito traz em segundo lugar."""
    linha = next(linha for linha in laudo.splitlines() if " · asset_" in linha)
    return linha.split(" · ")[1]


# ---------------------------------------------------------------------------
# Remendo
# ---------------------------------------------------------------------------
_BASE = {
    "grade": [4, 4],
    "paleta": {"a": "#111111", "b": "#222222"},
    "camadas": [
        {"nome": "fundo", "ops": [{"ret": [0, 0, 4, 4], "cor": "a"}]},
        {"nome": "meio", "ops": [{"ret": [1, 1, 2, 2], "cor": "b"}]},
        {"nome": "topo", "ops": [{"px": ["b"], "em": [0, 0]}]},
    ],
}


def _nomes(receita: dict) -> list[str]:
    return [camada["nome"] for camada in receita["camadas"]]


def test_remendo_junta_a_paleta_por_chave():
    receita, resumo = aplicar_remendo(_BASE, {"paleta": {"b": "#ff0000", "c": "#00ff00"}})
    assert receita["paleta"] == {"a": "#111111", "b": "#ff0000", "c": "#00ff00"}
    assert resumo.paleta == ["b", "c"]
    assert _BASE["paleta"]["b"] == "#222222", "a base não pode mudar"


def test_remendo_troca_a_camada_no_mesmo_lugar():
    nova = {"nome": "meio", "ops": [{"ret": [0, 0, 1, 1], "cor": "a"}]}
    receita, resumo = aplicar_remendo(_BASE, {"camadas": [nova]})
    assert _nomes(receita) == ["fundo", "meio", "topo"]
    assert receita["camadas"][1] == nova
    assert resumo.trocadas == ["meio"]


def test_remendo_acrescenta_camada_nova_no_fim():
    receita, resumo = aplicar_remendo(
        _BASE, {"camadas": [{"nome": "brilho", "ops": [{"px": ["a"], "em": [3, 3]}]}]}
    )
    assert _nomes(receita) == ["fundo", "meio", "topo", "brilho"]
    assert resumo.acrescentadas == ["brilho"]


def test_remendo_remove_camada():
    receita, resumo = aplicar_remendo(_BASE, {"camadas": [{"nome": "meio", "remover": True}]})
    assert _nomes(receita) == ["fundo", "topo"]
    assert resumo.texto() == "removeu camada meio"


def test_remendo_congela_o_nome_das_camadas_sem_nome():
    """Remover a primeira não pode renomear a segunda de "camada 2" para "camada 1"."""
    base = {
        "paleta": {"a": "#111111"},
        "camadas": [
            {"ops": [{"ret": [0, 0, 1, 1], "cor": "a"}]},
            {"ops": [{"ret": [1, 1, 1, 1], "cor": "a"}]},
        ],
    }
    receita, _ = aplicar_remendo(base, {"camadas": [{"nome": "camada 1", "remover": True}]})
    assert _nomes(receita) == ["camada 2"]


def test_resumo_do_remendo_em_uma_linha():
    _, resumo = aplicar_remendo(
        _BASE,
        {
            "paleta": {"a": "#000000"},
            "camadas": [
                {"nome": "topo", "ops": [{"px": ["a"], "em": [0, 0]}]},
                {"nome": "novo", "ops": [{"px": ["a"], "em": [1, 0]}]},
            ],
        },
    )
    assert resumo.texto() == "paleta a; trocou camada topo; acrescentou camada novo"


@pytest.mark.parametrize(
    ("parcial", "trecho"),
    [
        ("texto", "precisa ser um objeto"),
        ({}, "não muda nada"),
        ({"cores": {}}, "chave desconhecida"),
        ({"grade": [8, 8], "paleta": {"a": "#000000"}}, "não muda a grade"),
        ({"camadas": [{"ops": []}]}, "precisa de 'nome'"),
        ({"camadas": [{"nome": "x", "remover": True}]}, "não tem camada 'x'"),
        ({"camadas": [{"nome": "meio", "remover": True, "ops": []}]}, "não se mistura"),
        ({"camadas": [{"nome": "meio", "remover": False}]}, "só aceita true"),
        (
            {"camadas": [{"nome": n, "remover": True} for n in ("fundo", "meio", "topo")]},
            "removeu todas",
        ),
    ],
)
def test_remendo_invalido_diz_por_que(parcial, trecho):
    with pytest.raises(RemendoInvalido) as erro:
        aplicar_remendo(_BASE, parcial)
    assert trecho in str(erro.value)


# ---------------------------------------------------------------------------
# Onde está cada problema
# ---------------------------------------------------------------------------
def test_pixels_isolados_tem_teto_de_oito_e_mais_n():
    metricas = {
        "orphan_pixel_count": 11,
        "orphan_positions": [[x, 0] for x in range(11)],
    }
    onde = _onde({"code": "PX-WARN-ORPHAN"}, metricas, {})
    assert onde == "(0,0) (1,0) (2,0) (3,0) (4,0) (5,0) (6,0) (7,0) +3"
    assert MAX_POSICOES == 8


def test_pixels_isolados_sem_sobra_nao_mostram_mais():
    metricas = {"orphan_pixel_count": 2, "orphan_positions": [[1, 2], [3, 4]]}
    assert _onde({"code": "PX-WARN-ORPHAN"}, metricas, {}) == "(1,2) (3,4)"


@pytest.mark.parametrize(
    ("caixa", "lados"),
    [
        ([0, 3, 5, 6], "esquerda"),
        ([2, 0, 5, 6], "cima"),
        ([2, 3, 15, 6], "direita"),
        ([2, 3, 5, 15], "baixo"),
        ([0, 0, 15, 15], "cima, baixo, esquerda, direita"),
    ],
)
def test_borda_diz_o_lado(caixa, lados):
    aviso = {"code": "PX-WARN-BORDER", "detail": {"bounding_box": caixa}}
    assert _onde(aviso, {}, {"width": 16, "height": 16}) == lados


def test_contorno_fragmentado_nao_tem_onde():
    """O validador só conta os pedaços; o laudo não inventa um lugar."""
    aviso = {"code": "PX-WARN-OUTLINE-FRAGMENTED", "detail": {"count": 10}}
    assert _onde(aviso, {"bounding_box": [0, 0, 3, 3]}, {"width": 16, "height": 16}) == ""


def test_reprovado_lista_as_falhas():
    from types import SimpleNamespace

    spec = SimpleNamespace(
        palette=SimpleNamespace(max_colors=8), background=SimpleNamespace(mode="transparent")
    )
    variante = SimpleNamespace(
        status="rejected", quality_score=40, pixel_exact=False,
        logical_width=16, logical_height=16, color_count=12,
    )
    validacao = {
        "acceptance": {
            "status": "rejected",
            "pixel_exact": False,
            "quality_score": 40,
            "quality_threshold": 70,
            "failures": [{"code": "PX-COLOR-001", "message": "cores únicas: 12 (limite: 8)"}],
        }
    }
    laudo = formatar_laudo(
        pedido="teste", asset_id="asset_x", variante=variante, spec=spec,
        validacao=validacao, otimizacao=None, avisos_receita=[], caminho=Path("x.png"),
    )
    assert laudo.splitlines()[0] == "REPROVADO (falhou requisito técnico) · asset_x · teste"
    assert "Pixel Exact ✗" in laudo
    assert "falhas:\n- cores únicas: 12 (limite: 8)" in laudo


# ---------------------------------------------------------------------------
# consultar_pedido
# ---------------------------------------------------------------------------
def test_consultar_le_o_spec_e_traz_o_formato(servico: ServicoDesenhista):
    texto = servico.consultar("cavaleiro 32x32, 8 cores, sem fundo")

    assert texto.splitlines()[0] == (
        "pedido: cavaleiro 32x32, 8 cores, sem fundo (perfil pixel_character_32)"
    )
    assert "tipo: character · cavaleiro · categoria humanoid · corpo humanoid (inferido)" in texto
    assert "grade: 32×32 (do texto)" in texto
    assert "paleta: até 8 cores (do texto)" in texto
    assert "fundo: transparente (do texto)" in texto
    assert f"motor: {MOTOR}" in texto
    assert FORMATO_RECEITA in texto


def test_consultar_traz_o_recorte_da_base(servico: ServicoDesenhista):
    """Fase 3: depois do spec, as linhas da base que valem para o pedido."""
    texto = servico.consultar("cavaleiro 32x32, 8 cores, sem fundo")
    recorte = texto.split("\nconhecimento:\n", 1)[1]

    assert recorte.startswith("humanóide 32×32: cabeça y3–12 (10 px) · tronco y13–20 (8 px)")
    assert "cores: até 8, contorno incluído · paleta-mestra endesga-32" in recorte
    # Por padrão, só medidas e nomes de camadas: a receita do molde engessava o desenho.
    assert "{" not in recorte
    # Lote 8: depois do recorte, a linha dos temas da base consultável.
    recorte, temas = recorte.rsplit("\n", 1)
    assert temas.startswith("temas (consultar_base, regras que valem): contorno ")
    assert recorte.endswith("· a receita do molde-base vem com molde=true")
    # O recorte orienta e não muda o que o pedido virou.
    assert "estilo: contorno auto · sombreamento auto · luz não definida" in texto


def test_consultar_com_molde_traz_a_receita(servico: ServicoDesenhista):
    texto = servico.consultar("cavaleiro 32x32, 8 cores, sem fundo", molde=True)

    assert "molde humanoid_32x32: " in texto
    assert '{"grade":[32,32],"paleta":' in texto
    assert texto.rsplit("\n", 1)[0].endswith(USO_DO_MOLDE)  # e a linha dos temas


def test_consultar_sem_nada_da_base_diz_isso(container: AppContainer):
    container.conhecimento = BaseDeConhecimento.vazia()
    texto = ServicoDesenhista(container).consultar("cavaleiro 32x32")
    assert texto.endswith("conhecimento: (nada da base para este pedido)")


def test_perfil_de_48_poe_o_corpo_de_32_no_quadro(servico: ServicoDesenhista):
    """O quadro de 48 vem do profile, sem depender de o texto dizer "48x48"."""
    texto = servico.consultar("cavaleiro, 8 cores, sem fundo", "pixel_character_48")

    assert "grade: 48×48 (do perfil)" in texto
    assert "humanóide, corpo 32×32 num quadro 48×48: cabeça y19–28 (10 px)" in texto


def test_arqueira_no_quadro_de_48_traz_proporcoes_quadro_e_silhueta(servico: ServicoDesenhista):
    """O pedido real em que o recorte saiu sem medidas: "arqueira" não estava
    em `body_types`, e o corpo ficava `unknown`."""
    texto = servico.consultar("arqueira de capuz verde", "pixel_character_48")
    linhas = texto.split("\nconhecimento:\n", 1)[1].splitlines()

    assert "tipo: character · arqueira de capuz verde · categoria humanoid · corpo humanoid (inferido)" in texto
    assert linhas[0].startswith(
        "humanóide, corpo 32×32 num quadro 48×48: cabeça y19–28 (10 px) · tronco y29–36 (8 px)"
    )
    assert any(linha.startswith("quadro: corpo centrado entre x=23 e x=24") for linha in linhas)
    assert any(linha.startswith("silhueta: arma e escudo fora do corpo") for linha in linhas)
    assert SEM_CORPO not in texto


def test_corpo_deduzido_da_categoria_diz_a_origem(servico: ServicoDesenhista):
    texto = servico.consultar("astronauta de traje branco", "pixel_character_48")

    assert (
        "tipo: character · astronauta de traje branco · categoria humanoid · "
        "corpo humanoid (inferido da categoria) (inferido)"
    ) in texto
    assert "humanóide, corpo 32×32 num quadro 48×48" in texto


def test_lobo_continua_quadrupede(servico: ServicoDesenhista):
    texto = servico.consultar("lobo cinzento", "pixel_character_48")

    assert "categoria creature · corpo quadruped (inferido)" in texto
    assert "humanóide" not in texto and SEM_CORPO not in texto


def test_corpo_nao_identificado_e_dito_no_recorte(servico: ServicoDesenhista):
    """`creature` não implica corpo: sem termo que o nomeie, o recorte diz o
    que falta em vez de sair sem medidas em silêncio."""
    texto = servico.consultar("um monstro", "pixel_character_48")
    recorte = texto.split("\nconhecimento:\n", 1)[1]

    assert "corpo " not in texto.splitlines()[1]
    assert recorte.splitlines()[0] == SEM_CORPO


def test_consultar_sem_tamanho_usa_o_perfil(servico: ServicoDesenhista):
    texto = servico.consultar("uma espada", "pixel_prop_64")
    assert "grade: 64×64 (do perfil)" in texto


def test_perfil_que_nao_e_pixel_e_recusado(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="não é um profile de Pixel Art .*pixel_character_32"):
        servico.consultar("um castelo", "studio_character")


def test_pedido_vazio_e_recusado(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="pedido está vazio"):
        servico.consultar("   ")


# ---------------------------------------------------------------------------
# desenhar
# ---------------------------------------------------------------------------
def test_desenhar_aprovado(servico: ServicoDesenhista):
    laudo = run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao()))
    linhas = laudo.splitlines()

    assert linhas[0].startswith("APROVADO · asset_")
    assert linhas[0].endswith(" · poção vermelha 16x16")
    assert linhas[1] == "Pixel Exact ✓ · qualidade 100/100 (mínimo 70)"
    assert linhas[2] == "grade 16×16 · 6 de 12 cores · fundo transparente"
    assert "Optimizer: nada a corrigir" in linhas
    caminho = Path(linhas[-1].removeprefix("arquivo: "))
    assert caminho.exists() and caminho.suffix == ".png"
    assert Image.open(caminho).size == (16, 16)


def test_desenhar_nao_aprovado_diz_onde(servico: ServicoDesenhista):
    laudo = run(
        servico.desenhar(pedido="fagulhas 16x16", receita=RUIDO, perfil="pixel_prop_64")
    )

    assert laudo.startswith("NÃO APROVADO (qualidade abaixo do mínimo) · asset_")
    assert "  onde: (0,4) (2,4) (4,4) (6,4) (8,4) (10,4) (12,4) (14,4) +40" in laudo
    assert "  onde: esquerda, direita" in laudo
    # O contorno fragmentado aparece, mas sem lugar: o validador não o expõe.
    linhas = laudo.splitlines()
    contorno = next(i for i, linha in enumerate(linhas) if "o contorno está em" in linha)
    assert not linhas[contorno + 1].startswith("  onde:")
    assert "Optimizer: nenhum reparo seguro; manteve de propósito pixels isolados ×48" in laudo


def test_desenhar_recusa_receita_invalida_com_a_mensagem_da_gaveta(servico: ServicoDesenhista):
    receita = {"paleta": {"k": "#000000"}, "camadas": [{"ops": [{"ret": [0, 0, 1, 1], "cor": "z"}]}]}
    with pytest.raises(ErroDoPedido, match=r"receita inválida: .*a cor 'z' não está na paleta"):
        run(servico.desenhar(pedido="poção 16x16", receita=receita))


def test_desenhar_sem_receita_nem_base(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="falta 'receita'"):
        run(servico.desenhar(pedido="poção 16x16"))


def test_desenhar_sem_pedido(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="falta 'pedido'"):
        run(servico.desenhar(receita=_pocao()))


def test_avisos_de_recorte_entram_no_laudo(servico: ServicoDesenhista):
    receita = {"paleta": {"k": "#2d3436"}, "camadas": [
        {"nome": "corpo", "ops": [{"ret": [4, 4, 8, 8], "cor": "k"}, {"ret": [14, 0, 4, 2], "cor": "k"}]},
    ]}
    laudo = run(servico.desenhar(pedido="bloco 16x16", receita=receita))
    assert "avisos da receita:\n- camadas[0] ('corpo').ops[1] (ret): 4 pixel(s) fora da grade" in laudo
    # O aviso do kernel sobre negative prompt não é da receita e não entra.
    assert "negative" not in laudo


def test_sem_fallback_motor_desligado_falha_em_vez_de_virar_mock(
    container: AppContainer, servico: ServicoDesenhista
):
    """Motor escolhido é motor usado: sem a desenhista, nada de sprite de mock."""
    container.registry.disable(MOTOR)
    with pytest.raises(ErroDoPedido, match="desabilitad"):
        run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao()))
    assets = run(container.storage.assets.list(project_id="mcp"))
    assert not assets


# ---------------------------------------------------------------------------
# Remendo pelo serviço
# ---------------------------------------------------------------------------
def test_remendo_gera_asset_novo_e_mantem_a_base(servico: ServicoDesenhista):
    base = _id(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao())))

    laudo = run(
        servico.desenhar(
            base=base,
            receita={
                "paleta": {"r": "#2e8b57", "R": "#4fbf7f"},
                "camadas": [{"nome": "brilho", "ops": [{"px": ["b"], "em": [5, 7]}]}],
            },
        )
    )
    linhas = laudo.splitlines()
    assert linhas[0] == f"remendo de {base}: paleta r, R; trocou camada brilho"
    novo = _id(laudo)
    assert novo != base
    # O pedido e o perfil vieram da base.
    assert linhas[1].endswith(" · poção vermelha 16x16")

    verde = Image.open(Path(linhas[-1].removeprefix("arquivo: "))).convert("RGBA")
    assert verde.getpixel((7, 11)) == (0x2E, 0x8B, 0x57, 255)
    png_base, _ = run(servico.ver(base))
    vermelha = Image.open(io.BytesIO(png_base)).convert("RGBA")
    assert vermelha.getpixel((7 * 24, 11 * 24)) == (0xB0, 0x3A, 0x2E, 255), "a base ficou como era"


def test_remendo_de_remendo(servico: ServicoDesenhista):
    primeiro = _id(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao())))
    segundo = _id(run(servico.desenhar(base=primeiro, receita={"paleta": {"r": "#2e8b57"}})))
    terceiro = run(
        servico.desenhar(base=segundo, receita={"camadas": [{"nome": "brilho", "remover": True}]})
    )
    assert terceiro.startswith(f"remendo de {segundo}: removeu camada brilho")


def test_remendo_de_asset_que_nao_existe(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="não há asset 'asset_nada' no histórico"):
        run(servico.desenhar(base="asset_nada", receita={"paleta": {"a": "#000000"}}))


def test_remendo_invalido_vira_erro_do_pedido(servico: ServicoDesenhista):
    base = _id(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao())))
    with pytest.raises(ErroDoPedido, match="remendo inválido: .*não tem camada 'asa'"):
        run(servico.desenhar(base=base, receita={"camadas": [{"nome": "asa", "remover": True}]}))


def test_remendo_sem_receita(servico: ServicoDesenhista):
    base = _id(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao())))
    with pytest.raises(ErroDoPedido, match="com base, mande em 'receita' o que muda"):
        run(servico.desenhar(base=base))


# ---------------------------------------------------------------------------
# ver_asset
# ---------------------------------------------------------------------------
def test_ver_mostra_ampliada_silhueta_e_tamanho_real(servico: ServicoDesenhista):
    """Fase B2: o ``ver_asset`` devolve a mesma imagem do olhar que o ``desenhar``."""
    asset = _id(run(servico.desenhar(pedido="poção vermelha 16x16", receita=_pocao())))
    png, legenda = run(servico.ver(asset))

    imagem = Image.open(io.BytesIO(png)).convert("RGB")
    assert imagem.size == (588, 384)
    assert legenda == (
        f"{asset} · 16×16 · ampliado 24×, silhueta em preto e tamanho real (2× e 1×) · approved"
    )
    # Vizinho mais próximo: a rolha (6, 1) vira um bloco 24×24 da mesma cor.
    cores = {imagem.getpixel((6 * 24 + dx, 1 * 24 + dy)) for dx in range(24) for dy in range(24)}
    assert cores == {(0x8B, 0x5A, 0x2B)}
    # A silhueta (12×) começa depois do painel grande e do vão de 12 px: preta
    # onde há pixel, branca onde não há.
    assert imagem.getpixel((384 + 12 + 6 * 12 + 5, 1 * 12 + 5)) == (0, 0, 0)
    assert imagem.getpixel((384 + 12 + 5, 5)) == (255, 255, 255)


def test_ver_asset_inexistente(servico: ServicoDesenhista):
    with pytest.raises(ErroDoPedido, match="não há asset"):
        run(servico.ver("asset_nada"))
