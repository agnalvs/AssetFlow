"""A lista de verificação do olhar (Fase B2): nenhuma pergunta é inventada.

Cada pergunta de ``config/pixel_knowledge/olhar.yaml`` cita a seção do
``PIXEL_KNOWLEDGE.md`` de onde sai e, quando há, o trecho de uma regra de outro
YAML. Este teste confere as duas citações contra os arquivos de verdade.
"""

from __future__ import annotations

import re

import pytest
import yaml

from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import ServicoDesenhista
from assetflow.pixel_knowledge import (
    BaseDeConhecimento,
    lembrete_da_lista,
    lista_de_verificacao,
)
from tests.conftest import BACKEND_ROOT

CONHECIMENTO = BACKEND_ROOT / "config" / "pixel_knowledge"
DOCUMENTO = BACKEND_ROOT / "docs" / "PIXEL_KNOWLEDGE.md"


@pytest.fixture(scope="module")
def base() -> BaseDeConhecimento:
    carregada = BaseDeConhecimento.do_diretorio(CONHECIMENTO)
    assert carregada.problemas == ()
    return carregada


def _perguntas(base: BaseDeConhecimento):
    for forma, perguntas in base.olhar.listas.items():
        for pergunta in perguntas:
            yield forma, pergunta


def test_cada_lista_tem_de_4_a_6_perguntas(base):
    assert set(base.olhar.listas) == {"humanoid", "prop", "character"}
    assert all(4 <= len(lista) <= 6 for lista in base.olhar.listas.values())


def test_cada_secao_citada_existe_no_documento(base):
    secoes = set(re.findall(r"^## (\d+)\. ", DOCUMENTO.read_text(encoding="utf-8"), re.MULTILINE))
    for forma, pergunta in _perguntas(base):
        assert pergunta.secao.lstrip("§") in secoes, f"{forma}/{pergunta.nome}: {pergunta.secao}"


def test_cada_regra_citada_existe_no_yaml(base):
    for forma, pergunta in _perguntas(base):
        origem = pergunta.origem()
        if origem is None:
            continue
        arquivo, forma_citada, trecho = origem
        dados = yaml.safe_load((CONHECIMENTO / arquivo).read_text(encoding="utf-8"))
        regras = (
            dados["formas"][forma_citada]["regras"] if forma_citada else dados["regras"]
        )
        textos = [regra["texto"] for regra in regras]
        assert any(trecho in texto for texto in textos), f"{forma}/{pergunta.nome}: {pergunta.de}"


def _spec(container: AppContainer, texto: str, perfil: str):
    return ServicoDesenhista(container)._resolver(texto, perfil)


def test_lista_do_personagem_e_do_objeto(container: AppContainer, base):
    personagem = lista_de_verificacao(
        _spec(container, "maga do gelo 48x48, 12 cores", "pixel_character_48"),
        base.olhar,
        ampliacao=8,
        luz_padrao=base.luz.padrao,
    )
    assert personagem.splitlines()[0].startswith("olhar — na imagem: à esquerda ampliada 8×")
    assert "3. luz: vem de cima e da esquerda em todas as partes" in personagem
    assert personagem.splitlines()[-1].startswith("6. assimetria:")
    assert len(personagem) < 800

    objeto = lista_de_verificacao(
        _spec(container, "poção azul 16x16", "pixel_prop_64"), base.olhar, ampliacao=24, luz_padrao=base.luz.padrao
    )
    assert "à esquerda ampliada 24×" in objeto and "2. uma ideia:" in objeto
    assert len(objeto.splitlines()) == 6 and len(objeto) < 600


def test_corpo_sem_lista_propria_usa_a_geral_e_tile_nao_tem_lista(container: AppContainer, base):
    lobo = lista_de_verificacao(
        _spec(container, "lobo cinzento 32x32", "pixel_character_32"), base.olhar, ampliacao=12, luz_padrao=None
    )
    assert "dá para reconhecer a criatura" in lobo and len(lobo.splitlines()) == 5

    tile = lista_de_verificacao(
        _spec(container, "tileset de grama 16x16", "pixel_prop_64"), base.olhar, ampliacao=24, luz_padrao=None
    )
    assert "A base não tem lista de verificação para tile" in tile


def test_o_lembrete_dos_remendos_e_uma_linha(container: AppContainer, base):
    spec = _spec(container, "maga do gelo 48x48", "pixel_character_48")
    assert lembrete_da_lista(spec, base.olhar) == (
        "olhar — confira de novo a lista do primeiro olhar (silhueta, valores, luz, rosto, "
        "limpeza, assimetria)."
    )
