"""PaletteGuard — a paleta manda no Optimizer (plano Optimizer §16 e §67).

O Optimizer entra **depois** do ``PixelPostProcessor``, que já trouxe o sprite
para dentro do orçamento de cores. Uma correção que introduza uma cor nova
desfaz esse trabalho em silêncio: o asset volta a ter 17 cores em um contrato
de 16, e quem descobre é a validação final — tarde demais para saber qual
reparo fez isso.

A guarda fica no executor, então a regra vale **em cada ação**, não na
conferência do fim.

Dois modos, e a diferença importa
---------------------------------
``locked``
    A lista de cores é o contrato do projeto. Uma cor de fora é **recusada**:
    o reparo não acontece e o erro fica no log. Aproximar seria decidir por
    conta própria qual cor do projeto o artista quis.
``max_colors``
    O que importa é o número. Com espaço, a cor nova entra; com o orçamento
    cheio, ela é **resolvida** para a mais próxima em uso — a pincelada
    acontece, em um tom vizinho, e o sprite não fica com um buraco.
"""

from __future__ import annotations

from collections.abc import Sequence

from .canvas import RGBA

__all__ = ["PaletteGuard", "PaletteViolation", "as_rgba"]


class PaletteViolation(ValueError):
    """Um reparo tentou usar uma cor que a paleta travada não permite."""


class PaletteGuard:
    """Decide qual cor o Optimizer pode de fato usar."""

    def __init__(
        self,
        allowed: Sequence[str | RGBA] = (),
        *,
        max_colors: int | None = None,
        locked: bool = False,
    ) -> None:
        self._locked = locked
        self._max_colors = max_colors
        self._allowed: list[RGBA] = []
        for color in allowed:
            rgba = as_rgba(color)
            if rgba[3] != 0 and rgba not in self._allowed:
                self._allowed.append(rgba)

    @property
    def colors(self) -> tuple[RGBA, ...]:
        return tuple(self._allowed)

    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def is_full(self) -> bool:
        return self._max_colors is not None and len(self._allowed) >= self._max_colors

    # ------------------------------------------------------------------
    def resolve(self, color: str | RGBA | Sequence[int]) -> RGBA:
        """A cor que o reparo pode usar no lugar da pedida.

        Raises:
            PaletteViolation: só em paleta travada, e só para cor de fora.
        """
        rgba = as_rgba(color)

        # Apagar não gasta uma entrada da paleta: tratar o alpha 0 como cor
        # faria o orçamento ser consumido pela borracha.
        if rgba[3] == 0:
            return rgba

        if rgba in self._allowed:
            return rgba

        if self._locked:
            raise PaletteViolation(
                f"cor {_hex(rgba)} não pertence à paleta travada do projeto "
                f"({len(self._allowed)} cores); reparo recusado"
            )

        if not self.is_full:
            self._allowed.append(rgba)
            return rgba

        if not self._allowed:  # pragma: no cover - paleta de tamanho zero
            return rgba
        return _closest(rgba, self._allowed)

    def permits(self, color: str | RGBA) -> bool:
        """A cor passa sem alteração?"""
        try:
            return self.resolve(color) == as_rgba(color)
        except PaletteViolation:
            return False


def as_rgba(value: str | RGBA | Sequence[int]) -> RGBA:
    """Aceita ``#rgb``, ``#rrggbb``, ``#rrggbbaa`` e tuplas de 3 ou 4."""
    if isinstance(value, str):
        text = value.strip().lstrip("#")
        if len(text) in (3, 4):
            text = "".join(char * 2 for char in text)
        if len(text) == 6:
            text += "ff"
        if len(text) != 8:
            raise ValueError(f"cor hexadecimal inválida: {value!r}")
        return (
            int(text[0:2], 16),
            int(text[2:4], 16),
            int(text[4:6], 16),
            int(text[6:8], 16),
        )

    components = [int(item) for item in value]
    if len(components) == 3:
        components.append(255)
    if len(components) != 4:
        raise ValueError(f"cor precisa de 3 ou 4 componentes: {value!r}")
    return (
        max(0, min(255, components[0])),
        max(0, min(255, components[1])),
        max(0, min(255, components[2])),
        max(0, min(255, components[3])),
    )


def _hex(color: RGBA) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _closest(color: RGBA, candidates: Sequence[RGBA]) -> RGBA:
    """A mais próxima em distância euclidiana no RGB.

    RGB simples, e não um espaço perceptual: as paletas aqui têm no máximo
    algumas dezenas de cores bem separadas, e a diferença entre RGB e CIELAB
    nesse cenário não muda a escolha — muda só o custo.
    """
    return min(
        candidates,
        key=lambda item: sum(
            (int(item[index]) - int(color[index])) ** 2 for index in range(3)
        ),
    )
