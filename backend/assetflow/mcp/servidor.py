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
        formato: Annotated[
            bool,
            Field(description="true repete o formato inteiro dos comandos opcionais da receita."),
        ] = False,
    ) -> str:
        """Resolve um pedido de pixel art em texto livre (ex.: "cavaleiro 32x32, 8 cores, sem fundo") e devolve o que o AssetFlow entendeu, o formato da receita e as medidas, a paleta e a luz da base. Chame antes de desenhar."""
        try:
            return servico.consultar(pedido, perfil, molde, liberdade, formato)
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
                    "dele: omita pedido e perfil. Aprovado no validador, ele espera o seu "
                    "olhar e concluir_pedido."
                )
            ),
        ] = None,
    ) -> list:
        """Desenha um sprite a partir de uma receita e devolve o laudo e a imagem para o seu olhar. Para corrigir, passe base=<id> e só o que mudou. Com pedido_id, atende um pedido da fila: aprovado, ele espera o olhar e concluir_pedido."""
        try:
            laudo = await servico.desenhar(
                pedido=pedido, receita=receita, base=base, perfil=perfil, pedido_id=pedido_id
            )
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc
        if laudo.imagem is None:
            return [str(laudo)]
        return [str(laudo), Image(data=laudo.imagem, format="png")]

    @servidor.tool(structured_output=False)
    async def propor_conceitos(
        pedido_id: Annotated[str, Field(description="Id de um pedido de pedidos_pendentes.")],
        conceitos: Annotated[
            list[dict[str, str]],
            Field(
                description=(
                    "Três conceitos, cada um com traco, silhueta, objeto, pose e simplificar "
                    "(até 120 caracteres; simplificar, 80)."
                )
            ),
        ],
        escolhido: Annotated[
            int | None, Field(description="Se você escolhe: o mais forte, de 1 a 3.")
        ] = None,
        motivo: Annotated[
            str | None, Field(description="Se você escolhe: por que ele é o mais forte.")
        ] = None,
    ) -> str:
        """Propõe 3 conceitos para um pedido da fila antes do desenho: traço marcante, silhueta, objeto, pose e o que simplificar, diferentes entre si e próprios deste personagem. Se você escolhe, passe escolhido e motivo e desenhe em seguida."""
        try:
            return await servico.propor_conceitos(pedido_id, conceitos, escolhido, motivo)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    async def concluir_pedido(
        pedido_id: Annotated[str, Field(description="Id do pedido que você olhou.")],
        olhar: Annotated[
            str, Field(description="A linha do que você viu no desenho (até 240 caracteres).")
        ],
        asset_id: Annotated[
            str | None,
            Field(description="Um desenho aprovado anterior do mesmo pedido, se estava melhor."),
        ] = None,
        respostas: Annotated[
            dict[str, str] | None,
            Field(description='Uma por pergunta do olhar: {"silhueta": "sim", "valores": "não: onde"}.'),
        ] = None,
    ) -> str:
        """Conclui um pedido depois do seu olhar: passe a linha do que viu. Sem asset_id, vale o último desenho aprovado do pedido; com ele, um anterior do mesmo pedido."""
        try:
            return await servico.concluir(pedido_id, olhar, asset_id, respostas)
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    async def registrar_licao(
        asset_id: Annotated[
            str, Field(description="O asset olhado; tipo, corpo e porte vêm dele.")
        ],
        tema: Annotated[
            str,
            Field(
                description=(
                    "silhueta, proporcao, pose, rosto ou equipamento (forma); valor, luz, "
                    "cor, contorno ou limpeza (técnica)."
                )
            ),
        ],
        errou: Annotated[str, Field(description="O que ficou feio ou estranho (até 120).")],
        porque: Annotated[str, Field(description="Por que aconteceu (até 120).")],
        regra: Annotated[str, Field(description="A regra para não repetir (até 140).")],
        geral: Annotated[
            bool, Field(description="true quando a regra vale para qualquer tipo, corpo e porte.")
        ] = False,
        mesma_que: Annotated[
            str | None, Field(description="Id de uma lição do recorte que esta repete (L3).")
        ] = None,
        da_autora: Annotated[
            bool,
            Field(description="true ao converter uma opinião da autora sobre este asset."),
        ] = False,
    ) -> str:
        """Registra a lição de um olhar que achou algo feio ou estranho: o que errou, por quê e a regra para não repetir. Lição igual a uma já registrada só soma no contador. As lições voltam no recorte dos próximos pedidos parecidos."""
        try:
            return await servico.registrar_licao(
                asset_id, tema, errou, porque, regra, geral, mesma_que, da_autora
            )
        except ErroDoPedido as exc:
            raise ToolError(str(exc)) from exc

    @servidor.tool(structured_output=False)
    def consultar_base(
        tema: Annotated[str, Field(description="O tema: contorno, suavizacao, pontilhado, manchas ou erros.")],
        pedido: Annotated[
            str | None, Field(description="O texto do pedido, para trazer só as regras que valem para ele.")
        ] = None,
        perfil: Annotated[str | None, Field(description="Igual a consultar_pedido.")] = None,
        liberdade: Annotated[str | None, Field(description="fiel, equilibrado ou ousado.")] = None,
    ) -> str:
        """Devolve as regras de um tema da base de pixel art (contorno, suavização, pontilhado, manchas, erros comuns), com a seção de origem e como cada uma é conferida. Use quando tiver dúvida num tema; o recorte do pedido só cita os temas."""
        try:
            return servico.consultar_base(tema, pedido, perfil, liberdade)
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
        """Mostra um asset como o olhar o vê: ampliado, silhueta em preto e tamanho real (cerca de 300 tokens). Use para olhar de novo um desenho, como um pedido que voltou à fila sem o olhar."""
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
    # Lote 11: em que commit este servidor subiu; a tela avisa quando o código
    # mudar e for preciso reconectar pelo /mcp.
    from ..servidores import registrar, remover_registro

    try:
        registrar(settings, "mcp")
    except OSError:
        pass  # sem data/ gravável, só não há aviso
    try:
        servidor.run()
    finally:
        remover_registro(settings, "mcp")
