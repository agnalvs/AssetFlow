"""AssetFlow Pixel Agent — a estratégia que desenha pixel a pixel.

    canvas.py      a grade: um pixel lógico = uma posição   (§20)
    palette.py     as cores e o guarda que as limita         (§22)
    planner.py     o plano por receitas                      (§17)
    llm/           o plano por modelo de linguagem           (§18)
    executor.py    quem aplica as ferramentas                (§19)
    reviewer.py    quem inspeciona e descreve                (§23, §24)
    agent.py       quem orquestra e corrige                  (§15)
    session.py     quanto esforço cabe                       (§25)
    strategy.py    o encaixe no AssetFlow                    (§12)
    contracts/     plano, comandos e laudo
    tools/         uma ferramenta de desenho por arquivo     (§16)

Este pacote **não** é uma gaveta. Ele mora fora de ``generation/engines/``
porque não é um motor de imagem: um motor recebe prompt e devolve imagem; este
agente planeja, desenha com ferramentas, olha o resultado e volta atrás.

Ele nasceu como a gaveta ``texel-style-v1``, e isso era um erro de categoria —
o que o plano de correção existe para desfazer. Quem o oferece ao sistema é a
:class:`~assetflow.generation.pixel_agent.strategy.PixelAgentStrategy`, ao
lado da ``ModelGenerationStrategy``, e não o ``EngineRegistry``.
"""

from .agent import AGENT_ID, AGENT_VERSION, AgentDrawing, AssetFlowPixelAgent
from .canvas import PixelCanvas
from .contracts import DrawingBrief, DrawingPlan, ReviewInstructions, ToolCall
from .executor import PixelToolExecutor
from .llm import ChatClient, ChatConfig, LLMPlanner
from .palette import PaletteManager, SpritePalette
from .planner import PixelPlanner, PlanningAgent, RecipePlanner
from .reviewer import PixelReviewer
from .session import ITERATIONS_BY_QUALITY, AgentSession, QualityMode

__all__ = [
    "AGENT_ID",
    "AGENT_VERSION",
    "ITERATIONS_BY_QUALITY",
    "AgentDrawing",
    "AgentSession",
    "AssetFlowPixelAgent",
    "ChatClient",
    "ChatConfig",
    "DrawingBrief",
    "DrawingPlan",
    "LLMPlanner",
    "PaletteManager",
    "PixelCanvas",
    "PixelPlanner",
    "PixelReviewer",
    "PixelToolExecutor",
    "PlanningAgent",
    "RecipePlanner",
    "QualityMode",
    "ReviewInstructions",
    "SpritePalette",
    "ToolCall",
]
