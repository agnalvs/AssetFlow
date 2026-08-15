"""Generation Kernel — o coração da infraestrutura de IA (plano §6).

O Kernel **não gera imagens**. Ele:

- valida requests;
- descobre qual capacidade é necessária;
- localiza motores disponíveis (via Registry/Resolver);
- despacha o job para a gaveta escolhida;
- aplica timeout e cancelamento;
- normaliza o resultado;
- executa o fallback automático quando o motor preferido falha (§44);
- registra metadados e tempos (§48).

Ele é a única camada autorizada a chamar ``engine.generate()``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass

from ..schemas import (
    EngineGenerationResult,
    EngineRef,
    GenerationOutput,
    GenerationResult,
    GenerationStatus,
    ImageGenerationRequest,
    StageTimings,
    Stopwatch,
)
from .capabilities import CATALOG, CapabilityCatalog
from .contracts import (
    CancellationToken,
    EngineExecutionContext,
    NullProgressReporter,
    ProgressReporter,
)
from .exceptions import (
    EngineExecutionError,
    EngineTimeoutError,
    GenerationCancelled,
    GenerationError,
    InvalidGenerationRequest,
    NoEngineAvailable,
)
from .registry import EngineRegistry
from .resolver import EngineCandidate, EngineResolver

__all__ = ["GenerationKernel", "KernelExecution"]

_LOG = logging.getLogger("assetflow.generation.kernel")

_MAX_SEED = 2**31 - 1


@dataclass(slots=True)
class KernelExecution:
    """Parâmetros de execução de um request (contexto do job chamador)."""

    job_id: str
    cancellation: CancellationToken
    progress: ProgressReporter
    workspace: str | None = None


class GenerationKernel:
    """Fachada de execução sobre a estante de motores."""

    def __init__(
        self,
        registry: EngineRegistry,
        resolver: EngineResolver,
        *,
        catalog: CapabilityCatalog = CATALOG,
        default_timeout_s: float = 300.0,
    ) -> None:
        self._registry = registry
        self._resolver = resolver
        self._catalog = catalog
        self._default_timeout_s = default_timeout_s

    @property
    def registry(self) -> EngineRegistry:
        return self._registry

    @property
    def resolver(self) -> EngineResolver:
        return self._resolver

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------
    def validate(self, request: ImageGenerationRequest) -> None:
        """Validações que independem de motor.

        A validação específica de cada gaveta (limites, recursos) acontece no
        resolver, a partir do manifesto — nunca com ``if engine_id == ...``.
        """
        if request.output.variations < 1:
            raise InvalidGenerationRequest("é preciso pedir ao menos uma variação")
        if not self._registry.list(capability=request.capability):
            raise NoEngineAvailable(
                f"nenhuma gaveta registrada declara '{request.capability}'",
                detail={"capability": str(request.capability)},
            )

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    async def execute(
        self,
        request: ImageGenerationRequest,
        *,
        job_id: str,
        cancellation: CancellationToken | None = None,
        progress: ProgressReporter | None = None,
        workspace: str | None = None,
    ) -> GenerationResult:
        """Executa o request, com fallback automático entre motores.

        Returns:
            :class:`GenerationResult` normalizado — idêntico qualquer que
            tenha sido a tecnologia usada.
        """
        self.validate(request)

        execution = KernelExecution(
            job_id=job_id,
            cancellation=cancellation or CancellationToken(),
            progress=progress or NullProgressReporter(),
            workspace=workspace,
        )

        total = Stopwatch()
        resolution = await self._resolver.resolve(
            request.capability, selector=request.engine, request=request
        )
        chain = resolution.chain()
        _LOG.info(
            "job %s: capacidade '%s' resolvida para %s",
            job_id,
            request.capability,
            [candidate.engine_id for candidate in chain],
        )

        attempted: list[str] = []
        last_error: GenerationError | None = None

        for position, candidate in enumerate(chain):
            execution.cancellation.raise_if_cancelled()
            attempted.append(candidate.engine_id)
            try:
                engine_result, timings = await self._run_candidate(
                    candidate, request, execution
                )
            except GenerationCancelled:
                raise
            except GenerationError as exc:
                last_error = exc
                _LOG.warning(
                    "job %s: motor '%s' falhou (%s); %s",
                    job_id,
                    candidate.engine_id,
                    exc.code.value,
                    "tentando fallback" if position + 1 < len(chain) else "sem alternativas",
                )
                candidate.record.handle.mark_degraded(exc.message)
                continue

            timings.total_ms = total.elapsed_ms
            fallback_used = position > 0
            warnings = list(engine_result.warnings)
            warnings.extend(_support_warnings(candidate, request))
            if fallback_used:
                # Mensagem prevista no plano §44 — o usuário precisa saber que
                # não foi o motor principal que gerou o asset.
                warnings.append(
                    f"motor principal '{resolution.requested_engine_id}' indisponível; "
                    f"geração realizada pelo motor de fallback '{candidate.engine_id}'"
                )

            return GenerationResult(
                job_id=job_id,
                request_id=request.request_id,
                status=GenerationStatus.COMPLETED,
                capability=request.capability,
                engine=engine_result.engine,
                outputs=tuple(
                    GenerationOutput.from_artifact(artifact)
                    for artifact in engine_result.artifacts
                ),
                timings=timings,
                requested_engine_id=resolution.requested_engine_id,
                fallback_used=fallback_used,
                attempted_engines=tuple(attempted),
                warnings=tuple(dict.fromkeys(warnings)),
                metadata={
                    "resolution_chain": list(resolution.engine_ids),
                    "rejected_engines": dict(resolution.rejected),
                    "engine_metadata": engine_result.engine_metadata,
                    "capability_known": self._catalog.is_known(request.capability),
                },
            )

        raise last_error or NoEngineAvailable(
            f"nenhuma gaveta conseguiu atender '{request.capability}'",
            detail={"attempted": attempted, "rejected": dict(resolution.rejected)},
        )

    # ------------------------------------------------------------------
    # Despacho para uma gaveta
    # ------------------------------------------------------------------
    async def _run_candidate(
        self,
        candidate: EngineCandidate,
        request: ImageGenerationRequest,
        execution: KernelExecution,
    ) -> tuple[EngineGenerationResult, StageTimings]:
        """Executa o request em uma gaveta, respeitando limites e timeout."""
        handle = candidate.record.handle
        manifest = candidate.record.manifest
        timings = StageTimings()

        was_loaded = handle.is_loaded
        execution.progress(0.02, "resolving_engine", engine_id=candidate.engine_id)

        async with handle.acquire() as engine:
            if not was_loaded:
                timings.model_load_ms = handle.load_ms

            # Adapter de prompt da gaveta (plano §27). O Kernel é o único
            # lugar que o aplica, para que o motor não precise lembrar disso
            # e para que o prompt efetivo fique registrado no histórico.
            request = _apply_prompt_adapter(engine, request, manifest.id)

            timeout_s = float(manifest.timeouts.recommended_timeout_s or self._default_timeout_s)
            context = EngineExecutionContext(
                job_id=execution.job_id,
                cancellation=execution.cancellation,
                progress=execution.progress,
                deadline_s=timeout_s,
                logger=logging.getLogger(f"assetflow.engine.{manifest.id}"),
            )

            # Lotes: um motor pode ter limite de variações menor que o pedido.
            batches = _plan_batches(
                request.output.variations, manifest.limits.max_variations
            )
            master_seed = request.generation.seed
            if master_seed is None:
                master_seed = random.randint(0, _MAX_SEED)

            artifacts = []
            inference_ms = 0.0
            warnings: list[str] = []
            metadata: dict = {}
            engine_ref: EngineRef | None = None
            seed_offset = 0

            for batch_index, size in enumerate(batches):
                execution.cancellation.raise_if_cancelled()
                batch_request = request.model_copy(
                    update={
                        "output": request.output.model_copy(update={"variations": size}),
                        "generation": request.generation.model_copy(
                            update={"seed": (master_seed + seed_offset) % (_MAX_SEED + 1)}
                        ),
                    },
                    deep=True,
                )
                seed_offset += size

                watch = Stopwatch()
                try:
                    result = await asyncio.wait_for(
                        engine.generate(batch_request, context), timeout=timeout_s
                    )
                except asyncio.TimeoutError as exc:
                    execution.cancellation.cancel("timeout")
                    await _safe_cancel(engine, execution.job_id)
                    raise EngineTimeoutError(
                        f"motor '{manifest.id}' excedeu {timeout_s:.0f}s",
                        engine_id=manifest.id,
                    ) from exc
                except GenerationError:
                    raise
                except Exception as exc:  # tradução final para erro normalizado
                    raise EngineExecutionError(
                        f"motor '{manifest.id}' falhou: {exc}",
                        engine_id=manifest.id,
                        detail={"cause": repr(exc)},
                    ) from exc

                inference_ms += result.timings.inference_ms or watch.elapsed_ms
                engine_ref = result.engine
                warnings.extend(result.warnings)
                metadata.update(result.engine_metadata)
                for artifact in result.artifacts:
                    artifacts.append(
                        artifact.model_copy(update={"index": len(artifacts)})
                    )

                execution.progress(
                    min(0.95, (batch_index + 1) / max(1, len(batches))),
                    "generating",
                    engine_id=manifest.id,
                )

            if not artifacts:
                raise EngineExecutionError(
                    f"motor '{manifest.id}' não devolveu nenhuma imagem",
                    engine_id=manifest.id,
                )

            timings.inference_ms = inference_ms
            metadata["effective_prompt"] = {
                "positive": request.prompt.positive,
                "negative": request.prompt.negative,
            }
            return (
                EngineGenerationResult(
                    engine=engine_ref or engine.engine_ref(),
                    artifacts=tuple(artifacts),
                    timings=StageTimings(inference_ms=inference_ms),
                    warnings=tuple(dict.fromkeys(warnings)),
                    engine_metadata=metadata,
                ),
                timings,
            )


def _apply_prompt_adapter(
    engine, request: ImageGenerationRequest, engine_id: str
) -> ImageGenerationRequest:
    """Traduz o prompt para o dialeto da gaveta, quando ela tiver um.

    A representação semântica continua intacta no request — é ela, não o
    texto, que atravessa a troca de motores (plano §27/§28).
    """
    try:
        adapter = engine.prompt_adapter()
    except Exception:  # pragma: no cover - defensivo
        _LOG.debug("prompt_adapter() falhou em '%s'", engine_id, exc_info=True)
        return request

    if adapter is None:
        return request

    try:
        positive, negative = adapter.adapt(request)
    except Exception:  # pragma: no cover - um adapter quebrado não mata o job
        _LOG.warning(
            "adapter de prompt de '%s' falhou; usando o texto neutro", engine_id
        )
        return request

    return request.model_copy(
        update={
            "prompt": request.prompt.model_copy(
                update={"positive": positive, "negative": negative}
            )
        }
    )


def _plan_batches(requested: int, max_per_batch: int) -> list[int]:
    """Divide N variações em lotes que respeitam o limite da gaveta."""
    size = max(1, max_per_batch)
    full, rest = divmod(requested, size)
    batches = [size] * full
    if rest:
        batches.append(rest)
    return batches or [requested]


def _support_warnings(
    candidate: EngineCandidate, request: ImageGenerationRequest
) -> list[str]:
    """Avisos por recurso pedido que o motor escolhido não suporta.

    Não são erros: o pedido continua válido, mas o usuário precisa saber que
    algo foi ignorado (ex.: reprodutibilidade por seed).
    """
    supports = candidate.record.manifest.supports
    warnings: list[str] = []
    if request.generation.seed is not None and not supports.seed:
        warnings.append(f"motor '{candidate.engine_id}' ignora seed: resultado não reprodutível")
    if request.prompt.negative and not supports.negative_prompt:
        warnings.append(f"motor '{candidate.engine_id}' ignora negative prompt")
    if request.output.transparent and not supports.transparency:
        warnings.append(
            f"motor '{candidate.engine_id}' não gera transparência nativa; "
            "o pós-processamento tentará recuperar o alpha"
        )
    return warnings


async def _safe_cancel(engine, job_id: str) -> None:
    """Avisa a gaveta sobre o cancelamento sem deixar erro escapar."""
    try:
        await engine.cancel(job_id)
    except Exception:  # pragma: no cover - defensivo
        _LOG.debug("cancel() falhou no motor", exc_info=True)
