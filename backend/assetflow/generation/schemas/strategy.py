"""Estratégia de criação — **como** o asset será produzido (plano de correção §2).

A distinção que este módulo existe para manter, e que o plano de correção §51
declara obrigatória::

    STRATEGY   = como o asset será criado
    ENGINE     = qual tecnologia/modelo gera uma imagem
    AGENT      = sistema que toma decisões e usa ferramentas

Antes disto, o AssetFlow tinha um seletor só, chamado "Motor", com FLUX, SDXL,
Pixel Forge, SD-πXL e o agente de desenho lado a lado. Os quatro primeiros são
motores; o quinto é uma estratégia inteira. Oferecê-los juntos dizia à pessoa
que as cinco coisas são intercambiáveis — quando o tempo, os controles e a
natureza do resultado são diferentes.

Agora existem duas perguntas, e elas são feitas na ordem certa:

    1. Como criar?     Automático | Modelo de imagem | Agente Pixel
    2. Com o quê?      (só na primeira) qual motor / (só na segunda) qual agente
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import AssetFlowModel

__all__ = [
    "GenerationStrategyType",
    "AgentQualityMode",
    "AgentRef",
    "StrategyDescriptor",
]


class GenerationStrategyType(str, Enum):
    """Os métodos de criação (plano de correção §37)."""

    #: O AssetFlow escolhe a estratégia — e, se for por modelo, também o motor.
    AUTO = "auto"
    #: Prompt → motor de imagem → imagem.
    MODEL = "model"
    #: Prompt → planejamento → ferramentas → canvas → revisão → asset.
    PIXEL_AGENT = "pixel_agent"

    @property
    def uses_engine(self) -> bool:
        """A estratégia despacha para um motor de imagem?

        É o que o plano de correção §8 exige saber: a seleção de motor só faz
        sentido em ``model``. Perguntá-la em ``pixel_agent`` seria oferecer um
        controle que não tem efeito.
        """
        return self is GenerationStrategyType.MODEL


class AgentQualityMode(str, Enum):
    """Quanto esforço o agente pode gastar (plano de correção §25)."""

    AUTO = "auto"
    FAST = "fast"
    BALANCED = "balanced"
    DETAILED = "detailed"


class AgentRef(AssetFlowModel):
    """Referência ao agente que produziu um asset (plano de correção §28).

    O equivalente do :class:`~.engine.EngineRef` para o outro lado da
    arquitetura. Existir separado é o ponto: um asset feito pelo agente **não
    tem** motor, e forçá-lo a preencher um ``EngineRef`` faria o histórico
    afirmar que um modelo gerou o que nenhum modelo gerou.
    """

    id: str
    version: str
    #: O modelo que planejou, quando o planner usar um (plano de correção §18).
    #: Vazio no planner determinístico de hoje — e é informação, não lacuna:
    #: significa que nenhum LLM participou do desenho.
    planner_provider: str | None = None
    planner_model: str | None = None


class StrategyDescriptor(AssetFlowModel):
    """Um método de criação como a interface o vê (plano de correção §32).

    É o análogo do ``EngineCatalogEntry``, um nível acima: a tela desenha o
    seletor "Método de criação" a partir desta lista, e não de nomes escritos
    no frontend.
    """

    id: GenerationStrategyType
    display_name: str
    summary: str = ""
    description: str = ""
    #: Esta estratégia pode atender o pedido agora? ``auto`` fica indisponível
    #: só quando nenhuma das outras está.
    available: bool = True
    unavailable_reason: str | None = None
    #: ``True`` quando a tela deve mostrar o seletor de motor (plano §5).
    selects_engine: bool = False
    #: ``True`` quando a tela deve mostrar agente e modo de qualidade.
    selects_agent: bool = False
    highlights: tuple[str, ...] = ()
    metadata: dict[str, str] = Field(default_factory=dict)
