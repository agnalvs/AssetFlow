"""RepairPlanner — quem decide o que corrigir (plano Optimizer §12 e §17).

O revisor diz o que está errado. O planejador diz **o que fazer a respeito** —
e, tão importante quanto, o que deixar quieto.

A regra que dá nome ao módulo (§17)
-----------------------------------
Nem todo problema tem correção segura. Um pixel isolado pode ser ruído da
quantização ou pode ser **um olho** — e o AssetFlow já decidiu, no plano Pixel
§106, que não destrói detalhe intencional para melhorar uma nota.

O planejador distingue os dois casos pela **cor**:

* cor que aparece só naquele pixel (ou em mais um) é resíduo de quantização —
  ninguém desenha um detalhe com uma cor que não usa em nenhum outro lugar;
* cor que o sprite usa em quantidade é vocabulário do desenho — o preto do
  olho é o mesmo preto do contorno, e apagá-lo é apagar o rosto.

O que é preservado não some do relatório: vai para ``RepairPlan.declined``,
com o motivo. "Não corrigi, e aqui está por quê" é informação; silêncio não é.

O que o planejador nunca faz
----------------------------
**Não desenha o que não existe.** Contorno esfarelado é remendado; contorno
*ausente* não é criado. A diferença é a fronteira do §79: o Optimizer trabalha
sobre o que um motor gerou, não no lugar dele. Adicionar uma linha escura em
volta de um sprite que nunca teve contorno é uma decisão de estilo, e estilo é
do profile e do motor.

**Não preenche canvas vazio.** ``empty_canvas`` é reprovação honesta: inventar
pixels para tapar o buraco entregaria um asset que ninguém pediu, com nota
melhor. É o caso mais claro de ``NO_SAFE_REPAIRS``.

**Não move o sprite.** ``border_touch`` se resolve recortando e reencaixando —
que é trabalho do ``PixelPostProcessor``, e o ``_harden_spec`` já o faz.
Refazê-lo aqui, um pixel de cada vez, seria a mesma correção em dois lugares.
"""

from __future__ import annotations

from ..contracts.output_spec import PixelOutputSpec
from .canvas import RGBA, PixelCanvas
from .contracts import PixelIssue, PixelReview, RepairAction, RepairPlan

__all__ = [
    "MAX_OUTLINE_PATCH_RATIO",
    "MAX_REPAIRS_PER_ROUND",
    "RARE_COLOR_OCCURRENCES",
    "RepairPlanner",
]

#: Até quantas ocorrências no sprite inteiro uma cor é considerada resíduo de
#: quantização, e não detalhe intencional (§17).
RARE_COLOR_OCCURRENCES = 2

#: Fração máxima da fronteira do sprite que um remendo de contorno pode
#: cobrir. Acima disso não existe contorno a remendar — existe contorno a
#: criar, e criar é do motor (§79).
MAX_OUTLINE_PATCH_RATIO = 0.3

#: Teto de ações por volta. O laço tem três voltas (§19), então nada aqui
#: impede uma correção grande — ele só impede que **uma** volta reescreva o
#: sprite antes de alguém medir se a primeira correção ajudou.
MAX_REPAIRS_PER_ROUND = 64

#: Problemas que o planejador reconhece e sabe declinar com motivo. Um tipo
#: fora desta lista também é declinado, mas com o motivo genérico — o que é
#: um sinal de que o revisor aprendeu a ver algo que o planejador ainda não
#: sabe tratar.
_KNOWN_WITHOUT_REPAIR = {
    "empty_canvas": (
        "sprite quase vazio não tem correção honesta: preencher inventaria "
        "conteúdo que ninguém pediu"
    ),
    "overfilled_canvas": (
        "apagar pixels para abrir silhueta seria apagar o desenho; a correção "
        "é de enquadramento, não de reparo"
    ),
    "border_touch": (
        "reenquadrar é trabalho do PixelPostProcessor, que já tenta recortar e "
        "reencaixar quando o conteúdo encosta na borda"
    ),
}


class RepairPlanner:
    """Converte um :class:`PixelReview` em um :class:`RepairPlan` (§12)."""

    def plan(
        self,
        review: PixelReview,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
    ) -> RepairPlan:
        plan = RepairPlan()
        colors = canvas.colors()
        budget = MAX_REPAIRS_PER_ROUND

        for issue in review.issues:
            if budget <= 0:
                plan.decline(
                    issue.type,
                    f"teto de {MAX_REPAIRS_PER_ROUND} reparos por volta atingido; "
                    "fica para a próxima iteração",
                )
                continue

            actions = self._for(issue, canvas, spec, colors, plan)
            for action in actions[:budget]:
                plan.add(action)
            budget -= len(actions)

        return plan

    # ------------------------------------------------------------------
    def _for(
        self,
        issue: PixelIssue,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        colors: dict[RGBA, int],
        plan: RepairPlan,
    ) -> list[RepairAction]:
        handler = getattr(self, f"_plan_{issue.type}", None)
        if handler is None:
            plan.decline(
                issue.type,
                _KNOWN_WITHOUT_REPAIR.get(
                    issue.type, "nenhuma correção segura conhecida para este problema"
                ),
            )
            return []
        return handler(issue, canvas, spec, colors, plan)

    # -- órfãos --------------------------------------------------------
    def _plan_orphan_pixel(
        self,
        issue: PixelIssue,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        colors: dict[RGBA, int],
        plan: RepairPlan,
    ) -> list[RepairAction]:
        """Apagar, ligar ou preservar — a decisão do §17, pixel a pixel."""
        if issue.position is None:  # pragma: no cover - o revisor sempre põe
            return []
        x, y = issue.position
        color = canvas.get(x, y)
        occurrences = colors.get(color, 0)

        if occurrences > RARE_COLOR_OCCURRENCES:
            plan.decline(
                issue.type,
                f"pixel ({x}, {y}) preservado: a cor aparece {occurrences}x no "
                "sprite, então é vocabulário do desenho e não ruído — pode ser "
                "um olho, um brilho ou a ponta de uma espada",
            )
            return []

        if spec.cleanup.mode == "off":
            plan.decline(
                issue.type,
                "o profile desligou a limpeza (cleanup.mode = off)",
            )
            return []

        return [
            RepairAction(
                tool="erase_pixel",
                params={"x": x, "y": y},
                reason=(
                    f"pixel isolado em ({x}, {y}) com cor usada apenas "
                    f"{occurrences}x — resíduo da quantização"
                ),
                issue_type=issue.type,
            )
        ]

    # -- contorno ------------------------------------------------------
    def _plan_fragmented_outline(
        self,
        issue: PixelIssue,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        colors: dict[RGBA, int],
        plan: RepairPlan,
    ) -> list[RepairAction]:
        # ``cleanup.protect_outline`` não entra aqui de propósito: ele proíbe
        # **apagar** pixel de contorno, e ``repair_outline`` só pinta posições
        # vazias. As duas regras protegem a mesma coisa.
        if not issue.pixels:
            plan.decline(issue.type, "nenhuma posição de silhueta exposta")
            return []

        outline, border_total = _dominant_border_color(canvas)
        if outline is None:
            plan.decline(
                issue.type,
                "não foi possível identificar a cor do contorno; criar uma "
                "seria decidir estilo no lugar do motor",
            )
            return []

        # A fronteira entre remendar e desenhar (§79). Se quase toda a silhueta
        # está exposta, o sprite não tem contorno esfarelado — ele não tem
        # contorno. Pintar a volta inteira com a cor de fronteira não criaria
        # uma linha: engordaria o sprite em um anel da sua própria cor, e a
        # cada volta do laço em um anel a mais.
        if len(issue.pixels) > border_total * MAX_OUTLINE_PATCH_RATIO:
            plan.decline(
                issue.type,
                f"{len(issue.pixels)} de {border_total} pixels de fronteira "
                "estão expostos: não há contorno a remendar, e criar um seria "
                "decidir estilo no lugar do motor",
            )
            return []

        return [
            RepairAction(
                tool="repair_outline",
                params={"color": outline, "only": [list(point) for point in issue.pixels]},
                reason=(
                    f"{len(issue.pixels)} posição(ões) de silhueta sem linha; "
                    "remendo com a cor de contorno já usada pelo sprite"
                ),
                issue_type=issue.type,
            )
        ]

    # -- paleta --------------------------------------------------------
    def _plan_palette_overflow(
        self,
        issue: PixelIssue,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        colors: dict[RGBA, int],
        plan: RepairPlan,
    ) -> list[RepairAction]:
        """Absorve as cores raras nas vizinhas — sem apagar um pixel sequer.

        Trocar a cor preserva a forma; apagar o pixel abriria um buraco no
        sprite para caber no orçamento, o que é a troca errada.
        """
        limit = spec.max_colors
        if limit is None:  # pragma: no cover - o revisor não emite sem limite
            return []

        ordered = list(colors)
        keep = ordered[:limit]
        excess = ordered[limit:]
        if not keep or not excess:
            plan.decline(issue.type, "não há cor de destino para absorver o excesso")
            return []

        return [
            RepairAction(
                tool="replace_color",
                params={"from_color": color, "to_color": _closest(color, keep)},
                reason=(
                    f"cor rara ({colors[color]}x) absorvida pela mais próxima "
                    f"dentro do orçamento de {limit} cores"
                ),
                issue_type=issue.type,
            )
            for color in excess
        ]

    def _plan_locked_palette_violation(
        self,
        issue: PixelIssue,
        canvas: PixelCanvas,
        spec: PixelOutputSpec,
        colors: dict[RGBA, int],
        plan: RepairPlan,
    ) -> list[RepairAction]:
        """Traz cada intrusa para a cor mais próxima **da paleta do projeto**.

        Aqui aproximar é correto, e no executor não é (§16): a diferença é
        quem escolhe. O planejador escolhe entre as cores que o projeto
        autorizou; o executor, se aproximasse, escolheria entre as que já
        estão na imagem — que podem ser as próprias intrusas.
        """
        allowed = [_as_rgba(color) for color in spec.palette.colors]
        if not allowed:  # pragma: no cover - o spec exige `colors` em locked
            plan.decline(issue.type, "a paleta travada do projeto está vazia")
            return []

        intruders = [color for color in colors if color not in set(allowed)]
        return [
            RepairAction(
                tool="replace_color",
                params={"from_color": color, "to_color": _closest(color, allowed)},
                reason=(
                    f"cor {_hex(color)} não pertence à paleta travada; trocada "
                    f"pela mais próxima do projeto"
                ),
                issue_type=issue.type,
            )
            for color in intruders
        ]


# ----------------------------------------------------------------------
def _dominant_border_color(canvas: PixelCanvas) -> tuple[RGBA | None, int]:
    """A cor de contorno do sprite e quantos pixels de fronteira ele tem.

    O contorno é, por definição geométrica, a cor que mais aparece encostando
    no vazio — a mesma definição que o ``OutlineAnalyzer`` usa. Deduzi-la do
    canvas em vez de recebê-la do profile é o que faz o remendo usar a linha
    que o sprite já tem, em vez de uma nova.

    O total volta junto porque é o denominador da regra do §79: remendar é
    corrigir uma fração da fronteira, não repintá-la.
    """
    counts: dict[RGBA, int] = {}
    for x, y, color in canvas:
        if color[3] == 0:
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if canvas.contains(x + dx, y + dy) and not canvas.is_opaque(x + dx, y + dy):
                counts[color] = counts.get(color, 0) + 1
                break
    if not counts:
        return None, 0
    dominant = max(counts.items(), key=lambda item: item[1])[0]
    return dominant, sum(counts.values())


def _closest(color: RGBA, candidates: list[RGBA]) -> RGBA:
    return min(
        candidates,
        key=lambda item: sum(
            (int(item[index]) - int(color[index])) ** 2 for index in range(3)
        ),
    )


def _hex(color: RGBA) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


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
