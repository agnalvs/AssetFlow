"""O servidor MCP pelo protocolo, com o cliente do próprio SDK.

Pulado quando o SDK do MCP não está instalado — ele é opcional
(``pip install -e ".[mcp]"``). O que as ferramentas fazem está coberto em
``test_mcp.py``; aqui se cobra o que o Claude vê: nomes, descrições curtas,
o schema dos parâmetros, texto, imagem e erro.
"""

from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("mcp")

from mcp import Client, StdioServerParameters

from assetflow.bootstrap import AppContainer
from assetflow.mcp.servico import MOTOR, ServicoDesenhista
from assetflow.mcp.servidor import NOME, criar_servidor
from tests.conftest import BACKEND_ROOT, run

POCAO = BACKEND_ROOT / "assetflow" / "generation" / "engines" / "desenhista" / "exemplos" / "pocao_16x16.json"

#: Teto da descrição de uma ferramenta. Elas ocupam contexto em toda conversa
#: do Claude, use ele o AssetFlow ou não; crescer além disto é decisão, não
#: deriva.
TETO_DA_DESCRICAO = 260


@pytest.fixture
def servidor(container: AppContainer):
    container.registry.enable(MOTOR)
    return criar_servidor(ServicoDesenhista(container))


def _chamar(servidor, ferramenta: str, argumentos: dict):
    async def cenario():
        async with Client(servidor) as cliente:
            return await cliente.call_tool(ferramenta, argumentos)

    return run(cenario())


def test_tres_ferramentas_com_descricao_curta(servidor):
    async def cenario():
        async with Client(servidor) as cliente:
            return (await cliente.list_tools()).tools

    ferramentas = {f.name: f for f in run(cenario())}
    assert set(ferramentas) == {"consultar_pedido", "desenhar", "ver_asset"}
    for ferramenta in ferramentas.values():
        assert ferramenta.description
        assert len(ferramenta.description) <= TETO_DA_DESCRICAO, ferramenta.name

    perfil = ferramentas["consultar_pedido"].input_schema["properties"]["perfil"]
    # A lista vem do profiles.yaml, não de texto fixo.
    assert "pixel_character_32" in perfil["description"]
    assert "pixel_prop_64" in perfil["description"]
    assert "studio_character" not in perfil["description"]

    desenhar = ferramentas["desenhar"].input_schema
    assert set(desenhar["properties"]) == {"pedido", "receita", "base", "perfil"}
    assert desenhar.get("required", []) == []


def test_consultar_devolve_texto(servidor):
    resultado = _chamar(servidor, "consultar_pedido", {"pedido": "cavaleiro 32x32, 8 cores"})
    assert not resultado.is_error
    assert resultado.structured_content is None, "só texto: JSON a mais é contexto a mais"
    assert "grade: 32×32 (do texto)" in resultado.content[0].text


def test_desenhar_devolve_o_laudo(servidor):
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    resultado = _chamar(servidor, "desenhar", {"pedido": "poção vermelha 16x16", "receita": receita})
    assert not resultado.is_error
    assert resultado.content[0].text.startswith("APROVADO · asset_")


def test_erro_chega_ao_claude_em_portugues(servidor):
    resultado = _chamar(servidor, "desenhar", {"pedido": "poção 16x16"})
    assert resultado.is_error
    assert "falta 'receita'" in resultado.content[0].text


def test_ver_asset_devolve_legenda_e_imagem(servidor):
    receita = json.loads(POCAO.read_text(encoding="utf-8"))
    laudo = _chamar(servidor, "desenhar", {"pedido": "poção vermelha 16x16", "receita": receita})
    asset = laudo.content[0].text.splitlines()[0].split(" · ")[1]

    resultado = _chamar(servidor, "ver_asset", {"id": asset})
    assert not resultado.is_error
    texto, imagem = resultado.content
    assert texto.text.startswith(asset)
    assert imagem.type == "image"
    assert imagem.mime_type == "image/png"


def test_o_servidor_sobe_por_stdio():
    """O caminho do Claude Code: ``python -m assetflow.mcp``, falando por stdio.

    Sobe o processo de verdade e só lista as ferramentas — nada é gerado,
    então o ``backend/data`` do projeto não é tocado.
    """
    parametros = StdioServerParameters(
        command=sys.executable, args=["-m", "assetflow.mcp"], cwd=str(BACKEND_ROOT)
    )

    async def cenario():
        async with Client(parametros) as cliente:
            return [f.name for f in (await cliente.list_tools()).tools]

    assert sorted(run(cenario())) == ["consultar_pedido", "desenhar", "ver_asset"]
    assert NOME == "assetflow"
