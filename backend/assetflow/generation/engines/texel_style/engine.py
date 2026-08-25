"""`texel-style-v1` — o agente que desenha pixel a pixel (plano de motores §9 e §15).

    FinalResolvedSpec
        -> PlanningAgent      etapa 2: o plano de desenho
        -> ToolExecutor       etapa 3: as ferramentas pintam
        -> PixelCanvas        o estado
        -> ReviewLoop         etapa 4: o agente confere e corrige
        -> exportação         etapa 5: imagem + log das tool calls

Esta é a única gaveta que **não** gera uma imagem grande para depois reduzir.
Ela desenha direto na resolução lógica, e é essa diferença que ela existe para
oferecer (plano de motores §9.2): pixels intencionais, silhueta limpa, paleta conhecida
de antemão, consistência entre execuções.

Sobre licença e origem (plano de motores §2.4)
-----------------------------------
O Texel Studio é *source-available*, com restrição contra hospedagem como SaaS
concorrente. Esta gaveta **não** incorpora, importa nem revende aquele
projeto: ela é uma implementação própria do AssetFlow, inspirada na
arquitetura tool-based dele. O que foi adotado é o vocabulário de ferramentas
— ``draw_pixel``, ``fill_rect``, ``draw_circle``… —, que descreve bem o
problema; o código é todo daqui.

O que este MVP entrega
----------------------
Props simples: árvore, pedra, poção, baú, bloco, espada, moeda — e um boneco
básico. O plano de motores §15 é explícito em não começar por personagens complexos, e a
receita de personagem existe só para que um pedido desses não caia no fallback
genérico.
"""

from __future__ import annotations

import io
import random
import time
from typing import Any

from PIL import Image

from ....generation.kernel.contracts import (
    BaseImageGenerationEngine,
    EngineExecutionContext,
)
from ....generation.schemas import (
    EngineGenerationResult,
    EngineHealth,
    EngineHealthStatus,
    EngineRef,
    EngineRuntimeConfig,
    ImageArtifact,
    ImageGenerationRequest,
    StageTimings,
)
from .canvas import PixelCanvas
from .planner import DrawingBrief, DrawingPlan, PlanningAgent
from .review_loop import ReviewLoop
from .tool_executor import ToolCallLog, ToolExecutor

__all__ = ["TexelStyleEngine", "ADAPTER_VERSION"]

#: Versão do adapter — o código desta pasta (plano de motores §18).
ADAPTER_VERSION = "1.0.0"

_MAX_SEED = 2**31 - 1

#: Canvas usado quando o pedido não traz grid lógico (arte 2D pedindo esta
#: gaveta por engano). Pequeno de propósito: o valor desta gaveta é a grade.
_FALLBACK_CANVAS = 64


class TexelStyleEngine(BaseImageGenerationEngine):
    """Gaveta agentiva: planeja, desenha com ferramentas, revisa e exporta."""

    def __init__(self) -> None:
        super().__init__()
        self._planner = PlanningAgent()
        self._executor = ToolExecutor()
        self._review = ReviewLoop(self._executor)
        self._max_review_passes = 2

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        """Não há modelo para carregar: o "modelo" é o código das receitas.

        É a gaveta mais barata da estante para inicializar, e isso tem uma
        consequência prática boa: ela serve de fallback confiável quando um
        motor pesado não está disponível.
        """
        options = config.options or {}
        self._max_review_passes = int(options.get("review_passes", 2))

    async def health_check(self) -> EngineHealth:
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=True,
            gpu_available=False,
            detail="agente de desenho local; não usa GPU nem rede",
            metrics={
                "active_jobs": len(self._active_jobs),
                "tools": list(self._executor.tool_names),
                "recipes": list(self._planner.recipes),
            },
        )

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            # Não existe modelo baixado: o que produz o sprite é este código,
            # e é honesto dizer isso no histórico em vez de deixar o campo
            # vazio como se a informação tivesse se perdido.
            model_id=f"agent://texel-style@{ADAPTER_VERSION}",
            adapter_version=ADAPTER_VERSION,
        )

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def generate(
        self,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
    ) -> EngineGenerationResult:
        manifest = self.manifest()

        canvas_size = request.output.logical_size or (
            _FALLBACK_CANVAS,
            _FALLBACK_CANVAS,
        )
        warnings: list[str] = []
        if request.output.logical_size is None:
            warnings.append(
                "o pedido não traz grid lógico; o agente desenhou em "
                f"{_FALLBACK_CANVAS}×{_FALLBACK_CANVAS} — este motor foi feito "
                "para Pixel Art"
            )

        base_seed = request.generation.seed
        if base_seed is None:
            base_seed = random.randint(0, _MAX_SEED)

        subject = _subject_of(request)
        artifacts: list[ImageArtifact] = []
        plans: list[dict[str, Any]] = []
        logs: list[list[dict[str, Any]]] = []
        reviews: list[dict[str, Any]] = []

        self._track(context.job_id)
        started = time.perf_counter()
        try:
            total = max(1, request.output.variations)
            for index in range(total):
                context.cancellation.raise_if_cancelled()
                seed = (base_seed + index * 7919) % (_MAX_SEED + 1)

                image, plan, log, review = self._draw(
                    subject=subject,
                    asset_type=request.asset.type.value,
                    size=canvas_size,
                    max_colors=request.output.max_colors,
                    transparent=request.output.transparent,
                    seed=seed,
                )

                artifacts.append(
                    ImageArtifact(
                        index=index,
                        data=image,
                        mime_type="image/png",
                        width=canvas_size[0],
                        height=canvas_size[1],
                        seed=seed,
                        metadata={
                            "renderer": "texel-style",
                            "recipe": plan.recipe,
                            "native_logical": True,
                        },
                    )
                )
                plans.append(plan.document())
                logs.append(log.document())
                reviews.append(review)
                context.report(
                    (index + 1) / total, "generating", engine_id=manifest.id
                )
        finally:
            self._untrack(context.job_id)

        inference_ms = (time.perf_counter() - started) * 1000.0

        return EngineGenerationResult(
            engine=self.engine_ref(),
            artifacts=tuple(artifacts),
            timings=StageTimings(inference_ms=inference_ms),
            warnings=tuple(warnings),
            engine_metadata={
                "engine": manifest.id,
                "adapter_version": ADAPTER_VERSION,
                "canvas": list(canvas_size),
                "subject": subject,
                # O plano e o histórico de tool calls sobem no metadata do
                # motor, e é por isso que eles acabam em `engine_output.json`
                # ao lado do asset — o artefato que o plano de motores §9.5 pede.
                "plans": plans,
                "tool_calls": logs,
                "review": reviews,
            },
        )

    # ------------------------------------------------------------------
    def _draw(
        self,
        *,
        subject: str,
        asset_type: str,
        size: tuple[int, int],
        max_colors: int | None,
        transparent: bool,
        seed: int,
    ) -> tuple[bytes, DrawingPlan, ToolCallLog, dict[str, Any]]:
        """As cinco etapas do §9, para uma variação."""
        brief = DrawingBrief(
            subject=subject,
            asset_type=asset_type,
            width=size[0],
            height=size[1],
            max_colors=max_colors,
            transparent=transparent,
            seed=seed,
        )

        # Etapa 2 — planejamento.
        plan = self._planner.plan(brief)

        # Etapa 3 — execução por ferramentas.
        canvas = PixelCanvas(size[0], size[1])
        log = ToolCallLog()
        self._executor.execute_all(canvas, plan.calls, log)

        # Etapa 4 — inspeção e ajuste.
        report = self._review.run(
            canvas,
            outline_color=plan.palette.outline,
            max_colors=max_colors,
            log=log,
            max_passes=self._max_review_passes,
        )

        # Etapa 5 — exportação.
        if not transparent:
            # Fundo sólido pedido: a cor mais escura da paleta é a que menos
            # compete com o sprite, e usá-la mantém o resultado dentro do
            # orçamento de cores que acabou de ser aplicado.
            canvas = canvas.flatten(_hex_to_rgba(plan.palette.outline))

        return _encode_png(canvas), plan, log, report.document()


def _subject_of(request: ImageGenerationRequest) -> str:
    """O sujeito do desenho, na melhor fonte disponível.

    A semântica primeiro: ela é a leitura estruturada do AssetFlow, e traz o
    sujeito já separado de estilo, vista e restrições técnicas. O texto do
    prompt é o fallback, e nele o sujeito vem misturado com tudo o mais — o
    que faz o casamento de receita errar mais.
    """
    semantic = request.prompt.semantic
    if semantic is not None and semantic.subject.strip():
        return semantic.subject.strip()
    return request.prompt.positive.strip()


def _hex_to_rgba(value: str) -> tuple[int, int, int, int]:
    text = value.strip().lstrip("#")
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

    Devolver a imagem na resolução lógica é a razão de ser desta gaveta. O
    pós-processamento recebe uma imagem que já está no grid pedido, encontra
    origem e alvo iguais e passa direto: nenhuma reamostragem toca no desenho,
    e o que sai do arquivo é exatamente o que o agente decidiu pixel a pixel.
    """
    image = Image.frombytes("RGBA", (canvas.width, canvas.height), canvas.to_bytes())
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
