"""ExplicitConstraintExtractor — o que a pessoa escreveu de verdade (§26/§27).

Quando alguém digita ``tree 32x32, 8 colors, transparent background``, três
das quatro informações do pedido são **restrições exatas**, não estilo. Elas
não podem depender de interpretação: 32×32 é 32×32.

Por isso a extração acontece **antes** de qualquer classificação ou leitura
semântica (plano T→J §26). São duas consequências, e as duas importam:

1. o número vira contrato imediatamente, com origem ``explicit_prompt``, e
   nenhuma camada posterior pode sobrescrevê-lo;
2. o texto que segue para o classificador já está **limpo** — sem "32x32",
   sem "8 colors", sem "transparent background". Sem essa limpeza, a palavra
   *background* de "transparent background" faria uma árvore virar cenário.

O que sobra do texto é o ``subject``: o que a pessoa quer desenhado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

__all__ = ["ExplicitConstraintExtractor", "ExplicitConstraints"]


#: ``32x32``, ``32 × 32``, ``64x32``. O ``×`` tipográfico entra junto porque
#: é o que aparece quando o valor é copiado da própria interface.
_SIZE = re.compile(r"\b(\d{1,4})\s*[x×]\s*(\d{1,4})\b", re.IGNORECASE)

#: ``8 colors``, ``16 cores``, ``16-color``, ``paleta de 12 cores``.
_COLORS = re.compile(
    r"\b(?:paleta\s+(?:de\s+)?)?(\d{1,3})\s*[-\s]?\s*(?:colors?|colours?|cores|cor)\b",
    re.IGNORECASE,
)

#: Fundo transparente. Note que *background* sozinho NÃO casa: em "forest
#: background" a palavra é o tipo do asset, não uma restrição de fundo.
_TRANSPARENT = re.compile(
    r"\b(?:transparent\s+background|background\s+transparent|no\s+background|"
    r"without\s+background|transparent\s+bg|alpha\s+background|"
    r"fundo\s+transparente|sem\s+fundo|sem\s+plano\s+de\s+fundo)\b",
    re.IGNORECASE,
)

#: Fundo sólido/opaco pedido explicitamente.
_SOLID = re.compile(
    r"\b(?:solid\s+background|opaque\s+background|with\s+background|"
    r"fundo\s+solido|fundo\s+sólido|fundo\s+opaco|com\s+fundo)\b",
    re.IGNORECASE,
)

#: Vista. Só o que é inequívoco: "de lado" pode ser parte da frase ("um baú
#: de lado do trono"), então só casa com o qualificador junto — "visto de
#: lado". Restrição explícita que erra é pior do que restrição ausente,
#: porque ela ganha das camadas de baixo.
_VIEWS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "top_down",
        re.compile(r"\b(?:top[-\s]?down|de\s+cima|vista\s+superior)\b", re.IGNORECASE),
    ),
    (
        "isometric",
        re.compile(
            r"\b(?:isometric|isometrica|isométrica|isometrico|isométrico)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "three_quarter",
        re.compile(
            r"\b(?:three[-\s]quarter|3/4|tres\s+quartos|três\s+quartos)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "side",
        re.compile(
            r"\b(?:side\s+view|vista\s+lateral|visto\s+de\s+lado)\b", re.IGNORECASE
        ),
    ),
    (
        "front",
        re.compile(
            r"\b(?:front\s+view|vista\s+frontal|visto\s+de\s+frente)\b", re.IGNORECASE
        ),
    ),
    (
        "back",
        re.compile(
            r"\b(?:back\s+view|vista\s+traseira|visto\s+de\s+costas)\b", re.IGNORECASE
        ),
    ),
)


@dataclass(slots=True)
class ExplicitConstraints:
    """As restrições que estavam escritas, e o sujeito que sobrou."""

    subject: str = ""
    logical_width: int | None = None
    logical_height: int | None = None
    max_colors: int | None = None
    background: Literal["transparent", "solid"] | None = None
    view: str | None = None
    #: Os trechos consumidos do texto, na ordem em que apareceram. Servem ao
    #: trace: explicam por que o sujeito ficou menor que a frase original.
    matched: tuple[str, ...] = field(default=())

    @property
    def has_logical_size(self) -> bool:
        return self.logical_width is not None and self.logical_height is not None


class ExplicitConstraintExtractor:
    """Lê restrições exatas do texto livre, sem inventar nenhuma."""

    def extract(self, prompt: str) -> ExplicitConstraints:
        text = prompt or ""
        matched: list[str] = []

        def consume(pattern: re.Pattern[str], *, first_only: bool = True) -> re.Match[str] | None:
            nonlocal text
            match = pattern.search(text)
            if match is None:
                return None
            matched.append(match.group(0).strip())
            text = text[: match.start()] + " " + text[match.end() :]
            if not first_only:  # pragma: no cover - reservado a padrões futuros
                while (extra := pattern.search(text)) is not None:
                    text = text[: extra.start()] + " " + text[extra.end() :]
            return match

        constraints = ExplicitConstraints()

        # Fundo antes de tudo: é o único padrão que consome a palavra
        # "background", e o classificador depende dela ter sumido quando ela
        # fazia parte de "transparent background".
        if consume(_TRANSPARENT) is not None:
            constraints.background = "transparent"
        elif consume(_SOLID) is not None:
            constraints.background = "solid"

        if (size := consume(_SIZE)) is not None:
            constraints.logical_width = int(size.group(1))
            constraints.logical_height = int(size.group(2))

        if (colors := consume(_COLORS)) is not None:
            constraints.max_colors = int(colors.group(1))

        for name, pattern in _VIEWS:
            if consume(pattern) is not None:
                constraints.view = name
                break

        constraints.subject = _cleanup(text)
        constraints.matched = tuple(matched)
        return constraints


def _cleanup(text: str) -> str:
    """Remove a pontuação órfã deixada pelos trechos consumidos.

    ``"tree 32x32, 8 colors"`` menos as restrições vira ``"tree ,  ,"``; o
    sujeito precisa ser ``"tree"``. Não é cosmético: o sujeito vai inteiro
    para o prompt do motor.
    """
    collapsed = " ".join(text.split())
    collapsed = re.sub(r"\s*([,;])\s*", r"\1 ", collapsed)
    collapsed = re.sub(r"(?:[,;]\s*)+", ", ", collapsed)
    return collapsed.strip(" ,;-–—").strip()
