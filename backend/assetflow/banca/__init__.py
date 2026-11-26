"""A banca de teste (etapa K1 do plano da base de conhecimento).

Os seis pedidos de ``config/banca.yaml``, desenhados em rodadas ligadas a uma
versão da base, e a comparação cega na tela "Comparar". Rodadas e votos num
SQLite em ``data/banca/``. Não importa API, MCP, gaveta nem jobs (teste de
fronteiras). Detalhes: ``backend/docs/BANCA_E_CONCEITO.md``.
"""

from .caixa import (
    BancaIndisponivel,
    CaixaDaBanca,
    ErroDaBanca,
    Rodada,
    RodadaNaoEncontrada,
    Voto,
)
from .config import (
    Banca,
    BancaInvalida,
    ItemDaBanca,
    commit_do_git,
    impressao_da_base,
    ler_banca,
)
from .servico import ESCOLHAS, ServicoDaBanca, tokens_estimados

__all__ = [
    "ESCOLHAS",
    "Banca",
    "BancaIndisponivel",
    "BancaInvalida",
    "CaixaDaBanca",
    "ErroDaBanca",
    "ItemDaBanca",
    "Rodada",
    "RodadaNaoEncontrada",
    "ServicoDaBanca",
    "Voto",
    "commit_do_git",
    "impressao_da_base",
    "ler_banca",
    "tokens_estimados",
]
