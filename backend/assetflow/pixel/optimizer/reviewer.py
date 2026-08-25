"""PixelReviewer — o diagnóstico do Optimizer (plano Optimizer §11).

O revisor **olha e descreve**. Ele não corrige nada: recebe o canvas já na
resolução lógica, o :class:`PixelOutputSpec` e o
:class:`PixelValidationReport` da validação V1, e devolve um
:class:`PixelReview` — problemas com posição e severidade.

Por que ele lê o relatório do Validator em vez de medir de novo
---------------------------------------------------------------
Porque medir duas vezes é como se produz divergência: o Validator diz "23
cores para um orçamento de 16" e o revisor, contando à sua maneira, diria 22 —
e ninguém saberia qual dos dois está certo. O Validator é a fonte da verdade
sobre *o que* está errado; o revisor acrescenta apenas o que o relatório não
tem e o planejador precisa: **onde**.

Essa é a divisão de trabalho: o Validator mede a imagem inteira e resume; o
revisor pergunta ao canvas quais pixels exatos produziram aquele resumo.

O que ele procura
-----------------
``orphan_pixel``
    Pixel opaco sem vizinho. Em 1024px ninguém vê; em 32×32 salta aos olhos.
    Cada órfão vira um problema **separado**, com sua posição — é o que
    permite ao planejador aplicar o §17 pixel a pixel em vez de no atacado.
``fragmented_outline``
    O contorno existe e está esfarelado. Só isso: contorno **ausente** não é
    problema deste módulo (ver ``planner.py``).
``palette_overflow``
    Cores acima do orçamento (``PX-COLOR-001``).
``locked_palette_violation``
    Cor fora da paleta travada do projeto (``PX-PALETTE-001``).
``empty_canvas`` / ``overfilled_canvas`` / ``border_touch``
    Observações sem correção segura. O revisor as registra mesmo assim: um
    laudo que só menciona o que sabe consertar esconde metade do diagnóstico.
"""

from __future__ import annotations

from ..contracts.output_spec import PixelOutputSpec
from ..contracts.validation_report import PixelValidationReport
from .canvas import RGBA, PixelCanvas
from .contracts import IssueSeverity, PixelIssue, PixelReview

__all__ = ["PixelReviewer"]

#: Fragmentação acima da qual o contorno é considerado esfarelado. É o mesmo
#: limiar do ``OutlineAnalyzer``: dois números diferentes para a mesma
#: pergunta produziriam um aviso que o Optimizer ignora e uma correção que o
#: Validator não pediu.
_OUTLINE_FRAGMENTATION = 0.15


class PixelReviewer:
    """Transforma medida em diagnóstico localizado (plano Optimizer §11)."""

    name = "heuristic"

    def review(
        self,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        validation: PixelValidationReport,
    ) -> PixelReview:
        stats = canvas.stats()
        review = PixelReview(
            canvas={
                "size": [stats.width, stats.height],
                "opaque_pixels": stats.opaque_pixels,
                "color_count": stats.color_count,
                "occupancy": round(stats.occupancy, 4),
                "orphan_pixels": stats.orphan_pixels,
                "bounds": list(stats.bounds) if stats.bounds else None,
            }
        )

        codes = {check.code for check in validation.failures}
        warnings = {warning.code for warning in validation.quality.warnings}
        metrics = validation.quality.metrics
        colors = canvas.colors()

        # Um problema por órfão: o §17 decide caso a caso, e um problema
        # agregado ("14 órfãos") não teria como ser decidido caso a caso.
        for x, y in canvas.orphans():
            color = canvas.get(x, y)
            occurrences = colors.get(color, 0)
            review.add(
                PixelIssue(
                    type="orphan_pixel",
                    severity=(
                        IssueSeverity.MEDIUM if occurrences <= 2 else IssueSeverity.LOW
                    ),
                    position=(x, y),
                    detail=(
                        f"pixel opaco isolado em ({x}, {y}); a cor aparece "
                        f"{occurrences}x no sprite"
                    ),
                    pixels=((x, y),),
                )
            )

        if "PX-WARN-OUTLINE-FRAGMENTED" in warnings or (
            metrics.outline_fragmentation > _OUTLINE_FRAGMENTATION
        ):
            outline = _outline_color(metrics.outline_colors)
            exposed = _exposed_positions(canvas, outline)
            if exposed:
                review.add(
                    PixelIssue(
                        type="fragmented_outline",
                        severity=IssueSeverity.MEDIUM,
                        region="silhueta",
                        detail=(
                            f"contorno com fragmentação "
                            f"{metrics.outline_fragmentation:.2f}; "
                            f"{len(exposed)} posição(ões) de silhueta sem linha"
                        ),
                        pixels=tuple(exposed),
                    )
                )

        limit = spec.max_colors
        if "PX-COLOR-001" in codes and limit is not None:
            excess = _rarest(colors, len(colors) - limit)
            review.add(
                PixelIssue(
                    type="palette_overflow",
                    severity=IssueSeverity.HIGH,
                    region="paleta",
                    detail=(
                        f"{len(colors)} cores para um orçamento de {limit}; "
                        f"{len(excess)} cor(es) precisam ser absorvidas"
                    ),
                    pixels=tuple(_positions_of(canvas, excess)),
                )
            )

        if "PX-PALETTE-001" in codes and spec.palette.is_locked:
            allowed = {_as_rgba(color) for color in spec.palette.colors}
            intruders = [color for color in colors if color not in allowed]
            review.add(
                PixelIssue(
                    type="locked_palette_violation",
                    severity=IssueSeverity.HIGH,
                    region="paleta",
                    detail=(
                        f"{len(intruders)} cor(es) fora da paleta travada do projeto"
                    ),
                    pixels=tuple(_positions_of(canvas, intruders)),
                )
            )

        if "PX-EMPTY-001" in codes or "PX-WARN-OCCUPANCY-LOW" in warnings:
            review.add(
                PixelIssue(
                    type="empty_canvas",
                    severity=IssueSeverity.HIGH,
                    region="canvas",
                    detail=f"o sprite ocupa apenas {stats.occupancy:.1%} do canvas",
                )
            )

        if "PX-WARN-OCCUPANCY-HIGH" in warnings:
            review.add(
                PixelIssue(
                    type="overfilled_canvas",
                    severity=IssueSeverity.MEDIUM,
                    region="canvas",
                    detail=(
                        f"o sprite cobre {stats.occupancy:.1%} do canvas e "
                        "quase não sobrou silhueta"
                    ),
                )
            )

        if "PX-BOUND-001" in codes or "PX-WARN-BORDER" in warnings:
            review.add(
                PixelIssue(
                    type="border_touch",
                    severity=IssueSeverity.MEDIUM,
                    region="silhueta",
                    detail="o sprite encosta na borda e o contorno não cabe",
                )
            )

        return review


# ----------------------------------------------------------------------
def _outline_color(colors: tuple[str, ...]) -> RGBA | None:
    """A cor predominante do contorno, se o Validator conseguiu identificá-la."""
    if not colors:
        return None
    return _as_rgba(colors[0])


def _exposed_positions(
    canvas: PixelCanvas, outline: RGBA | None
) -> list[tuple[int, int]]:
    """Vazios encostados em cor de silhueta que **não** é o contorno.

    A pergunta não é "existe borda livre?" — essa é verdade para qualquer
    sprite com margem, contorno inclusive, e um laço que a use pede contorno
    a cada volta, engorda o sprite em um anel por iteração e nunca converge.

    A pergunta é sobre a **cor** exposta: se todo pixel de fronteira já é o
    contorno, o trabalho está feito.
    """
    if outline is None:
        return []
    found: list[tuple[int, int]] = []
    for x, y, color in canvas:
        if color[3] != 0:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbour = canvas.get(x + dx, y + dy)
            if neighbour[3] > 0 and neighbour != outline:
                found.append((x, y))
                break
    return found


def _rarest(colors: dict[RGBA, int], count: int) -> list[RGBA]:
    """As ``count`` cores menos usadas — as candidatas a serem absorvidas.

    ``colors`` já vem ordenado da mais frequente para a menos pelo
    :meth:`PixelCanvas.colors`, então as últimas são as raras.
    """
    if count <= 0:
        return []
    return list(colors)[-count:]


def _positions_of(canvas: PixelCanvas, colors) -> list[tuple[int, int]]:
    wanted = set(colors)
    return [(x, y) for x, y, color in canvas if color in wanted]


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
