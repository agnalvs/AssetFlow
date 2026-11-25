"""Do grid lógico para um tamanho que o GPT Image aceite.

Este é o coração da gaveta, e ele existe por causa de um número: o GPT Image
exige **no mínimo 655.360 pixels** por imagem. Um sprite 32×32 tem 1.024 — 640
vezes menos. Não há como pedir um sprite ao modelo.

Isso não é um obstáculo a contornar; é a confirmação da arquitetura do
AssetFlow. ``generation_resolution`` e ``logical_resolution`` são grandezas
diferentes, o motor só responde pela primeira, e quem entrega a segunda é o
Pixel Exact::

    logical 32×32  ->  render 832×832  ->  GPT Image  ->  redução  ->  32×32

As quatro regras do provedor, todas verificadas na documentação:

* ambas as arestas múltiplas de **16**;
* total de pixels entre **655.360** e **8.294.400**;
* aresta maior de no máximo **3840**;
* proporção entre a maior e a menor aresta de no máximo **3:1**.

Por que escala inteira, e não "o menor tamanho válido"
------------------------------------------------------
Porque o que vem depois é uma **redução por blocos**. Com o render sendo um
múltiplo inteiro do grid lógico, cada pixel do sprite corresponde a um bloco
exato de N×N pixels do render, e a média (ou a votação) daquele bloco é uma
resposta limpa. Com 900×900 para um grid de 32, cada pixel lógico cobriria
28,125 pixels de origem — as bordas de bloco cairiam no meio de um pixel de
origem, e a silhueta chegaria à grade já contaminada.

Um render 3% maior custa quase nada. Uma silhueta borrada custa o asset.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "MAX_EDGE",
    "MAX_RATIO",
    "MAX_TOTAL_PIXELS",
    "MIN_TOTAL_PIXELS",
    "MULTIPLE_OF",
    "RenderSize",
    "SizeNotRepresentable",
    "render_size_for",
]

#: As restrições do provedor. Elas são dele, não nossas — e por isso vivem
#: aqui dentro da gaveta, e não em nenhum contrato do AssetFlow.
MULTIPLE_OF = 16
MIN_TOTAL_PIXELS = 655_360
MAX_TOTAL_PIXELS = 8_294_400
MAX_EDGE = 3840
MAX_RATIO = 3.0


class SizeNotRepresentable(ValueError):
    """O pedido não cabe nas restrições do provedor.

    Acontece com proporções muito alongadas — uma barra de vida 128×8 tem
    proporção 16:1, e o GPT Image não passa de 3:1. É recusa honesta: gerar em
    3:1 e esticar depois entregaria um asset deformado sem avisar ninguém.
    """


@dataclass(frozen=True, slots=True)
class RenderSize:
    """O tamanho em que o motor vai gerar, e como se chegou nele."""

    width: int
    height: int
    #: Quantos pixels de render por pixel lógico. ``None`` quando não houve
    #: grid lógico (arte 2D convencional), onde a pergunta não se aplica.
    scale: int | None = None

    @property
    def as_param(self) -> str:
        """No formato que a API recebe: ``"832x832"``."""
        return f"{self.width}x{self.height}"

    @property
    def total_pixels(self) -> int:
        return self.width * self.height

    def document(self) -> dict[str, object]:
        return {
            "render_size": [self.width, self.height],
            "scale": self.scale,
            "total_pixels": self.total_pixels,
        }


def render_size_for(
    logical: tuple[int, int] | None,
    fallback: tuple[int, int],
) -> RenderSize:
    """O tamanho de geração para este pedido.

    Args:
        logical: o grid lógico do asset, quando existe. É ele que manda: o
            render precisa ser um múltiplo inteiro dele.
        fallback: a resolução de render do spec, usada quando não há grid —
            arte 2D convencional, onde não existe redução por blocos.

    Raises:
        SizeNotRepresentable: proporção fora de 3:1.
    """
    if logical is not None:
        width, height = logical
        if width > 0 and height > 0:
            return _integer_multiple(width, height)
    return _snap(*fallback)


# ----------------------------------------------------------------------
def _integer_multiple(width: int, height: int) -> RenderSize:
    """A menor escala inteira que satisfaz as quatro regras.

    A busca é por escala, e não por tamanho, porque é a escala que interessa à
    redução. Ela é limitada: assim que a aresta maior passa do teto do
    provedor, não há escala que sirva, e o caso cai no encaixe aproximado.
    """
    _reject_extreme_ratio(width, height)

    scale = 1
    while max(width, height) * scale <= MAX_EDGE:
        render_w = width * scale
        render_h = height * scale
        if (
            render_w % MULTIPLE_OF == 0
            and render_h % MULTIPLE_OF == 0
            and MIN_TOTAL_PIXELS <= render_w * render_h <= MAX_TOTAL_PIXELS
        ):
            return RenderSize(render_w, render_h, scale=scale)
        scale += 1

    # Nenhuma escala inteira serve. Acontece com grids já grandes, onde a
    # escala 1 estoura o teto de pixels — e aí a redução por blocos não é o
    # que está em jogo, porque quase não há redução.
    return _snap(width, height)


def _snap(width: int, height: int) -> RenderSize:
    """Encaixa uma proporção nas regras, sem exigir escala inteira.

    Usado quando não há grid lógico. Cresce ou encolhe proporcionalmente até
    o total de pixels entrar na faixa, e só então arredonda cada aresta para
    o múltiplo de 16 mais próximo — nessa ordem, porque arredondar antes
    moveria a proporção e poderia jogá-la para fora do limite de 3:1.
    """
    _reject_extreme_ratio(width, height)

    ratio_w, ratio_h = float(width), float(height)
    total = ratio_w * ratio_h

    if total < MIN_TOTAL_PIXELS:
        factor = (MIN_TOTAL_PIXELS / total) ** 0.5
    elif total > MAX_TOTAL_PIXELS:
        factor = (MAX_TOTAL_PIXELS / total) ** 0.5
    else:
        factor = 1.0

    render_w = _round_up_to_multiple(ratio_w * factor)
    render_h = _round_up_to_multiple(ratio_h * factor)

    # O arredondamento para cima pode ter estourado a aresta máxima ou o teto
    # de pixels; encolher um degrau resolve sem sair da proporção.
    while max(render_w, render_h) > MAX_EDGE or render_w * render_h > MAX_TOTAL_PIXELS:
        render_w = max(MULTIPLE_OF, render_w - MULTIPLE_OF)
        render_h = max(MULTIPLE_OF, render_h - MULTIPLE_OF)

    if render_w * render_h < MIN_TOTAL_PIXELS:  # pragma: no cover - defensivo
        raise SizeNotRepresentable(
            f"{width}×{height} não cabe entre {MIN_TOTAL_PIXELS} e "
            f"{MAX_TOTAL_PIXELS} pixels sem deformar a proporção"
        )
    return RenderSize(render_w, render_h, scale=None)


def _reject_extreme_ratio(width: int, height: int) -> None:
    longer, shorter = max(width, height), min(width, height)
    if shorter <= 0:
        raise SizeNotRepresentable(f"dimensão inválida: {width}×{height}")
    if longer / shorter > MAX_RATIO:
        raise SizeNotRepresentable(
            f"proporção {longer}:{shorter} passa do limite de 3:1 do GPT Image; "
            "gere este asset em um motor com resolução nativa, ou peça um "
            "enquadramento menos alongado"
        )


def _round_up_to_multiple(value: float) -> int:
    steps = int(value // MULTIPLE_OF)
    if value % MULTIPLE_OF:
        steps += 1
    return max(MULTIPLE_OF, steps * MULTIPLE_OF)
