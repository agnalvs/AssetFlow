"""Quanto a conversa com o Claude custa, estimado (lotes 1 e 12).

O servidor MCP soma o que passa pela conversa — caracteres que ele manda,
caracteres que o Claude escreve (texto e receita) e imagens —, e cada soma vira
um evento datado na tabela ``custos`` da fila. Daí saem o custo de cada pedido,
o de cada dia e o aviso do limite diário.

A conta é uma **estimativa**: ~3 caracteres por token em texto, ~2,3 na receita
(as linhas de pixels são densas) e 294 tokens por imagem do olhar
(⌈588/28⌉ × ⌈384/28⌉, a regra de imagem). O raciocínio do Claude não passa pelo
servidor e não entra — é a dúvida registrada no lote 1.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any

__all__ = ["TOKENS_POR_IMAGEM", "por_dia", "tokens_do_dia", "tokens_estimados", "tokens_hoje"]

TOKENS_POR_IMAGEM = 294


def tokens_estimados(custo: Mapping[str, Any] | None) -> int:
    """Tokens a partir dos caracteres: ~3 por token em texto, ~2,3 em pixels, 294 por imagem."""
    if not custo:
        return 0
    return round(
        (custo.get("entrada", 0) + custo.get("saida_texto", 0)) / 3
        + custo.get("saida_receita", 0) / 2.3
        + TOKENS_POR_IMAGEM * custo.get("imagens", 0)
    )


def _dia_local(em: str) -> date:
    momento = datetime.fromisoformat(em)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone().date()


def por_dia(eventos: Iterable[Mapping[str, Any]], dias: int, hoje: date | None = None) -> list[dict[str, Any]]:
    """Tokens e consultas por dia local, do mais novo ao mais velho, ``dias`` dias."""
    hoje = hoje or datetime.now(UTC).astimezone().date()
    soma: dict[date, int] = defaultdict(int)
    vezes: dict[date, int] = defaultdict(int)
    for evento in eventos:
        dia = _dia_local(evento["em"])
        soma[dia] += tokens_estimados(evento)
        vezes[dia] += 1
    return [
        {"data": (hoje - timedelta(days=i)).isoformat(),
         "tokens": soma.get(hoje - timedelta(days=i), 0),
         "consultas": vezes.get(hoje - timedelta(days=i), 0)}
        for i in range(max(1, dias))
    ]


def tokens_do_dia(eventos: Iterable[Mapping[str, Any]], hoje: date | None = None) -> int:
    return por_dia(eventos, 1, hoje)[0]["tokens"]


def inicio_do_dia(dias_atras: int = 0) -> datetime:
    """A meia-noite local de ``dias_atras`` dias atrás, em UTC."""
    local = datetime.now(UTC).astimezone()
    meia_noite = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=dias_atras)
    return meia_noite.astimezone(UTC)


def tokens_hoje(fila: Any) -> int:
    """Os tokens estimados de hoje (dia local), lidos da fila."""
    return tokens_do_dia(fila.custos_desde(inicio_do_dia()))
