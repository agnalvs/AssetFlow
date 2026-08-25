"""AssetFlow Pixel Agent — desenha o asset pixel a pixel (plano de correção §15).

    DrawingBrief
        -> PlanningAgent        o plano: regiões, papéis de cor, comandos
        -> PixelToolExecutor    as ferramentas pintam
        -> PixelCanvas          o estado
        -> PixelReviewer        o laudo: o que está errado
        -> reparo               o agente aplica o que sabe aplicar
        -> AgentDrawing         PNG no grid + plano + log + laudos

Por que isto **não** é um motor
-------------------------------
Foi assim que ele nasceu — como a gaveta ``texel-style-v1`` —, e era um erro de
categoria. Um motor recebe um prompt e devolve uma imagem; o que ele faz por
dentro é problema dele. Este agente não é isso: ele *toma decisões*, usa
ferramentas, olha o resultado e volta atrás. Oferecê-lo no mesmo seletor que
FLUX e SDXL dizia à pessoa que as três coisas são intercambiáveis, quando o
tempo, o resultado e os controles são de naturezas diferentes.

Agora ele é o que sempre foi: a implementação de uma **estratégia de criação**
(:class:`~assetflow.generation.pixel_agent.strategy.PixelAgentStrategy`).

O que ele desenha depende do planejador
---------------------------------------
Com o :class:`~.planner.RecipePlanner` — o padrão — o vocabulário é finito:
árvore, pedra, poção, baú, tile, casa, espada, moeda, boneco. Fora disso, uma
forma genérica.

Com o :class:`~.llm.LLMPlanner`, não há vocabulário: o plano vem de um modelo
de linguagem e o agente desenha qualquer sujeito, mantendo as mesmas garantias
— grade exata, paleta fechada, silhueta contornada, log reconstruível.

Nos dois casos, ``planner.recognizes()`` responde se o objeto está ao alcance,
e é isso que permite à escolha automática não mandar para cá o que este agente
não sabe fazer, e à escolha manual avisar antes de entregar.

Sobre o nome (plano de correção §33)
------------------------------------
O vocabulário de ferramentas veio da arquitetura tool-based do Texel Studio, e
o pacote se chamou ``texel_style`` durante o desenvolvimento. Na interface o
nome é **AssetFlow Pixel Agent**: identidade própria, e nenhuma sugestão de
que o AssetFlow esteja incorporando um produto de terceiros — que ele não
está, já que este código é todo daqui.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Any

from PIL import Image

from .canvas import RGBA, PixelCanvas
from .contracts.command import ToolCall
from .contracts.plan import DrawingBrief, DrawingPlan, ReviewInstructions
from .executor import PixelToolExecutor
from .palette import PaletteManager
from .planner import PixelPlanner, RecipePlanner
from .reviewer import PixelReviewer
from .session import AgentSession, QualityMode

__all__ = ["AGENT_ID", "AGENT_VERSION", "AgentDrawing", "AssetFlowPixelAgent"]

_LOG = logging.getLogger("assetflow.pixel_agent")

#: Identidade do agente nos metadados e no seletor (plano de correção §28).
AGENT_ID = "assetflow_pixel_agent"
AGENT_VERSION = "0.1.0"


@dataclass(slots=True)
class AgentDrawing:
    """Um sprite desenhado, com tudo que explica como ele ficou assim."""

    data: bytes
    width: int
    height: int
    seed: int
    plan: DrawingPlan
    session: AgentSession

    def document(self) -> dict[str, Any]:
        return {
            "plan": self.plan.document(),
            "session": self.session.document(),
            "tool_calls": self.session.log.document(),
        }


class AssetFlowPixelAgent:
    """O agente de desenho do AssetFlow.

    Ele não conhece job, storage, capacidade nem motor. Recebe um
    :class:`DrawingBrief` e devolve um :class:`AgentDrawing` — quem o encaixa
    no sistema é a estratégia.
    """

    id = AGENT_ID
    version = AGENT_VERSION

    def __init__(
        self,
        planner: PixelPlanner | None = None,
        reviewer: PixelReviewer | None = None,
    ) -> None:
        # O planejador é a peça trocável (plano de correção §18): receitas por
        # padrão, modelo de linguagem quando houver um configurado. O resto do
        # agente não sabe qual dos dois está ali.
        self._planner = planner or RecipePlanner()
        self._reviewer = reviewer or PixelReviewer()

    @property
    def planner(self) -> PixelPlanner:
        return self._planner

    @property
    def recipes(self) -> tuple[str, ...]:
        return self._planner.recipes

    # ------------------------------------------------------------------
    def draw(
        self,
        brief: DrawingBrief,
        *,
        quality: QualityMode | str = QualityMode.BALANCED,
        max_iterations: int | None = None,
        auto_review: bool = True,
        budgets: dict[QualityMode, int] | None = None,
    ) -> AgentDrawing:
        """Planeja, desenha, revisa e corrige — nesta ordem."""
        session = AgentSession.for_quality(
            quality,
            max_iterations=max_iterations,
            auto_review=auto_review,
            budgets=budgets,
        )

        # -- etapa 1: planejar ------------------------------------------
        plan = self._planner.plan(brief)
        session.plan = plan

        # A paleta do plano é o orçamento do agente daqui em diante (§22).
        palette = PaletteManager(plan.palette.colors(), max_colors=brief.max_colors)
        executor = PixelToolExecutor(palette=palette)

        # -- etapa 2: desenhar ------------------------------------------
        canvas = PixelCanvas(brief.width, brief.height)
        executor.execute_all(canvas, plan.calls, session.log)

        # -- etapa 3: revisar e corrigir --------------------------------
        if session.auto_review:
            self._review_loop(canvas, executor, plan, brief, session)

        # -- etapa 4: exportar ------------------------------------------
        if not brief.transparent:
            canvas = canvas.flatten(_as_rgba(plan.palette.outline))

        return AgentDrawing(
            data=_encode_png(canvas),
            width=canvas.width,
            height=canvas.height,
            seed=brief.seed,
            plan=plan,
            session=session,
        )

    # ------------------------------------------------------------------
    def _review_loop(
        self,
        canvas: PixelCanvas,
        executor: PixelToolExecutor,
        plan: DrawingPlan,
        brief: DrawingBrief,
        session: AgentSession,
    ) -> None:
        """O laço do §23: inspecionar, receber o laudo, corrigir.

        Ele para cedo quando o laudo não tem nada acionável — gastar as seis
        iterações de um modo ``detailed`` em um sprite que já está limpo não
        melhora nada e cobra o tempo assim mesmo.
        """
        for _ in range(session.max_iterations):
            review = self._reviewer.review(
                canvas, plan=plan, max_colors=brief.max_colors
            )
            session.record_review(review)

            if not review.actionable:
                break

            applied = self._repair(canvas, executor, plan, brief, review, session)
            if applied == 0:
                # O laudo apontou problemas que nenhuma ação resolveu. Insistir
                # produziria as mesmas iterações e o mesmo resultado.
                break

    def _repair(
        self,
        canvas: PixelCanvas,
        executor: PixelToolExecutor,
        plan: DrawingPlan,
        brief: DrawingBrief,
        review: ReviewInstructions,
        session: AgentSession,
    ) -> int:
        """Aplica as ações recomendadas — sempre pelas ferramentas (§24).

        A ordem importa e custou um teste para aparecer: **limpar antes,
        contornar depois**. Contornar primeiro envolve todo pixel opaco,
        inclusive o pixel solto que a limpeza ia remover; envolvido, ele deixa
        de ser órfão, sobrevive e vira um borrão de cinco pixels no meio do
        nada. A sujeira não só permanece, como fica maior.
        """
        actions = {
            action
            for issue in review.actionable
            for action in issue.recommended_actions
        }
        applied = 0

        if "remove_orphans" in actions:
            applied += self._remove_orphans(canvas, executor, session)
        if "add_outline" in actions:
            applied += self._add_outline(canvas, executor, plan, session)
        if "enforce_palette" in actions:
            applied += self._enforce_palette(canvas, executor, brief, session)
        return applied

    # ------------------------------------------------------------------
    def _remove_orphans(
        self, canvas: PixelCanvas, executor: PixelToolExecutor, session: AgentSession
    ) -> int:
        orphans = canvas.orphans()
        if not orphans:
            return 0
        record = executor.execute(
            canvas,
            ToolCall(
                tool="draw_pixels",
                params={
                    "points": [list(point) for point in orphans],
                    # Alpha 0: apagar é pintar de transparente. Não existe
                    # ferramenta de borracha, e não precisa existir.
                    "color": [0, 0, 0, 0],
                },
                note="reparo: remoção de pixels órfãos",
            ),
            session.log,
        )
        session.record_repair("PX-AGENT-ORPHAN", record.pixels_changed)
        return record.pixels_changed

    def _add_outline(
        self,
        canvas: PixelCanvas,
        executor: PixelToolExecutor,
        plan: DrawingPlan,
        session: AgentSession,
    ) -> int:
        edges = canvas.edge_pixels()
        if not edges:
            return 0
        record = executor.execute(
            canvas,
            ToolCall(
                tool="draw_pixels",
                params={
                    "points": [list(point) for point in edges],
                    "color": plan.palette.outline,
                },
                note="reparo: contorno da silhueta",
            ),
            session.log,
        )
        session.record_repair("PX-AGENT-OUTLINE", record.pixels_changed)
        return record.pixels_changed

    def _enforce_palette(
        self,
        canvas: PixelCanvas,
        executor: PixelToolExecutor,
        brief: DrawingBrief,
        session: AgentSession,
    ) -> int:
        """Rede de segurança do §22.

        Com o Palette Manager no executor, chegar aqui com cor sobrando
        significa que alguma coisa pintou por fora dele. O reparo remapeia por
        frequência: o que fica são as áreas grandes, que definem o objeto; o
        que sai são detalhes pontuais — a ordem certa de perder informação em
        pixel art.
        """
        if brief.max_colors is None:
            return 0
        counts = canvas.colors()
        if len(counts) <= brief.max_colors:
            return 0

        keep = list(counts)[: brief.max_colors]
        applied = 0
        for color in list(counts)[brief.max_colors :]:
            points = [[x, y] for x, y, current in canvas if current == color]
            if not points:
                continue
            record = executor.execute(
                canvas,
                ToolCall(
                    tool="draw_pixels",
                    params={"points": points, "color": list(_closest(color, keep))},
                    note="reparo: ajuste de paleta",
                ),
                session.log,
            )
            applied += record.pixels_changed
        session.record_repair("PX-AGENT-PALETTE", applied)
        return applied


def _closest(color: RGBA, candidates: list[RGBA]) -> RGBA:
    return min(
        candidates,
        key=lambda item: sum(
            (int(item[index]) - int(color[index])) ** 2 for index in range(3)
        ),
    )


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


def _encode_png(canvas: PixelCanvas) -> bytes:
    """O canvas vira PNG **no tamanho do canvas** — nunca ampliado.

    Entregar na resolução lógica é a razão de ser do agente (plano de correção
    §20). O pós-processamento recebe uma imagem que já está no grid pedido,
    encontra origem e alvo iguais e passa direto: nenhuma reamostragem toca no
    desenho, e o arquivo entregue é exatamente o que o agente decidiu pixel a
    pixel.
    """
    image = Image.frombytes("RGBA", (canvas.width, canvas.height), canvas.to_bytes())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
