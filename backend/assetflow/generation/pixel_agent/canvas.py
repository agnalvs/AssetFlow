"""PixelCanvas — a superfície onde o agente desenha (plano de correção §20).

A diferença entre o agente e um modelo de difusão está inteira nesta classe:
aqui não existe uma imagem grande que depois encolhe. Existe uma grade de
32×32 posições, e cada uma é preenchida por uma decisão. O plano de correção
§20 chama isso de canvas *pixel-native*: se a resolução lógica é 32×32, o
canvas é 32×32, e cada coordenada corresponde a exatamente um pixel lógico.

Consequências práticas de trabalhar na grade:

* **não há anti-aliasing para remover** — nenhuma cor intermediária chega a
  existir;
* **o alpha já é binário** — um pixel foi pintado ou não foi;
* **a paleta é conhecida** — ela é a lista de cores que o agente usou, não uma
  estimativa feita depois de quantizar.

O canvas não conhece motor, job nem AssetFlow. Ele sabe guardar pixels,
responder o que tem neles e virar uma imagem no fim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

__all__ = ["RGBA", "TRANSPARENT", "PixelCanvas", "CanvasStats"]

#: Uma cor como o canvas a guarda: quatro inteiros de 0 a 255.
RGBA = tuple[int, int, int, int]

TRANSPARENT: RGBA = (0, 0, 0, 0)


@dataclass(frozen=True, slots=True)
class CanvasStats:
    """O que o revisor precisa saber sobre o desenho (plano de correção §23)."""

    width: int
    height: int
    opaque_pixels: int
    color_count: int
    #: Fração do canvas ocupada por pixel opaco. É a medida que separa "sprite
    #: vazio" de "mancha que cobre tudo".
    occupancy: float
    #: Caixa do conteúdo — ``None`` quando o canvas está vazio.
    bounds: tuple[int, int, int, int] | None
    #: Pixels opacos sem nenhum vizinho opaco (os 4 lados). Um punhado deles é
    #: ruído visual; em pixel art eles saltam à vista.
    orphan_pixels: int


@dataclass(slots=True)
class PixelCanvas:
    """Grade RGBA de tamanho fixo, endereçada por ``(x, y)``.

    A origem é o canto superior esquerdo, como em toda imagem — e como nas
    ferramentas de desenho que o agente usa.
    """

    width: int
    height: int
    _pixels: list[RGBA] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError(
                f"canvas degenerado: {self.width}×{self.height} — "
                "largura e altura precisam ser maiores que zero"
            )
        if not self._pixels:
            self._pixels = [TRANSPARENT] * (self.width * self.height)

    # ------------------------------------------------------------------
    # Acesso
    # ------------------------------------------------------------------
    def contains(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get(self, x: int, y: int) -> RGBA:
        """A cor em ``(x, y)``; transparente fora do canvas.

        Fora do canvas devolve transparente em vez de estourar de propósito:
        as ferramentas desenham formas que passam da borda o tempo todo, e
        obrigar cada uma a checar limites espalharia a mesma condição por
        todos os arquivos de ``tools/``.
        """
        if not self.contains(x, y):
            return TRANSPARENT
        return self._pixels[y * self.width + x]

    def set(self, x: int, y: int, color: RGBA) -> bool:
        """Pinta ``(x, y)``. Devolve ``True`` se algo mudou de fato.

        O retorno é o que alimenta a contagem de pixels alterados no log de
        tool calls: uma chamada que não muda nada é informação útil quando se
        está depurando um plano de desenho.
        """
        if not self.contains(x, y):
            return False
        index = y * self.width + x
        if self._pixels[index] == color:
            return False
        self._pixels[index] = color
        return True

    def is_opaque(self, x: int, y: int) -> bool:
        return self.get(x, y)[3] > 0

    def __iter__(self) -> Iterator[tuple[int, int, RGBA]]:
        for y in range(self.height):
            for x in range(self.width):
                yield x, y, self._pixels[y * self.width + x]

    # ------------------------------------------------------------------
    # Leitura agregada (o `inspect_canvas` do plano de correção §16)
    # ------------------------------------------------------------------
    def colors(self) -> dict[RGBA, int]:
        """Cores opacas usadas e quantas vezes, da mais frequente para a menos.

        Pixels transparentes ficam de fora: um pixel invisível não é uma cor
        do sprite e não pode gastar uma entrada da paleta.
        """
        counts: dict[RGBA, int] = {}
        for color in self._pixels:
            if color[3] == 0:
                continue
            counts[color] = counts.get(color, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))

    def bounds(self) -> tuple[int, int, int, int] | None:
        """Caixa do conteúdo opaco, ``(x0, y0, x1, y1)`` com fim inclusivo."""
        min_x = min_y = None
        max_x = max_y = None
        for x, y, color in self:
            if color[3] == 0:
                continue
            min_x = x if min_x is None else min(min_x, x)
            min_y = y if min_y is None else min(min_y, y)
            max_x = x if max_x is None else max(max_x, x)
            max_y = y if max_y is None else max(max_y, y)
        if min_x is None:
            return None
        return (min_x, min_y, max_x, max_y)  # type: ignore[return-value]

    def orphans(self) -> list[tuple[int, int]]:
        """Pixels opacos sem vizinho opaco em nenhum dos quatro lados."""
        found: list[tuple[int, int]] = []
        for x, y, color in self:
            if color[3] == 0:
                continue
            neighbours = (
                self.is_opaque(x + 1, y),
                self.is_opaque(x - 1, y),
                self.is_opaque(x, y + 1),
                self.is_opaque(x, y - 1),
            )
            if not any(neighbours):
                found.append((x, y))
        return found

    def stats(self) -> CanvasStats:
        """O retrato do canvas que o Review Loop lê."""
        colors = self.colors()
        opaque = sum(colors.values())
        total = self.width * self.height
        return CanvasStats(
            width=self.width,
            height=self.height,
            opaque_pixels=opaque,
            color_count=len(colors),
            occupancy=opaque / total if total else 0.0,
            bounds=self.bounds(),
            orphan_pixels=len(self.orphans()),
        )

    def edge_pixels(self) -> list[tuple[int, int]]:
        """Posições **vazias** que encostam em pixel opaco.

        É a borda de fora do desenho — onde o contorno é desenhado. Devolver
        as posições, e não desenhar nelas, mantém a decisão com o Review Loop
        e a execução com as ferramentas.
        """
        found: list[tuple[int, int]] = []
        for x, y, color in self:
            if color[3] != 0:
                continue
            touches = (
                self.is_opaque(x + 1, y),
                self.is_opaque(x - 1, y),
                self.is_opaque(x, y + 1),
                self.is_opaque(x, y - 1),
            )
            if any(touches):
                found.append((x, y))
        return found

    # ------------------------------------------------------------------
    # Saída
    # ------------------------------------------------------------------
    def to_bytes(self) -> bytes:
        """Os pixels em RGBA cru, na ordem de leitura."""
        data = bytearray(self.width * self.height * 4)
        for index, color in enumerate(self._pixels):
            offset = index * 4
            data[offset : offset + 4] = bytes(color)
        return bytes(data)

    def flatten(self, background: RGBA) -> "PixelCanvas":
        """Cópia com o transparente trocado por uma cor de fundo sólida."""
        clone = PixelCanvas(self.width, self.height, list(self._pixels))
        for index, color in enumerate(clone._pixels):
            if color[3] == 0:
                clone._pixels[index] = background
        return clone

    def copy(self) -> "PixelCanvas":
        return PixelCanvas(self.width, self.height, list(self._pixels))

    def apply_all(self, positions: Iterable[tuple[int, int]], color: RGBA) -> int:
        """Pinta uma sequência de posições com a mesma cor."""
        return sum(1 for x, y in positions if self.set(x, y, color))
