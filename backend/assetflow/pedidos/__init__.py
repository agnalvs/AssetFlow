"""A fila de pedidos da tela (Fase B do plano do app).

A tela cria pedidos; o Claude, pela conversa, os pega com ``pedidos_pendentes``
e os desenha com ``desenhar(pedido_id=...)``; a tela vê o resultado. A fila
mora num SQLite em ``data/pedidos/``, porque a API e o servidor MCP são dois
processos.

- :mod:`.modelo` — o pedido, as situações e as etapas que a tela mostra;
- :mod:`.fila` — o SQLite: uma transição, uma instrução condicional;
- :mod:`.servico` — montar, pré-visualizar e criar, com o spec resolvido uma vez.

Este pacote não importa a API, o MCP nem gaveta nenhuma: os dois o usam.
"""

from .fila import (
    ErroDaFila,
    FilaCorrompida,
    FilaDePedidos,
    FilaIndisponivel,
    PedidoNaoEncontrado,
    TransicaoRecusada,
    agora_utc,
    nova_leva,
)
from .modelo import Etapa, Evento, Liberdade, Pedido, Situacao, Tipo
from .servico import CorpoDoPedido, ServicoDePedidos

__all__ = [
    "CorpoDoPedido",
    "ErroDaFila",
    "Etapa",
    "Evento",
    "FilaCorrompida",
    "FilaDePedidos",
    "FilaIndisponivel",
    "Liberdade",
    "Pedido",
    "PedidoNaoEncontrado",
    "ServicoDePedidos",
    "Situacao",
    "Tipo",
    "TransicaoRecusada",
    "agora_utc",
    "nova_leva",
]
