"""AssetFlow Pixel Optimizer — o estágio que todo motor herda (plano Optimizer).

O que este pacote resolve
-------------------------
O AssetFlow tinha dois caminhos para produzir Pixel Art: um motor de IA ou um
agente que desenhava sozinho. Quem pedia um asset precisava **escolher entre
os dois** — e escolher errado era comum, porque a escolha certa depende de
coisas que só se sabem depois de ver o resultado.

O plano Optimizer desfaz essa bifurcação. Não existem dois caminhos: existe um
só, e o agente deixa de ser uma alternativa ao motor para virar o que sempre
fez melhor — **corrigir pixel a pixel** o que um motor gerou:

    Motor -> PixelPostProcessor -> Validação V1 -> Optimizer -> Validação V2
                                                                    -> Aceitação

Quem pede um asset escolhe **o motor**, e só. A otimização não é uma opção da
interface: ela é parte do pipeline (§33, §46).

As peças
--------
:mod:`.canvas`
    O sprite em edição, sempre na resolução lógica real (§14).
:mod:`.reviewer`
    Mede e descreve. Não corrige.
:mod:`.planner`
    Decide o que corrigir — e o que preservar (§17).
:mod:`.executor`
    Aplica, com a guarda de paleta, e registra tudo (§13, §16).
:mod:`.loop`
    Revisa, planeja, corrige, repete. Três voltas no máximo (§19).
:mod:`.optimizer`
    A fachada, com a regra de ouro: otimizar não pode piorar (§20).

Como o resto do módulo Pixel, nada aqui conhece motor, job, storage ou
biblioteca de IA. Ele recebe ``(imagem, PixelOutputSpec, validação)``.
"""

from .canvas import RGBA, TRANSPARENT, CanvasStats, PixelCanvas
from .contracts import (
    IssueSeverity,
    OptimizationReport,
    OptimizationStatus,
    PixelIssue,
    PixelReview,
    RepairAction,
    RepairPlan,
)
from .executor import PixelToolExecutor, ToolCallLog, ToolCallRecord
from .loop import MAX_ITERATIONS, ReviewLoop
from .optimizer import (
    OPTIMIZER_VERSION,
    AssetFlowPixelOptimizer,
    OptimizationOutcome,
)
from .palette import PaletteGuard, PaletteViolation
from .planner import RepairPlanner
from .reviewer import PixelReviewer

__all__ = [
    "MAX_ITERATIONS",
    "OPTIMIZER_VERSION",
    "RGBA",
    "TRANSPARENT",
    "AssetFlowPixelOptimizer",
    "CanvasStats",
    "IssueSeverity",
    "OptimizationOutcome",
    "OptimizationReport",
    "OptimizationStatus",
    "PaletteGuard",
    "PaletteViolation",
    "PixelCanvas",
    "PixelIssue",
    "PixelReview",
    "PixelReviewer",
    "PixelToolExecutor",
    "RepairAction",
    "RepairPlan",
    "RepairPlanner",
    "ReviewLoop",
    "ToolCallLog",
    "ToolCallRecord",
]
