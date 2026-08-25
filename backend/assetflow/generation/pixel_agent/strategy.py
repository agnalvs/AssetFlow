"""PixelAgentStrategy — o encaixe do agente no AssetFlow (plano de correção §15).

    FinalResolvedSpec
          ↓
    DrawingBrief              o pedido, na língua do agente
          ↓
    AssetFlowPixelAgent       planeja, desenha, revisa, corrige
          ↓
    GenerationResult          imagens normalizadas, como qualquer estratégia

A regra que esta classe existe para garantir (§15): **ela não chama um
diffusion model para produzir o asset final**. O único motor que pode
participar é o de referência conceitual (§26), e mesmo esse é *supporting
engine* — a imagem que ele produzir não vira asset, vira inspiração.

Ela mora dentro de ``pixel_agent/`` e não em ``strategies/`` porque é a ponte
específica deste agente. ``strategies/`` guarda o que é comum a todas: o
contrato, o registro e o resolvedor.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time

from ..schemas import (
    AgentRef,
    EngineAdvice,
    FinalResolvedSpec,
    GenerationOutput,
    GenerationResult,
    GenerationStatus,
    GenerationStrategyType,
    StageTimings,
)
from ..strategies.base import GenerationStrategy, StrategyContext
from .agent import AGENT_ID, AGENT_VERSION, AssetFlowPixelAgent
from .contracts.plan import DrawingBrief
from .session import ITERATIONS_BY_QUALITY, QualityMode

__all__ = ["PixelAgentStrategy"]

_LOG = logging.getLogger("assetflow.generation.strategies.pixel_agent")

_MAX_SEED = 2**31 - 1

#: Canvas usado quando o pedido não traz grid lógico. Só acontece em arte 2D
#: convencional, onde esta estratégia não deveria ter sido escolhida — o
#: `supports()` abaixo a descarta antes.
_FALLBACK_CANVAS = 64


class PixelAgentStrategy(GenerationStrategy):
    """Cria o asset desenhando pixel a pixel."""

    strategy_id = GenerationStrategyType.PIXEL_AGENT
    display_name = "Agente Pixel"
    summary = (
        "Um agente planeja o desenho, pinta com ferramentas na própria grade "
        "e revisa o resultado. Pixels intencionais, sem redução de imagem."
    )
    highlights = (
        "desenha direto na resolução lógica, sem reduzir imagem grande",
        "silhueta limpa e paleta exata por construção",
        "reproduzível: a mesma seed devolve o mesmo sprite",
        "vocabulário de props ainda limitado nesta primeira versão",
    )

    def __init__(
        self,
        agent: AssetFlowPixelAgent | None = None,
        *,
        quality_budgets: dict[QualityMode, int] | None = None,
    ) -> None:
        self._agent = agent or AssetFlowPixelAgent()
        self._budgets = quality_budgets or dict(ITERATIONS_BY_QUALITY)

    @property
    def agent(self) -> AssetFlowPixelAgent:
        return self._agent

    # ------------------------------------------------------------------
    def supports(self, spec: FinalResolvedSpec) -> bool:
        """Só Pixel Art, e só com grid lógico.

        Um agente que desenha pixel a pixel precisa saber quantos pixels são.
        Em arte 2D convencional não existe grid, e aceitar o pedido produziria
        um sprite pequeno esticado — pior do que recusar.
        """
        return spec.is_pixel

    def accepts(self, advice: EngineAdvice) -> bool:
        """Na escolha automática, o agente só se oferece para o que sabe fazer.

        Duas condições, e a segunda custou uma bolha entregue como casa: além
        de precisar de uma grade para desenhar, ele precisa **conhecer o
        objeto**. O planejador desenha por receitas, e um sujeito fora do
        vocabulário cai na forma genérica — que é honesta, e não é o que
        alguém quer receber ao pedir "house".

        Em seleção manual isto não se aplica: quem escolheu o agente recebe o
        agente, com um aviso de que o objeto está fora do vocabulário dele
        (plano de correção §25, regra 1, na sua versão para métodos).
        """
        if advice.mode != "pixel" or advice.logical_size is None:
            return False
        return self._agent.planner.recognizes(advice.subject, advice.asset_type)

    async def available(self) -> tuple[bool, str | None]:
        """Sempre disponível: o agente não baixa nada e não usa GPU."""
        return (True, None)

    async def generate(self, context: StrategyContext) -> GenerationResult:
        resolved = context.resolved
        config = resolved.pixel_agent

        canvas = (
            resolved.logical_resolution.size
            if resolved.logical_resolution
            else (_FALLBACK_CANVAS, _FALLBACK_CANVAS)
        )
        quality = _resolve_quality(config.quality_mode, canvas)

        base_seed = resolved.generation.seed
        if base_seed is None:
            base_seed = random.randint(0, _MAX_SEED)

        subject = context.semantic.subject.strip() or context.request.prompt.strip()
        variations = max(1, resolved.generation.variations)

        outputs: list[GenerationOutput] = []
        sessions: list[dict] = []
        watch = time.perf_counter()

        for index in range(variations):
            context.cancellation.raise_if_cancelled()
            seed = (base_seed + index * 7919) % (_MAX_SEED + 1)

            brief = DrawingBrief(
                subject=subject,
                asset_type=resolved.asset.type.value,
                width=canvas[0],
                height=canvas[1],
                max_colors=resolved.palette.max_colors if resolved.palette else None,
                transparent=resolved.background.transparent,
                seed=seed,
            )

            # O desenho é CPU pura e pode levar centenas de milissegundos em
            # 128×128. Fora do event loop: segurá-lo aqui travaria o polling
            # de status de todos os outros jobs.
            drawing = await asyncio.to_thread(
                self._agent.draw,
                brief,
                quality=quality,
                max_iterations=config.max_iterations,
                auto_review=config.auto_review,
                budgets=self._budgets,
            )

            outputs.append(
                GenerationOutput(
                    index=index,
                    mime_type="image/png",
                    width=drawing.width,
                    height=drawing.height,
                    seed=seed,
                    data=drawing.data,
                    metadata={
                        "renderer": "pixel-agent",
                        "recipe": drawing.plan.recipe,
                        "native_logical": True,
                    },
                )
            )
            sessions.append(drawing.document())
            context.report(
                (index + 1) / variations, "generating", agent_id=self._agent.id
            )

        warnings: list[str] = []
        if resolved.logical_resolution is None:
            warnings.append(
                "o pedido não traz grid lógico; o agente desenhou em "
                f"{_FALLBACK_CANVAS}×{_FALLBACK_CANVAS}"
            )
        # O planejador por LLM caiu para as receitas nesta geração? Isso muda
        # o que a pessoa recebeu, e precisa aparecer.
        fallback_reason = getattr(self._agent.planner, "last_fallback_reason", None)
        if fallback_reason:
            warnings.append(
                f"o planejador por modelo de linguagem não respondeu "
                f"({fallback_reason}); o desenho usou as receitas internas"
            )

        if not self._agent.planner.recognizes(subject, resolved.asset.type.value):
            # O aviso é a diferença entre um asset estranho e um asset
            # estranho **explicado**. Sem ele, quem pede "house" recebe uma
            # forma genérica e não tem como saber se o sistema falhou ou se o
            # objeto está fora do vocabulário do agente.
            warnings.append(
                f"o Agente Pixel ainda não sabe desenhar '{subject}': ele "
                "produziu uma forma genérica. Para este objeto, o método "
                "'Modelo de imagem' tende a dar um resultado melhor"
            )

        return GenerationResult(
            job_id=context.job_id,
            request_id=context.request.request_id,
            status=GenerationStatus.COMPLETED,
            capability=resolved.capability,
            strategy=self.strategy_id,
            # Sem motor, e é o ponto (plano de correção §44, teste 2).
            engine=None,
            agent=_agent_ref(self._agent.planner),
            outputs=tuple(outputs),
            timings=StageTimings(
                inference_ms=(time.perf_counter() - watch) * 1000.0
            ),
            warnings=tuple(warnings),
            metadata={
                # Os metadados do §28: o que o agente decidiu e quanto gastou.
                "agent": {"id": AGENT_ID, "version": AGENT_VERSION},
                # Qual planejador produziu o desenho — a informação que o §28
                # pede sob "planner", e que separa um sprite de receita de um
                # sprite planejado por modelo.
                "planner": _planner_document(self._agent.planner),
                "quality_mode": quality.value,
                "sessions": sessions,
                "concept_reference": {
                    "used": resolved.concept_reference.enabled,
                    "engine_id": resolved.concept_reference.engine_id,
                },
            },
        )


def _resolve_quality(
    requested: object, canvas: tuple[int, int]
) -> QualityMode:
    """Traduz ``auto`` em um modo concreto a partir do tamanho do canvas.

    Grades pequenas têm poucos pixels para revisar e convergem rápido; grades
    grandes têm mais lugar onde a revisão encontra algo para corrigir. Gastar
    seis iterações em um sprite de 16×16 custa tempo e não muda o resultado.
    """
    value = getattr(requested, "value", requested)
    if value and value != "auto":
        return QualityMode(value)
    longest = max(canvas)
    if longest <= 16:
        return QualityMode.FAST
    if longest <= 64:
        return QualityMode.BALANCED
    return QualityMode.DETAILED


def _planner_document(planner) -> dict:
    """Quem planejou este desenho, para os metadados do job (§28)."""
    client = getattr(planner, "client", None)
    if client is None:
        return {"type": "recipes", "vocabulary": list(planner.recipes)}
    return {
        "type": "llm",
        "provider": client.config.base_url,
        "model": client.config.model,
        "fell_back": bool(getattr(planner, "last_fallback_reason", None)),
    }


def _agent_ref(planner) -> AgentRef:
    """A identidade do agente, com o modelo planejador quando houver um.

    O plano de correção §18 separa "modelo planejador" de "motor de imagem", e
    o histórico precisa manter essa separação: um sprite planejado pelo
    `qwen2.5` não foi *gerado* por ele.
    """
    client = getattr(planner, "client", None)
    if client is None or getattr(planner, "last_fallback_reason", None):
        return AgentRef(id=AGENT_ID, version=AGENT_VERSION)
    return AgentRef(
        id=AGENT_ID,
        version=AGENT_VERSION,
        planner_provider=client.config.base_url,
        planner_model=client.config.model,
    )
