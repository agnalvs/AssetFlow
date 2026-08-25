"""Paletas do engine estilo Texel (plano de motores §9.2).

Um agente que desenha pixel a pixel tem uma vantagem que nenhum modelo de
difusão tem: ele **escolhe** as cores antes de pintar, em vez de produzir
milhares delas e deixar alguém quantizar depois. É por isso que esta gaveta
declara ``palette_control`` no catálogo — a paleta não é um limite imposto no
fim, é o material com que o desenho começa.

Cada paleta tem papéis nomeados em vez de uma lista solta de cores. Um papel
diz *para que serve* aquela cor — ``base``, ``shade``, ``light``, ``accent``,
``outline`` —, e é isso que permite que a mesma receita de árvore funcione com
a paleta de árvore e com a de pedra sem nenhuma linha condicional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .canvas import RGBA

__all__ = [
    "DEFAULT_PALETTE",
    "PALETTES",
    "PaletteManager",
    "SpritePalette",
    "palette_for",
]


@dataclass(frozen=True, slots=True)
class SpritePalette:
    """As cores de um sprite, por papel.

    ``extra`` guarda os papéis específicos de uma receita — o marrom do tronco
    da árvore, o dourado do fecho do baú. Eles ficam separados dos cinco papéis
    universais para que uma receita nova possa pedir uma cor própria sem
    inchar o contrato de todas as outras.
    """

    base: str
    shade: str
    light: str
    accent: str
    outline: str
    extra: dict[str, str] | None = None

    def role(self, name: str, fallback: str | None = None) -> str:
        """A cor de um papel, com fallback explícito.

        Pedir um papel inexistente sem fallback é erro de programação na
        receita, e é melhor que apareça como exceção do que como um pixel
        preto que ninguém explica.
        """
        if name in {"base", "shade", "light", "accent", "outline"}:
            return getattr(self, name)
        if self.extra and name in self.extra:
            return self.extra[name]
        if fallback is not None:
            return fallback
        raise KeyError(f"papel de cor desconhecido na paleta: '{name}'")

    def roles(self) -> dict[str, str]:
        """Os papéis nomeados, como o ``palette_roles`` do §17.

        O plano de desenho declara papéis, não uma lista de hexadecimais: é o
        papel que permite a uma correção pedir "mais highlight na copa" em vez
        de "mais #74AA59", e é o que faz a mesma receita funcionar com paletas
        diferentes.
        """
        named = {
            "base": self.base,
            "shade": self.shade,
            "light": self.light,
            "accent": self.accent,
            "outline": self.outline,
        }
        named.update(self.extra or {})
        return named

    def colors(self) -> tuple[str, ...]:
        """Todas as cores, sem repetição, na ordem de importância visual."""
        ordered = [self.base, self.shade, self.light, self.accent, self.outline]
        ordered.extend((self.extra or {}).values())
        return tuple(dict.fromkeys(ordered))

    def limited_to(self, max_colors: int | None) -> "SpritePalette":
        """A mesma paleta cabendo no orçamento de cores do pedido.

        Quando o orçamento é apertado, os papéis que somem são os de
        *variação* — ``light`` e ``accent`` viram ``base`` —, nunca ``base``
        nem ``outline``. É a ordem certa: um sprite sem contorno perde a
        silhueta, que é a única coisa que se lê em 16×16; um sprite sem
        segunda tonalidade só fica mais chapado.
        """
        if max_colors is None or len(self.colors()) <= max_colors:
            return self
        if max_colors <= 2:
            return SpritePalette(
                base=self.base,
                shade=self.base,
                light=self.base,
                accent=self.base,
                outline=self.outline,
            )
        if max_colors == 3:
            return SpritePalette(
                base=self.base,
                shade=self.shade,
                light=self.base,
                accent=self.shade,
                outline=self.outline,
            )
        # Com 4 ou mais, os papéis universais cabem; o que sai são os extras.
        return SpritePalette(
            base=self.base,
            shade=self.shade,
            light=self.light,
            accent=self.accent if max_colors > 4 else self.shade,
            outline=self.outline,
            extra=self._trimmed_extra(max_colors),
        )

    def _trimmed_extra(self, max_colors: int) -> dict[str, str]:
        """Mantém os extras que ainda couberem, mapeando o resto para ``base``."""
        if not self.extra:
            return {}
        universal = len({self.base, self.shade, self.light, self.accent, self.outline})
        room = max(0, max_colors - universal)
        trimmed: dict[str, str] = {}
        for index, (name, color) in enumerate(self.extra.items()):
            trimmed[name] = color if index < room else self.base
        return trimmed


#: As paletas de partida, por receita. São poucas e conservadoras de
#: propósito: o objetivo do MVP é um prop legível, não uma direção de arte.
PALETTES: dict[str, SpritePalette] = {
    "tree": SpritePalette(
        base="#4a8c3f",
        shade="#2f6b2a",
        light="#6fbf50",
        accent="#8fd96a",
        outline="#1e2a1a",
        extra={"trunk": "#6b4a2b", "trunk_shade": "#4a3220"},
    ),
    "house": SpritePalette(
        base="#d9c9a8",
        shade="#ab9877",
        light="#f0e4c8",
        accent="#a4453a",
        outline="#2a2019",
        extra={
            "roof": "#a4453a",
            "roof_shade": "#7a2f28",
            "door": "#6b4a2b",
            "window": "#6ea8c9",
        },
    ),
    "rock": SpritePalette(
        base="#8a8a92",
        shade="#5f5f68",
        light="#b4b4bd",
        accent="#6f6f78",
        outline="#2e2e34",
    ),
    "potion": SpritePalette(
        base="#cfe8f5",
        shade="#8fb6c9",
        light="#ffffff",
        accent="#d4386a",
        outline="#24202a",
        extra={"liquid": "#d4386a", "liquid_light": "#ff7aa2", "cork": "#8b5a2b"},
    ),
    "chest": SpritePalette(
        base="#8a5a2b",
        shade="#5e3b1a",
        light="#a8763f",
        accent="#d9b23c",
        outline="#241708",
        extra={"metal": "#d9b23c", "metal_shade": "#8f6f1c"},
    ),
    "tile": SpritePalette(
        base="#7a6a55",
        shade="#574a3a",
        light="#9c8a72",
        accent="#6a5a46",
        outline="#2c241b",
    ),
    "sword": SpritePalette(
        base="#cdd3da",
        shade="#8d949c",
        light="#f0f4f8",
        accent="#b8860b",
        outline="#23262b",
        extra={"handle": "#6b4a2b", "guard": "#b8860b"},
    ),
    "coin": SpritePalette(
        base="#f2c14e",
        shade="#b5852a",
        light="#ffe08a",
        accent="#8a6320",
        outline="#4a3410",
    ),
    "character": SpritePalette(
        base="#4a6fa5",
        shade="#33507a",
        light="#6f92c4",
        accent="#e8b48c",
        outline="#1d2330",
        extra={"skin": "#e8b48c", "hair": "#5a3b22"},
    ),
}

#: Usada quando a receita genérica atende. Neutra e fria de propósito: ela não
#: deve parecer uma escolha de arte, e sim um objeto ainda sem identidade.
DEFAULT_PALETTE = SpritePalette(
    base="#6f7fa8",
    shade="#47536f",
    light="#9aa9cc",
    accent="#c7d2ea",
    outline="#1f2430",
)


def palette_for(recipe: str) -> SpritePalette:
    """A paleta de uma receita, ou a neutra."""
    return PALETTES.get(recipe, DEFAULT_PALETTE)


class PaletteManager:
    """O guarda da paleta (plano de correção §22).

    Regra do §22: *o agente só pode usar cores presentes na paleta resolvida*.
    Se o pedido diz 16 cores, não existe décima sétima — e a regra vale
    **durante** o desenho, não só na conferência do fim.

    A diferença entre as duas coisas é grande. Corrigir a paleta depois é
    remapear pixels que já foram pintados: o desenho perde tonalidades em
    lugares que o agente escolheu a dedo, e o resultado é uma imagem que
    ninguém planejou. Barrar a cor na hora faz a substituição acontecer onde a
    decisão está sendo tomada, com a informação de qual papel ela deveria
    cumprir.

    Cor desconhecida não é erro: ela é **resolvida** para a mais próxima que
    já está em uso. Erro seria recusar a pincelada e deixar um buraco no
    sprite por causa de dois pontos de diferença em um canal.
    """

    def __init__(self, allowed: Sequence[str], *, max_colors: int | None = None) -> None:
        self._allowed: list[RGBA] = []
        self._max_colors = max_colors
        for color in allowed:
            self.admit(color)

    @property
    def colors(self) -> tuple[RGBA, ...]:
        return tuple(self._allowed)

    @property
    def is_full(self) -> bool:
        return self._max_colors is not None and len(self._allowed) >= self._max_colors

    def admit(self, color: "str | RGBA") -> bool:
        """Acrescenta uma cor à paleta, se ainda houver espaço."""
        rgba = _as_rgba(color)
        if rgba[3] == 0 or rgba in self._allowed:
            return True
        if self.is_full:
            return False
        self._allowed.append(rgba)
        return True

    def resolve(self, color: "str | RGBA") -> RGBA:
        """A cor que o agente pode de fato usar no lugar da pedida.

        Transparente passa direto: apagar não gasta uma entrada da paleta, e
        tratar o alpha 0 como cor faria o orçamento ser consumido pela
        borracha.
        """
        rgba = _as_rgba(color)
        if rgba[3] == 0:
            return rgba
        if rgba in self._allowed:
            return rgba
        if not self.is_full:
            self._allowed.append(rgba)
            return rgba
        if not self._allowed:  # pragma: no cover - paleta de tamanho zero
            return rgba
        return _closest(rgba, self._allowed)


def _as_rgba(value: "str | RGBA") -> RGBA:
    """Aceita ``#rgb``, ``#rrggbb``, ``#rrggbbaa`` e tuplas."""
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


def _closest(color: RGBA, candidates: Sequence[RGBA]) -> RGBA:
    """A mais próxima em distância euclidiana no RGB.

    RGB simples, e não um espaço perceptual: as paletas do agente têm meia
    dúzia de cores bem separadas, e a diferença entre RGB e CIELAB nesse
    cenário não muda a escolha — muda só o custo.
    """
    return min(
        candidates,
        key=lambda item: sum(
            (int(item[index]) - int(color[index])) ** 2 for index in range(3)
        ),
    )
