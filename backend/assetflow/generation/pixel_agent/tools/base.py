"""O contrato de uma ferramenta de desenho (plano de motores §9.3).

Uma ferramenta recebe o canvas e parâmetros nomeados, pinta, e devolve quantos
pixels mudaram. Só isso. Ela não sabe o que está sendo desenhado, não decide
cor e não conhece o plano — quem decide é o :mod:`..planner`, quem executa é o
:mod:`..tool_executor`.

Essa separação é a razão de o engine inteiro ser depurável: como toda alteração
no canvas passa por uma chamada de ferramenta registrada, o histórico de tool
calls **é** a reconstrução exata do desenho. Um sprite que saiu errado tem um
log que diz em que passo ele saiu errado.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..canvas import RGBA, PixelCanvas

__all__ = ["PixelTool", "as_color", "as_int"]


@runtime_checkable
class PixelTool(Protocol):
    """Uma ferramenta de desenho registrável no executor."""

    #: Nome usado na tool call. É o vocabulário publicado no plano de motores §9.3.
    name: str

    def __call__(self, canvas: PixelCanvas, **params: Any) -> int:
        """Aplica a ferramenta e devolve quantos pixels mudaram."""
        ...


def as_color(value: Any) -> RGBA:
    """Normaliza cor vinda de um plano para ``(r, g, b, a)``.

    Aceita ``#rgb``, ``#rgba``, ``#rrggbb``, ``#rrggbbaa`` e tupla/lista de 3
    ou 4 componentes. Uma cor inválida vira erro claro em vez de um pixel
    preto silencioso: em pixel art, uma cor errada é um defeito visível, e
    descobri-lo na imagem custa muito mais do que descobri-lo aqui.

    A forma curta (``#fff``) existe porque é como se escreve cor à mão, e um
    plano de desenho é escrito à mão. Recusá-la transformaria um atalho
    universal em erro de digitação.
    """
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) in (3, 4):
            text = "".join(char * 2 for char in text)
        if len(text) == 6:
            text += "ff"
        if len(text) != 8:
            raise ValueError(f"cor hexadecimal inválida: {value!r}")
        try:
            return (
                int(text[0:2], 16),
                int(text[2:4], 16),
                int(text[4:6], 16),
                int(text[6:8], 16),
            )
        except ValueError as exc:
            raise ValueError(f"cor hexadecimal inválida: {value!r}") from exc

    if isinstance(value, (tuple, list)):
        components = [int(item) for item in value]
        if len(components) == 3:
            components.append(255)
        if len(components) != 4:
            raise ValueError(f"cor precisa de 3 ou 4 componentes: {value!r}")
        return tuple(max(0, min(255, item)) for item in components)  # type: ignore[return-value]

    raise ValueError(f"cor não reconhecida: {value!r}")


def as_int(value: Any, name: str) -> int:
    """Uma coordenada inteira — e **só** inteira (plano de correção §21).

    Um ``12.5`` é recusado em vez de virar ``12``. A regra parece severa para
    quem vem de canvas em ponto flutuante, e é o contrário: em uma grade de
    32×32, meio pixel não existe. Truncar em silêncio esconderia um erro de
    planejamento — o plano *achava* que estava desenhando entre duas colunas —
    e o defeito só apareceria na imagem, meia dúzia de etapas depois.

    ``12.0`` passa: é um inteiro escrito como float, o que acontece o tempo
    todo quando o plano vem de JSON. O que não passa é fração de pixel.
    """
    if isinstance(value, bool):
        # `bool` é `int` em Python, e "desenhe na coluna True" é sempre um bug.
        raise ValueError(f"parâmetro '{name}' precisa ser inteiro: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(
                f"parâmetro '{name}' não aceita coordenada fracionária: {value!r} "
                "— a grade não tem meio pixel"
            )
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            pass
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(
                f"parâmetro '{name}' precisa ser inteiro: {value!r}"
            ) from exc
        if not number.is_integer():
            raise ValueError(
                f"parâmetro '{name}' não aceita coordenada fracionária: {value!r} "
                "— a grade não tem meio pixel"
            )
        return int(number)
    raise ValueError(f"parâmetro '{name}' precisa ser inteiro: {value!r}")
