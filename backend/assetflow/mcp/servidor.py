"""O servidor MCP: as ferramentas do desenhista, por stdio.

Casca fina sobre :class:`~.servico.ServicoDesenhista`. Só este módulo importa
o SDK do MCP (``mcp``, dependência opcional: ``pip install -e ".[mcp]"``).

As descrições das ferramentas são **curtas de propósito**: o Claude as carrega
em toda conversa, use ele o AssetFlow ou não. O formato da receita, que é o
texto longo, vem na resposta de ``consultar_pedido``, só quando há desenho.

stdout é o canal do protocolo: nada aqui escreve nele. Log vai para stderr.

Sem ``from __future__ import annotations`` de propósito: o SDK lê as anotações
das ferramentas para montar o schema, e a descrição de ``perfil`` é uma
variável local de :func:`criar_servidor` — como texto adiado, ela não seria
encontrada.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from .servico import PERFIL_PADRAO, ErroDoPedido, ServicoDesenhista

__all__ = ["NOME", "criar_servidor", "main"]

#: Nome do servidor no Claude Code (``claude mcp add ... assetflow ...``).
NOME = "assetflow"


def criar_servidor(
    servico: ServicoDesenhista,
    *,
    ao_encerrar: Callable[[], Awaitable[None]] | None = None,
) -> MCPServer:
    """Monta o servidor com as ferramentas ligadas a ``servico``."""

    @asynccontextmanager
    async def ciclo(_servidor: MCPServer) -> AsyncIterator[None]:
        try:
            yield None
        finally:
            if ao_encerrar is not None:
                await ao_encerrar()

    servidor = MCPServer(NOME, log_level="WARNING", lifespan=ciclo)

    # A lista sai do profiles.yaml no boot: um profile novo aparece aqui sem
    # editar este arquivo.
    perfil_desc = (
        "Profile de partida; só vale no que o texto não disser. "
        f"Opções: {', '.join(servico.perfis())}. Padrão: {PERFIL_PADRAO}."
    )
    liberdade_consulta = (
        "Fiel (padrão, como hoje), equilibrado ou ousado: muda só a orientação do "
        "recorte; grade, cores e fundo não mudam."
    )
    liberdade_referencia = (
        "Fiel (padrão, como hoje), equilibrado ou ousado; em ousado, a imagem é "
        "escolhida pelo estilo, sem o filtro de porte."
    )

    @servidor.tool(structured_output=False)
    def consultar_pedido(
        pedido: Annotated[str, Field(description="O pedido em texto livre.")],
        perfil: Annotated[str | None, Field(description=perfil_desc)] = None,
        molde: Annotated[
            bool, Field(description="true inclui a receita do molde-base; sem ele, só as medidas.")
        ] = False,
        liberdade: Annotated[str | None, Field(description=liberdade_consulta)] = None,
    ) -> str:
        """Resolve um pedido de pixel art em texto livre (ex.: "cavaleiro 32x32, 8 cores, sem fundo") e devolve o que o AssetFlow entendeu, o formato da receita e as medidas, a paleta e a luz da base. Chame antes de desenhar."""
        try:
            return servico.consultar(pedido, perfil, molde, liberdade)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    async def pedidos_pendentes(
        limite: Annotated[
            int,
            Field(description="Quantos pedidos trazer, dos mais antigos (padrão 5, máximo 10)."),
        ] = 5,
    ) -> str:
        """Lista os pedidos feitos na tela do AssetFlow que esperam desenho, cada um já com o que consultar_pedido devolveria, e os reserva para você. Desenhe cada um com desenhar(pedido_id=...)."""
        try:
            return await servico.pedidos_pendentes(limite)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    async def desenhar(
        pedido: Annotated[
            str | None,
            Field(description="O mesmo texto de consultar_pedido. Com base, pode omitir."),
        ] = None,
        receita: Annotated[
            dict[str, Any] | None,
            Field(description="A receita completa; com base, só paleta e camadas alteradas."),
        ] = None,
        base: Annotated[
            str | None, Field(description="Id de um asset anterior, para remendo.")
        ] = None,
        perfil: Annotated[
            str | None,
            Field(description="Igual a consultar_pedido; num remendo, o da base."),
        ] = None,
        pedido_id: Annotated[
            str | None,
            Field(
                description=(
                    "Id de um pedido de pedidos_pendentes. Texto, perfil e controles vêm "
                    "dele: omita pedido e perfil. Aprovado, o pedido fica concluído e "
                    "aparece na tela."
                )
            ),
        ] = None,
    ) -> str:
        """Desenha um sprite a partir de uma receita e devolve o laudo: aprovação, nota, problemas, id do asset e caminho do PNG. Para corrigir, passe base=<id> e só o que mudou. Com pedido_id, atende um pedido da fila da tela."""
        try:
            return await servico.desenhar(
                pedido=pedido, receita=receita, base=base, perfil=perfil, pedido_id=pedido_id
            )
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    def ver_referencia(
        pedido: Annotated[str, Field(description="O mesmo texto de consultar_pedido.")],
        perfil: Annotated[str | None, Field(description="Igual a consultar_pedido.")] = None,
        liberdade: Annotated[str | None, Field(description=liberdade_referencia)] = None,
    ) -> list:
        """Mostra UMA imagem de referência dos pacotes livres ativos, do tipo de asset do pedido, ampliada. Serve para ver estilo, não para copiar; use só quando precisar ver."""
        try:
            png, legenda = servico.ver_referencia(pedido, perfil, liberdade)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc
        return [legenda, Image(data=png, format="png")]

    @servidor.tool(structured_output=False)
    async def ver_asset(
        id: Annotated[str, Field(description="Id do asset.")],
    ) -> list:
        """Mostra o PNG de um asset, ampliado, para revisão visual. Custa mais contexto que o laudo: use só quando precisar ver."""
        try:
            png, legenda = await servico.ver(id)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc
        return [legenda, Image(data=png, format="png")]

    return servidor


def main() -> None:
    """``python -m assetflow.mcp``: monta o AssetFlow e serve por stdio."""
    from ..bootstrap import build_container
    from ..settings import load_settings

    settings = load_settings()
    # O servidor roda o worker ele mesmo, um job por chamada (ver
    # ServicoDesenhista._executar): um worker em segundo plano disputaria a
    # fila com ele.
    settings.worker.embedded = False
    container = build_container(settings)
    servidor = criar_servidor(ServicoDesenhista(container), ao_encerrar=container.shutdown)
    servidor.run()
