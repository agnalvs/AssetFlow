"""Lote 8: a base por temas, com etiquetas, e consultar_base(tema)."""

from __future__ import annotations

import pytest

from assetflow.mcp.servico import ErroDoPedido, ServicoDesenhista
from assetflow.pedidos import CorpoDoPedido
from assetflow.pixel_knowledge import BaseDeConhecimento, ConhecimentoInvalido
from assetflow.pixel_knowledge.base import _ler_tema
from assetflow.pixel_knowledge.temas import regras_que_valem
from tests.conftest import BACKEND_ROOT, run

CONHECIMENTO = BACKEND_ROOT / "config" / "pixel_knowledge"
DOCUMENTO = (BACKEND_ROOT / "docs" / "PIXEL_KNOWLEDGE.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def base() -> BaseDeConhecimento:
    return BaseDeConhecimento.do_diretorio(CONHECIMENTO)


def test_as_quatro_secoes_viraram_temas_sem_problema(base):
    assert base.problemas == ()
    assert set(base.temas) == {"contorno", "suavizacao", "pontilhado", "manchas", "erros"}
    secoes = {t.secao for t in base.temas.values()}
    assert secoes == {"§4", "§7", "§8", "§17"}
    for tema in base.temas.values():
        assert f"## {tema.secao[1:]}. " in DOCUMENTO  # a seção existe no documento
        for regra in tema.regras:
            assert regra.secao == tema.secao and regra.verificacao


def test_regra_de_tema_com_numero_precisa_de_fonte_e_etiqueta_conferida():
    with pytest.raises(ConhecimentoInvalido, match="número sem fonte"):
        _ler_tema({"tema": "x", "titulo": "x", "secao": "§4", "regras": [
            {"texto": "até 15%", "classe": "style", "secao": "§4", "verificacao": "autora"}]}, "t", "x")
    with pytest.raises(ConhecimentoInvalido, match="liberdade"):
        _ler_tema({"tema": "x", "titulo": "x", "secao": "§4", "regras": [
            {"texto": "y", "classe": "style", "secao": "§4", "verificacao": "autora",
             "etiquetas": {"liberdade": ["solto"]}}]}, "t", "x")
    with pytest.raises(ConhecimentoInvalido, match="nome do arquivo"):
        _ler_tema({"tema": "outro", "titulo": "x", "secao": "§4", "regras": []}, "t", "x")


def _spec(servico, texto, perfil):
    return servico._resolver(texto, perfil)


def test_o_pedido_aciona_as_etiquetas(base, container):
    servico = ServicoDesenhista(container)
    pequeno = _spec(servico, "poção 16x16", "pixel_prop_64")
    grande = _spec(servico, "céu 64x64", "pixel_prop_64")
    pontilhado = base.temas["pontilhado"]
    pequenas = [r.texto for r in regras_que_valem(pontilhado, pequeno)]
    grandes = [r.texto for r in regras_que_valem(pontilhado, grande)]
    assert "personagem e objeto de até 32×32 não pontilham" in pequenas
    assert "personagem e objeto de até 32×32 não pontilham" not in grandes
    assert any("15% da área" in t for t in grandes)
    suave = base.temas["suavizacao"]
    assert [r.texto for r in regras_que_valem(suave, pequeno)] == [
        "em sprite pequeno de jogo, sem suavização: vira ruído"
    ]
    # Em ousado, as regras de gosto (liberdade fiel e equilibrado) saem.
    contorno = base.temas["contorno"]
    assert len(regras_que_valem(contorno, pequeno, "ousado")) < len(regras_que_valem(contorno, pequeno))


def test_consultar_base_filtra_pelo_pedido_e_recusa_tema_desconhecido(container):
    servico = ServicoDesenhista(container)
    texto = servico.consultar_base("pontilhado", pedido="poção 16x16", perfil="pixel_prop_64")
    assert texto.startswith("pontilhado (dithering) (PIXEL_KNOWLEDGE §7) — ")
    assert "não pontilham · o app mede (PONTILHADO)" in texto
    assert "15% da área" not in texto
    assert "15% da área" in servico.consultar_base("pontilhado")  # sem pedido, o tema inteiro
    with pytest.raises(ErroDoPedido, match="os temas são: contorno"):
        servico.consultar_base("anatomia")


def test_a_consulta_cita_os_temas_e_a_lista_os_poe_uma_vez(container):
    servico = ServicoDesenhista(container)
    consulta = servico.consultar("poção 16x16", "pixel_prop_64")
    assert consulta.splitlines()[-1].startswith("temas (consultar_base, regras que valem): contorno ")
    for texto in ("poção 16x16", "espada 32x32", "baú 32x32"):
        run(container.pedidos.criar(CorpoDoPedido(prompt=texto, profile="pixel_prop_64",
                                                  modo_conceito="sem_conceito")))
    lista = run(servico.pedidos_pendentes())
    assert lista.count("temas da base: ") == 1 and "temas (consultar_base" not in lista


def test_desligado_some_a_linha_e_a_ferramenta_recusa(container):
    container.settings.aprendizado.consultar_base = False
    servico = ServicoDesenhista(container)
    assert "temas (consultar_base" not in servico.consultar("poção 16x16", "pixel_prop_64")
    with pytest.raises(ErroDoPedido, match="ASSETFLOW_CONSULTAR_BASE"):
        servico.consultar_base("contorno")
