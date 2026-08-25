"""PlanningAgent — a etapa 2 do engine estilo Texel (plano de motores §9.1 e §9.2).

O agente recebe o pedido já resolvido e produz um **plano de desenho**: o
tamanho do canvas, a paleta, as regiões nomeadas e a sequência de tool calls
que constrói o sprite. Só depois disso alguma coisa é pintada.

Por que planejar antes de desenhar, e não desenhar direto
---------------------------------------------------------
Porque o plano é inspecionável. Ele é o objeto que o §9.2 desenha — canvas,
asset_type, subject, palette, regions — e ele existe separado da execução para
que se possa olhar *o que o agente pretendia* antes de olhar o resultado.
Quando um sprite sai errado, a primeira pergunta é sempre se o plano estava
errado ou se a execução estava; sem plano explícito, não há como separar.

O planejador desta versão é **determinístico e baseado em receitas**. Não há
LLM aqui, e isso é uma escolha, não uma limitação temporária:

* uma receita produz o mesmo sprite para a mesma seed, sempre — e é isso que
  torna o engine comparável no benchmark do §19;
* ela roda em milissegundos, sem rede e sem chave de API;
* ela é legível: "tronco é um retângulo de 0.42 a 0.58 da largura" é uma
  afirmação que se discute.

O ponto de extensão para um planejador com LLM está desenhado: quem quiser
substituir esta classe só precisa devolver um :class:`DrawingPlan`. O resto do
engine — executor, review loop, exportação — não muda uma linha.
"""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from .palette import SpritePalette, palette_for
from .tool_executor import ToolCall

__all__ = ["DrawingBrief", "DrawingPlan", "PlanningAgent", "RECIPE_KEYWORDS"]


@dataclass(frozen=True, slots=True)
class DrawingBrief:
    """O pedido, na forma de que o planejador precisa.

    É uma tradução do :class:`ImageGenerationRequest`, e existe para que o
    planejador não dependa do contrato universal: ele fala de canvas, sujeito
    e cores, não de capacidade, variação ou seed de motor.
    """

    subject: str
    asset_type: str
    width: int
    height: int
    max_colors: int | None = None
    transparent: bool = True
    seed: int = 0


@dataclass(frozen=True, slots=True)
class DrawingPlan:
    """O plano intermediário do plano de motores §9.2."""

    canvas: tuple[int, int]
    asset_type: str
    subject: str
    recipe: str
    palette: SpritePalette
    #: ``{"copa": (x0, y0, x1, y1)}`` — as regiões que a receita reconhece.
    regions: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    calls: tuple[ToolCall, ...] = ()

    def document(self) -> dict[str, Any]:
        """O plano como JSON, no formato que o §9.2 mostra."""
        return {
            "canvas": list(self.canvas),
            "asset_type": self.asset_type,
            "subject": self.subject,
            "recipe": self.recipe,
            "palette": list(self.palette.colors()),
            "regions": [
                {"name": name, "bbox": list(bbox)}
                for name, bbox in self.regions.items()
            ],
            "calls": len(self.calls),
        }


#: Palavras que escolhem a receita, em português e inglês — o mesmo princípio
#: da taxonomia de assets: vocabulário é configuração de linguagem, não lógica.
#:
#: A ordem importa: a primeira receita cujo termo aparecer no sujeito vence, e
#: as mais específicas vêm antes. "wooden chest" tem de casar com ``chest``,
#: não com a madeira genérica.
RECIPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "potion",
        ("potion", "pocao", "elixir", "flask", "frasco", "vial", "garrafa", "bottle"),
    ),
    (
        "chest",
        ("chest", "bau", "crate", "caixa", "coffer", "treasure", "tesouro"),
    ),
    (
        "sword",
        ("sword", "espada", "blade", "lamina", "dagger", "adaga", "knife", "faca"),
    ),
    (
        "coin",
        ("coin", "moeda", "gold piece", "medal", "medalha", "token", "ficha"),
    ),
    (
        "tree",
        ("tree", "arvore", "pine", "pinheiro", "oak", "carvalho", "bush", "arbusto",
         "shrub", "palm", "palmeira", "foliage", "folhagem"),
    ),
    (
        "rock",
        ("rock", "rocha", "stone", "pedra", "boulder", "pedregulho", "ore", "minerio",
         "crystal", "cristal", "gem", "gema"),
    ),
    (
        "tile",
        ("tile", "azulejo", "block", "bloco", "brick", "tijolo", "ground", "chao",
         "floor", "piso", "grass tile", "wall", "parede", "tileset"),
    ),
    (
        "character",
        ("character", "personagem", "knight", "cavaleiro", "mage", "mago", "wizard",
         "warrior", "guerreiro", "hero", "heroi", "slime", "monster", "monstro",
         "goblin", "orc", "elf", "elfo", "npc", "girl", "boy", "man", "woman"),
    ),
)

#: Tipos de asset que puxam uma receita mesmo sem palavra reconhecida. Serve
#: ao caso "um objeto qualquer classificado como tileset": a receita de tile é
#: melhor palpite do que a genérica.
_TYPE_RECIPES: dict[str, str] = {
    "tile": "tile",
    "tileset": "tile",
    "character": "character",
    "icon": "coin",
}


class PlanningAgent:
    """Escolhe a receita e monta a sequência de tool calls."""

    def __init__(self) -> None:
        self._recipes: dict[str, Callable[[_Layout], list[ToolCall]]] = {
            "tree": _recipe_tree,
            "rock": _recipe_rock,
            "potion": _recipe_potion,
            "chest": _recipe_chest,
            "tile": _recipe_tile,
            "sword": _recipe_sword,
            "coin": _recipe_coin,
            "character": _recipe_character,
            "generic": _recipe_generic,
        }

    @property
    def recipes(self) -> tuple[str, ...]:
        return tuple(sorted(self._recipes))

    # ------------------------------------------------------------------
    def plan(self, brief: DrawingBrief) -> DrawingPlan:
        """Monta o plano de desenho deste pedido."""
        recipe = self.choose_recipe(brief.subject, brief.asset_type)
        palette = palette_for(recipe).limited_to(brief.max_colors)
        layout = _Layout(
            width=brief.width,
            height=brief.height,
            palette=palette,
            rng=random.Random(brief.seed),
            seed=brief.seed,
        )
        calls = self._recipes[recipe](layout)
        return DrawingPlan(
            canvas=(brief.width, brief.height),
            asset_type=brief.asset_type,
            subject=brief.subject,
            recipe=recipe,
            palette=palette,
            regions=dict(layout.regions),
            calls=tuple(calls),
        )

    def choose_recipe(self, subject: str, asset_type: str) -> str:
        """Qual receita descreve este sujeito.

        Sujeito primeiro, tipo depois. É a mesma prioridade que a taxonomia do
        AssetFlow já usa e pelo mesmo motivo: uma árvore continua sendo uma
        árvore quando o profile se chama `pixel_character_64`.
        """
        text = _normalize(subject)
        for recipe, keywords in RECIPE_KEYWORDS:
            if any(_contains_word(text, keyword) for keyword in keywords):
                return recipe
        return _TYPE_RECIPES.get(asset_type, "generic")


# ---------------------------------------------------------------------------
# Geometria compartilhada pelas receitas
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _Layout:
    """Converte proporções em coordenadas de pixel.

    As receitas são escritas em frações do canvas — "o tronco vai de 0.42 a
    0.58 da largura" — e não em pixels. É o que faz a mesma receita produzir
    um sprite coerente em 16×16 e em 128×128, que é o requisito do seletor de
    resolução da tela.
    """

    width: int
    height: int
    palette: SpritePalette
    rng: random.Random
    seed: int
    regions: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)

    def x(self, ratio: float) -> int:
        return max(0, min(self.width - 1, round(ratio * (self.width - 1))))

    def y(self, ratio: float) -> int:
        return max(0, min(self.height - 1, round(ratio * (self.height - 1))))

    def span(self, ratio: float) -> int:
        """Um comprimento em fração do menor lado — usado por raios."""
        return max(1, round(ratio * min(self.width, self.height)))

    def color(self, role: str, fallback: str | None = None) -> str:
        return self.palette.role(role, fallback)

    def region(
        self, name: str, x0: float, y0: float, x1: float, y1: float
    ) -> tuple[int, int, int, int]:
        """Registra uma região nomeada e devolve a caixa em pixels."""
        box = (self.x(x0), self.y(y0), self.x(x1), self.y(y1))
        self.regions[name] = box
        return box

    def rect(
        self, name: str, x0: float, y0: float, x1: float, y1: float, role: str,
        *, fallback: str | None = None, note: str | None = None,
    ) -> ToolCall:
        """Um ``fill_rect`` em coordenadas fracionárias, já registrado."""
        box = self.region(name, x0, y0, x1, y1)
        return ToolCall(
            tool="fill_rect",
            params={
                "x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
                "color": self.color(role, fallback),
            },
            note=note or name,
        )

    def circle(
        self, name: str, cx: float, cy: float, radius: float, role: str,
        *, fallback: str | None = None, filled: bool = True, note: str | None = None,
    ) -> ToolCall:
        """Um ``draw_circle`` em coordenadas fracionárias, já registrado."""
        center_x, center_y = self.x(cx), self.y(cy)
        r = self.span(radius)
        self.regions[name] = (
            max(0, center_x - r), max(0, center_y - r),
            min(self.width - 1, center_x + r), min(self.height - 1, center_y + r),
        )
        return ToolCall(
            tool="draw_circle",
            params={
                "cx": center_x, "cy": center_y, "radius": r,
                "color": self.color(role, fallback), "filled": filled,
            },
            note=note or name,
        )

    def noise(
        self, region: str, role: str, density: float, *,
        fallback: str | None = None, note: str | None = None,
    ) -> ToolCall:
        """Ruído semeado sobre uma região já desenhada."""
        box = self.regions.get(region, (0, 0, self.width - 1, self.height - 1))
        return ToolCall(
            tool="noise_fill_rect",
            params={
                "x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
                "color": self.color(role, fallback),
                "density": density,
                # A seed sai do nome da região: duas texturas no mesmo sprite
                # precisam de padrões diferentes, e a mesma região precisa do
                # mesmo padrão em toda execução.
                "seed": (self.seed + _stable_hash(region)) % (2**31),
                "only_over_opaque": True,
            },
            note=note or f"textura de {region}",
        )


def _stable_hash(text: str) -> int:
    """Hash determinístico entre execuções.

    ``hash()`` de string em Python é aleatorizado por processo (PYTHONHASHSEED),
    então usá-lo aqui faria o mesmo pedido produzir texturas diferentes a cada
    reinício do backend — e o engine deixaria de ser reproduzível.
    """
    total = 0
    for char in text:
        total = (total * 131 + ord(char)) % (2**31)
    return total


def _normalize(text: str) -> str:
    """Minúsculas, sem acento — para casar "árvore" com "arvore"."""
    lowered = (text or "").lower()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _contains_word(text: str, keyword: str) -> bool:
    """Casa o termo respeitando fronteira de palavra.

    Sem isso, "ore" (minério) casaria dentro de "more", e "arvore" dentro de
    qualquer frase que contivesse a palavra. É o mesmo cuidado que a taxonomia
    de assets já toma com o vocabulário dela.
    """
    if " " in keyword:
        return keyword in text
    padded = f" {text} "
    for separator in (",", ".", ";", ":", "!", "?", "(", ")", "-", "/"):
        padded = padded.replace(separator, " ")
    return f" {keyword} " in padded or f" {keyword}s " in padded


# ---------------------------------------------------------------------------
# Receitas (plano de motores §15 — props simples primeiro, personagem por último)
# ---------------------------------------------------------------------------
def _recipe_tree(layout: _Layout) -> list[ToolCall]:
    """Árvore: tronco reto e copa em três bolhas sobrepostas.

    Três bolhas, e não uma: um círculo só lê como pirulito. A sobreposição
    assimétrica é o que dá silhueta de copa em poucos pixels.
    """
    return [
        layout.rect("tronco", 0.42, 0.55, 0.58, 0.94, "trunk", fallback=layout.palette.shade),
        layout.rect("tronco_sombra", 0.42, 0.55, 0.47, 0.94, "trunk_shade",
                    fallback=layout.palette.shade, note="lado sombreado do tronco"),
        layout.circle("copa", 0.50, 0.34, 0.27, "base", note="copa central"),
        layout.circle("copa_esquerda", 0.31, 0.44, 0.19, "base"),
        layout.circle("copa_direita", 0.69, 0.44, 0.19, "base"),
        layout.circle("copa_topo", 0.50, 0.22, 0.17, "base"),
        layout.noise("copa", "light", 0.28, note="luz na copa"),
        layout.noise("copa_esquerda", "shade", 0.30, note="sombra à esquerda"),
        layout.noise("copa_direita", "shade", 0.22, note="sombra à direita"),
        ToolCall(tool="view_canvas", params={}, note="conferir a copa"),
    ]


def _recipe_rock(layout: _Layout) -> list[ToolCall]:
    """Pedra: base larga, topo facetado, luz em cima e sombra embaixo."""
    return [
        layout.circle("massa", 0.50, 0.62, 0.30, "base"),
        layout.rect("base", 0.18, 0.62, 0.82, 0.86, "base"),
        ToolCall(
            tool="draw_triangle",
            params={
                "x0": layout.x(0.26), "y0": layout.y(0.64),
                "x1": layout.x(0.52), "y1": layout.y(0.24),
                "x2": layout.x(0.76), "y2": layout.y(0.64),
                "color": layout.color("base"),
            },
            note="faceta superior",
        ),
        layout.rect("faceta_luz", 0.30, 0.34, 0.52, 0.60, "light", note="face iluminada"),
        layout.noise("base", "shade", 0.34, note="sombra na base"),
        layout.noise("massa", "accent", 0.14, note="granulado"),
        ToolCall(tool="view_canvas", params={}, note="conferir a silhueta"),
    ]


def _recipe_potion(layout: _Layout) -> list[ToolCall]:
    """Poção: rolha, gargalo, bojo de vidro e líquido no fundo.

    O líquido é desenhado **depois** do vidro e um pouco mais abaixo: é essa
    diferença de altura que faz o olho ler "meio cheia" em vez de "bola
    colorida dentro de um círculo".
    """
    return [
        layout.rect("rolha", 0.43, 0.06, 0.57, 0.18, "cork", fallback=layout.palette.shade),
        layout.rect("gargalo", 0.45, 0.18, 0.55, 0.38, "base", note="gargalo de vidro"),
        layout.circle("bojo", 0.50, 0.64, 0.27, "base", note="bojo de vidro"),
        layout.circle("liquido", 0.50, 0.70, 0.21, "liquid",
                      fallback=layout.palette.accent),
        layout.noise("liquido", "liquid_light", 0.20,
                     fallback=layout.palette.light, note="brilho do líquido"),
        ToolCall(
            tool="draw_pixels",
            params={
                "points": [
                    [layout.x(0.38), layout.y(0.56)],
                    [layout.x(0.38), layout.y(0.60)],
                    [layout.x(0.41), layout.y(0.53)],
                ],
                "color": layout.color("light"),
            },
            note="reflexo no vidro",
        ),
        ToolCall(tool="view_canvas", params={}, note="conferir o vidro"),
    ]


def _recipe_chest(layout: _Layout) -> list[ToolCall]:
    """Baú: corpo, tampa mais larga, cintas de metal e fecho."""
    return [
        layout.rect("corpo", 0.16, 0.44, 0.84, 0.86, "base"),
        layout.rect("tampa", 0.12, 0.24, 0.88, 0.46, "light", note="tampa"),
        layout.rect("juncao", 0.12, 0.42, 0.88, 0.46, "shade", note="junção tampa/corpo"),
        layout.rect("cinta_esquerda", 0.26, 0.24, 0.32, 0.86, "metal",
                    fallback=layout.palette.accent),
        layout.rect("cinta_direita", 0.68, 0.24, 0.74, 0.86, "metal",
                    fallback=layout.palette.accent),
        layout.rect("fecho", 0.44, 0.44, 0.56, 0.58, "metal",
                    fallback=layout.palette.accent),
        layout.rect("buraco_fechadura", 0.48, 0.49, 0.52, 0.54, "outline",
                    note="furo da fechadura"),
        layout.noise("corpo", "shade", 0.16, note="veios da madeira"),
        ToolCall(tool="view_canvas", params={}, note="conferir o fecho"),
    ]


def _recipe_tile(layout: _Layout) -> list[ToolCall]:
    """Bloco/azulejo: preenche o canvas inteiro e trabalha as bordas.

    A única receita que ocupa 100% do canvas, e tem de ser assim: um tile com
    margem transparente não encosta no vizinho, e a folga apareceria como uma
    grade de falhas ao montar o cenário.
    """
    return [
        layout.rect("face", 0.0, 0.0, 1.0, 1.0, "base"),
        layout.rect("topo", 0.0, 0.0, 1.0, 0.16, "light", note="borda superior iluminada"),
        layout.rect("fundo", 0.0, 0.84, 1.0, 1.0, "shade", note="borda inferior sombreada"),
        layout.rect("lateral_esquerda", 0.0, 0.0, 0.08, 1.0, "light"),
        layout.rect("lateral_direita", 0.92, 0.0, 1.0, 1.0, "shade"),
        layout.noise("face", "accent", 0.18, note="granulado da face"),
        layout.noise("fundo", "outline", 0.12, note="sujeira na base"),
        ToolCall(tool="view_canvas", params={}, note="conferir o encaixe"),
    ]


def _recipe_sword(layout: _Layout) -> list[ToolCall]:
    """Espada: ponta, lâmina com fio iluminado, guarda, cabo e pomo."""
    return [
        ToolCall(
            tool="draw_triangle",
            params={
                "x0": layout.x(0.44), "y0": layout.y(0.16),
                "x1": layout.x(0.50), "y1": layout.y(0.04),
                "x2": layout.x(0.56), "y2": layout.y(0.16),
                "color": layout.color("base"),
            },
            note="ponta da lâmina",
        ),
        layout.rect("lamina", 0.44, 0.14, 0.56, 0.62, "base"),
        layout.rect("fio", 0.44, 0.14, 0.48, 0.62, "light", note="fio iluminado"),
        layout.rect("guarda", 0.26, 0.62, 0.74, 0.69, "guard",
                    fallback=layout.palette.accent),
        layout.rect("cabo", 0.45, 0.69, 0.55, 0.88, "handle",
                    fallback=layout.palette.shade),
        layout.circle("pomo", 0.50, 0.91, 0.07, "guard", fallback=layout.palette.accent),
        ToolCall(tool="view_canvas", params={}, note="conferir a silhueta"),
    ]


def _recipe_coin(layout: _Layout) -> list[ToolCall]:
    """Moeda: disco, anel interno e um brilho de três pixels."""
    return [
        layout.circle("disco", 0.50, 0.50, 0.36, "shade"),
        layout.circle("face", 0.50, 0.50, 0.30, "base"),
        layout.circle("anel", 0.50, 0.50, 0.19, "shade", filled=False, note="anel interno"),
        ToolCall(
            tool="draw_pixels",
            params={
                "points": [
                    [layout.x(0.36), layout.y(0.32)],
                    [layout.x(0.40), layout.y(0.28)],
                    [layout.x(0.32), layout.y(0.38)],
                ],
                "color": layout.color("light"),
            },
            note="brilho",
        ),
        ToolCall(tool="view_canvas", params={}, note="conferir o disco"),
    ]


def _recipe_character(layout: _Layout) -> list[ToolCall]:
    """Personagem simples, de frente.

    O plano de motores §15 pede explicitamente para **não** começar por personagens
    complexos, e esta receita respeita isso: ela é um boneco legível — cabeça,
    tronco, braços, pernas —, não uma tentativa de anatomia. Ela existe para
    que um pedido de personagem neste motor produza algo coerente em vez de
    cair na receita genérica e devolver uma bolha.
    """
    return [
        layout.circle("cabeca", 0.50, 0.22, 0.13, "skin", fallback=layout.palette.accent),
        layout.rect("cabelo", 0.37, 0.09, 0.63, 0.17, "hair",
                    fallback=layout.palette.shade, note="cabelo"),
        layout.rect("tronco", 0.38, 0.36, 0.62, 0.66, "base"),
        layout.rect("braco_esquerdo", 0.28, 0.38, 0.37, 0.62, "shade"),
        layout.rect("braco_direito", 0.63, 0.38, 0.72, 0.62, "shade"),
        # As pernas precisam de uma coluna vazia entre elas. Encostadas, e
        # sendo da mesma cor, elas viram um bloco só — o boneco fica com
        # saia. Um pixel de folga é o que resolve, e em 32×32 é o suficiente.
        layout.rect("perna_esquerda", 0.38, 0.66, 0.46, 0.92, "shade"),
        layout.rect("perna_direita", 0.54, 0.66, 0.62, 0.92, "shade"),
        layout.rect("peito", 0.44, 0.40, 0.56, 0.54, "light", note="luz no peito"),
        ToolCall(
            tool="draw_pixels",
            params={
                "points": [
                    [layout.x(0.44), layout.y(0.22)],
                    [layout.x(0.56), layout.y(0.22)],
                ],
                "color": layout.color("outline"),
            },
            note="olhos",
        ),
        ToolCall(tool="view_canvas", params={}, note="conferir a pose"),
    ]


def _recipe_generic(layout: _Layout) -> list[ToolCall]:
    """Prop genérico: massa central sobre uma base, com luz e sombra.

    O fallback honesto. Ele não tenta adivinhar o que é o objeto — produz um
    volume centrado, legível e com silhueta limpa, que é o mínimo que um asset
    precisa ter. Reconhecer um sujeito novo é acrescentar termos em
    :data:`RECIPE_KEYWORDS` e uma receita ao lado desta.
    """
    return [
        layout.circle("massa", 0.50, 0.52, 0.28, "base"),
        layout.rect("base", 0.26, 0.62, 0.74, 0.86, "base"),
        layout.rect("luz", 0.34, 0.34, 0.52, 0.52, "light", note="face iluminada"),
        layout.noise("base", "shade", 0.30, note="sombra na base"),
        layout.noise("massa", "accent", 0.12, note="detalhe"),
        ToolCall(tool="view_canvas", params={}, note="conferir o volume"),
    ]
