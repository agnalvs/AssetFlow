"""PixelReviewer — a inspeção do desenho (plano de correção §23 e §24).

O revisor **olha e descreve**. Ele não desenha, não apaga e não corrige: ele
recebe o canvas, o plano e o contrato do job, e devolve
:class:`ReviewInstructions` — uma lista de problemas com as ações
recomendadas para cada um.

Por que essa separação, se juntar seria menos código
----------------------------------------------------
Porque "medir" e "consertar" falham de formas diferentes, e um revisor que
conserta esconde as duas. Quando o revisor só descreve:

* o laudo vira dado — ele entra nos metadados do job e diz o que o agente
  encontrou, mesmo quando não soube resolver;
* a correção continua passando pelas ferramentas, e portanto pelo log, que é o
  que mantém a promessa de que o histórico reconstrói o resultado;
* trocar o revisor por um com LLM (plano de correção §18) não dá a ele o poder
  de mexer no canvas — ele continua limitado a opinar.

É a mesma fronteira que o AssetFlow já mantém entre o ``PixelValidator``, que
mede, e a ``PixelAcceptancePolicy``, que decide.

O que ele procura, e por quê
----------------------------
``PX-AGENT-ORPHAN``
    Pixel opaco sem vizinho. Em 1024px ninguém vê; em 32×32 ele é ruído que
    salta aos olhos.
``PX-AGENT-OUTLINE``
    Silhueta sem contorno. Um sprite pequeno sem linha escura em volta se
    dissolve em qualquer fundo que não seja o do editor.
``PX-AGENT-PALETTE``
    Orçamento de cores estourado. Com o Palette Manager em uso isto deveria
    ser impossível — encontrar algo aqui significa que alguém pintou por fora
    do executor, e é bom saber disso.
``PX-AGENT-EMPTY``
    Desenho quase vazio. Não há correção honesta: inventar pixels para tapar o
    buraco entregaria um asset que ninguém pediu.
``PX-AGENT-BOUNDS``
    Sprite colado nas bordas, sem folga para o contorno existir.
"""

from __future__ import annotations

from .canvas import RGBA, PixelCanvas
from .contracts.plan import DrawingPlan, ReviewInstructions

__all__ = ["PixelReviewer", "MIN_OCCUPANCY", "MAX_OCCUPANCY"]

#: Abaixo disto o sprite é considerado vazio demais para ser um asset.
MIN_OCCUPANCY = 0.02

#: Acima disto ele cobre o quadro inteiro — o que é correto para um tile e
#: suspeito para qualquer outra coisa, porque significa que não sobrou
#: silhueta para ler.
MAX_OCCUPANCY = 0.97

#: Receitas que devem mesmo ocupar o canvas inteiro. Um tile com margem
#: transparente não encosta no vizinho, e a folga apareceria como uma grade de
#: falhas ao montar o cenário.
_FULL_BLEED_RECIPES = frozenset({"tile"})


class PixelReviewer:
    """Inspeciona o canvas e devolve o laudo (plano de correção §23)."""

    def review(
        self,
        canvas: PixelCanvas,
        *,
        plan: DrawingPlan,
        max_colors: int | None = None,
    ) -> ReviewInstructions:
        """Mede o canvas e descreve o que está errado.

        As ações recomendadas usam um vocabulário fechado — ``remove_orphans``,
        ``add_outline``, ``enforce_palette`` — porque é o agente que as executa,
        e ele precisa saber o que fazer com cada uma. Um texto livre seria mais
        expressivo e não teria como ser aplicado.
        """
        stats = canvas.stats()
        instructions = ReviewInstructions(
            canvas={
                "size": [stats.width, stats.height],
                "opaque_pixels": stats.opaque_pixels,
                "color_count": stats.color_count,
                "occupancy": round(stats.occupancy, 4),
                "orphan_pixels": stats.orphan_pixels,
                "bounds": list(stats.bounds) if stats.bounds else None,
            }
        )

        if stats.orphan_pixels:
            instructions.add(
                "PX-AGENT-ORPHAN",
                "canvas",
                f"{stats.orphan_pixels} pixel(s) opaco(s) sem vizinho",
                "remove_orphans",
            )

        full_bleed = plan.recipe in _FULL_BLEED_RECIPES
        if not full_bleed and _needs_outline(canvas, _as_rgba(plan.palette.outline)):
            instructions.add(
                "PX-AGENT-OUTLINE",
                "silhueta",
                "a silhueta ainda não tem contorno",
                "add_outline",
            )

        if max_colors is not None and stats.color_count > max_colors:
            instructions.add(
                "PX-AGENT-PALETTE",
                "paleta",
                f"{stats.color_count} cores para um orçamento de {max_colors}",
                "enforce_palette",
            )

        if stats.occupancy < MIN_OCCUPANCY:
            # Sem ação recomendada: é observação, e o Validator decide depois.
            instructions.add(
                "PX-AGENT-EMPTY",
                "canvas",
                f"o desenho ocupa apenas {stats.occupancy:.1%} do canvas",
            )
        elif not full_bleed and stats.occupancy > MAX_OCCUPANCY:
            instructions.add(
                "PX-AGENT-BOUNDS",
                "canvas",
                "o desenho cobre o quadro inteiro e não sobrou silhueta",
            )

        if not full_bleed and stats.bounds and _touches_border(stats.bounds, canvas):
            instructions.add(
                "PX-AGENT-BOUNDS",
                "silhueta",
                "o desenho encosta na borda e o contorno não cabe",
            )

        return instructions


def _touches_border(bounds: tuple[int, int, int, int], canvas: PixelCanvas) -> bool:
    x0, y0, x1, y1 = bounds
    return x0 == 0 or y0 == 0 or x1 == canvas.width - 1 or y1 == canvas.height - 1


def _needs_outline(canvas: PixelCanvas, outline: RGBA) -> bool:
    """A silhueta tem alguma cor exposta que não seja o contorno?

    A pergunta parece a mesma que "existe pixel vazio encostando no desenho?",
    e não é — a diferença custou um sprite que crescia sozinho.

    "Existe borda livre" é verdade para **qualquer** desenho com margem,
    inclusive um que já foi contornado: o contorno recém-pintado também tem
    vazio em volta. Em um laço de revisão, isso pede contorno de novo a cada
    volta, cada volta engorda o sprite em um anel, e seis iterações de modo
    ``detailed`` transformam uma árvore em uma mancha que cobre o quadro.

    A pergunta certa é sobre a **cor** exposta: se todo pixel que faz fronteira
    com o vazio já é o contorno, o trabalho está feito. É o que converge.
    """
    for x, y, color in canvas:
        if color[3] == 0 or color == outline:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = (x + dx, y + dy)
            if not canvas.contains(*neighbour):
                # Encostar na borda do canvas não é cor exposta: não há para
                # onde desenhar o contorno, e o `PX-AGENT-BOUNDS` já cobre isso.
                continue
            if not canvas.is_opaque(*neighbour):
                return True
    return False


def _as_rgba(value: str) -> RGBA:
    text = value.strip().lstrip("#")
    if len(text) in (3, 4):
        text = "".join(char * 2 for char in text)
    if len(text) == 6:
        text += "ff"
    return (
        int(text[0:2], 16),
        int(text[2:4], 16),
        int(text[4:6], 16),
        int(text[6:8], 16),
    )
