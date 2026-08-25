"""O contrato de uma estratégia de criação (plano de correção §12).

Uma estratégia responde a uma única pergunta: **como estes pixels vão
existir?** Ela recebe o contrato do job e devolve imagens normalizadas. O que
acontece no meio — despachar para um motor, planejar e desenhar com
ferramentas, compor a partir de peças — é problema dela.

O que ela **não** faz, e é o que a mantém pequena: prompt, pós-processamento,
validação, storage e histórico continuam sendo do pipeline. A estratégia é o
trecho entre "o pedido está resolvido" e "existem pixels".

    Pipeline                       o produto: prompt, pós, storage
      └─ GenerationStrategy        como os pixels nascem      <- aqui
           ├─ ModelGenerationStrategy   -> Kernel -> Engine
           └─ PixelAgentStrategy        -> Planner -> Tools -> Canvas

Por que uma camada nova, e não mais um motor
---------------------------------------------
Porque o agente de desenho nunca coube na forma de motor. Um motor recebe
prompt e devolve imagem; o agente decide, usa ferramentas, olha o resultado e
volta atrás. Enfiá-lo no ``EngineRegistry`` funcionava — e mentia para a
pessoa que escolhia, oferecendo no mesmo seletor coisas que não são
comparáveis (plano de correção §1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..kernel.contracts import CancellationToken, NullProgressReporter, ProgressReporter
from ..kernel.service import GenerationKernel
from ..profiles import GenerationProfile
from ..schemas import (
    AssetGenerationRequest,
    EngineAdvice,
    FinalResolvedSpec,
    GenerationResult,
    GenerationStrategyType,
    SemanticPrompt,
)

__all__ = ["StrategyContext", "GenerationStrategy"]


@dataclass(slots=True)
class StrategyContext:
    """Tudo que uma estratégia precisa para produzir pixels.

    Note o que **não** está aqui: storage, job manager, repositório de
    histórico. A estratégia produz imagens; guardá-las é de outra camada.
    """

    job_id: str
    request: AssetGenerationRequest
    profile: GenerationProfile
    #: O contrato do job. Fonte única de tipo, resolução, paleta, fundo,
    #: estratégia e motor — e nenhuma estratégia o reinterpreta (plano T→J §37).
    resolved: FinalResolvedSpec
    #: A leitura semântica já resolvida pelo pipeline. As estratégias que
    #: falam com motores a transformam em texto; o agente lê o sujeito dela.
    semantic: SemanticPrompt
    #: Só as estratégias que usam motor precisam do Kernel. O agente o recebe
    #: e o ignora — e é isso que permite ligar uma referência conceitual
    #: (plano de correção §26) sem mudar o contrato.
    kernel: GenerationKernel
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    progress: ProgressReporter = field(default_factory=NullProgressReporter)
    metadata: dict[str, Any] = field(default_factory=dict)

    def report(self, progress: float, stage: str = "", **extra: Any) -> None:
        try:
            self.progress(max(0.0, min(1.0, progress)), stage, **extra)
        except Exception:  # pragma: no cover - observabilidade nunca quebra job
            pass


class GenerationStrategy(ABC):
    """Contrato de um método de criação (plano de correção §12)."""

    #: O tipo que esta estratégia implementa. É por ele que o registry a
    #: encontra — nunca por ``isinstance``.
    strategy_id: GenerationStrategyType

    #: Nome e descrição para a tela. Ficam na estratégia, e não em uma tabela
    #: no frontend, pelo mesmo motivo do catálogo de motores: acrescentar uma
    #: estratégia não pode exigir editar React.
    display_name: str = ""
    summary: str = ""
    highlights: tuple[str, ...] = ()

    @abstractmethod
    def supports(self, spec: FinalResolvedSpec) -> bool:
        """Esta estratégia consegue atender este contrato?

        Usado pela resolução automática para descartar candidatas antes de
        tentar — e pela validação, para recusar uma combinação impossível com
        uma frase em vez de um erro no meio da geração.
        """

    def accepts(self, advice: EngineAdvice) -> bool:
        """Esta estratégia é candidata na escolha **automática**?

        Diferente de :meth:`supports`, que responde sobre o contrato já
        resolvido, esta pergunta é feita antes — quando ainda se está
        decidindo o método — e serve para o resolvedor não oferecer o que a
        estratégia faria mal.

        O padrão é sim: uma estratégia de propósito geral atende qualquer
        pedido. Quem tem limite o declara aqui, e é isso que tira do
        resolvedor a necessidade de conhecer cada estratégia pelo nome — o
        ``if candidate is PIXEL_AGENT`` que estava lá era exatamente o tipo de
        acoplamento que o plano de correção §51 manda evitar.
        """
        return True

    @abstractmethod
    async def available(self) -> tuple[bool, str | None]:
        """``(dá para usar agora?, por que não)``.

        Separado de :meth:`supports` de propósito: um é sobre o *pedido*, o
        outro é sobre o *ambiente*. "Não sei fazer arte 2D" e "não há motor de
        pé nesta máquina" são recusas diferentes e produzem mensagens
        diferentes na tela.
        """

    @abstractmethod
    async def generate(self, context: StrategyContext) -> GenerationResult:
        """Produz as imagens deste job, já normalizadas."""
