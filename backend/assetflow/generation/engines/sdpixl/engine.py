"""`sdpixl-v1` — a gaveta do SD-πXL (plano de motores §8.2 e §13).

O SD-πXL é a referência de qualidade técnica em Pixel Art: ele trabalha
nativamente em baixa resolução e com paleta limitada, que é exatamente o que
um sprite é. O preço, declarado pelo próprio projeto, é tempo de otimização em
horas e uma recomendação de 24 GB de VRAM.

Isso muda **como** ele entra no AssetFlow, não **se** ele entra:

* nasce desabilitado, com selo ``experimental`` e ``lento`` no catálogo;
* declara ``recommended_timeout_s`` em horas, e o worker precisa concordar
  (``ASSETFLOW_JOB_TIMEOUT_S``) — o teto do worker envolve o job inteiro;
* nunca é preferido pela política automática sem que alguém peça qualidade
  máxima explicitamente (plano de motores §16).

A integração é por processo externo. O motivo é de arquitetura, não de
preguiça: importar o SD-πXL como biblioteca amarraria o backend ao ambiente
Python dele — outra versão de torch, outras dependências — e o plano de motores §3 é
categórico em manter essas dependências confinadas.

Repare que esta gaveta cumpre o Engine Contract inteiro sem carregar modelo
nenhum em memória: é o contrato que permite a "processo externo de horas" e a
"modelo na GPU" ocuparem a mesma prateleira. Quem cobra isso é
``tests/contract/test_engine_contract.py``, que gera o caso sozinho a partir
do manifesto.
"""

from __future__ import annotations

import random
import tempfile
import time
from pathlib import Path

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
from .bridge import command_available, render_command, run_command
from .config import ADAPTER_VERSION, SDPiXLConfig

__all__ = ["SDPiXLEngine"]

_MAX_SEED = 2**31 - 1


class SDPiXLEngine(BaseImageGenerationEngine):
    """Ponte para o SD-πXL executado como processo local."""

    def __init__(self) -> None:
        super().__init__()
        self._sdpixl_config = SDPiXLConfig()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def on_initialize(self, config: EngineRuntimeConfig) -> None:
        """Só lê configuração: não há modelo para carregar em memória.

        Quem carrega peso é o processo externo, e ele nasce e morre a cada
        geração. É uma diferença real entre esta gaveta e as de difusão, e ela
        aparece no health check: aqui ``model_loaded`` nunca fica ``True``.
        """
        self._sdpixl_config = SDPiXLConfig.from_runtime(config)
        problem = command_available(
            self._sdpixl_config.command, self._sdpixl_config.working_dir
        )
        if problem:
            # Não é erro de inicialização: a gaveta existe, está registrada e
            # é escolhível — ela apenas não está pronta nesta máquina. Quem
            # comunica isso é o health check, que é onde a interface olha.
            self._logger.warning("SD-πXL indisponível: %s", problem)

    async def health_check(self) -> EngineHealth:
        problem = command_available(
            self._sdpixl_config.command, self._sdpixl_config.working_dir
        )
        if problem:
            return EngineHealth(
                status=EngineHealthStatus.UNAVAILABLE,
                model_loaded=False,
                gpu_available=False,
                detail=problem,
            )
        return EngineHealth(
            status=EngineHealthStatus.HEALTHY,
            model_loaded=False,
            gpu_available=False,
            detail="processo externo; cada geração pode levar muito tempo",
            metrics={
                "active_jobs": len(self._active_jobs),
                "process_timeout_s": self._sdpixl_config.process_timeout_s,
            },
        )

    def engine_ref(self) -> EngineRef:
        manifest = self.manifest()
        return EngineRef(
            id=manifest.id,
            version=manifest.version,
            provider=manifest.provider,
            model_id=self._sdpixl_config.model_id,
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
        config = self._sdpixl_config
        options = request.options_for(manifest.id)

        seed = request.generation.seed
        if seed is None:
            seed = random.randint(0, _MAX_SEED)
        steps = int(options.get("steps", config.steps_for(request.generation.quality)))

        # O SD-πXL trabalha no tamanho lógico — é o ponto dele. Sem grid
        # lógico no pedido (arte 2D), cai para o tamanho de render.
        logical = request.output.logical_size or (
            request.output.width,
            request.output.height,
        )

        self._track(context.job_id)
        started = time.perf_counter()
        try:
            images = await self._render(
                request=request,
                context=context,
                seed=seed,
                steps=steps,
                logical=logical,
            )
        finally:
            self._untrack(context.job_id)

        inference_ms = (time.perf_counter() - started) * 1000.0
        artifacts = tuple(
            ImageArtifact(
                index=index,
                data=data,
                mime_type="image/png",
                width=logical[0],
                height=logical[1],
                seed=(seed + index) % (_MAX_SEED + 1),
                metadata={"renderer": "sd-pixl", "native_logical": True},
            )
            for index, data in enumerate(images)
        )

        return EngineGenerationResult(
            engine=self.engine_ref(),
            artifacts=artifacts,
            timings=StageTimings(inference_ms=inference_ms),
            warnings=(),
            engine_metadata={
                "engine": manifest.id,
                "adapter_version": ADAPTER_VERSION,
                "steps": steps,
                "logical_size": list(logical),
                "max_colors": request.output.max_colors,
                "quality": request.generation.quality.value,
            },
        )

    # ------------------------------------------------------------------
    async def _render(
        self,
        *,
        request: ImageGenerationRequest,
        context: EngineExecutionContext,
        seed: int,
        steps: int,
        logical: tuple[int, int],
    ) -> list[bytes]:
        """Roda o processo uma vez por variação.

        Uma vez **por variação**, e não um lote só: o SD-πXL otimiza uma
        imagem por execução, e fingir um lote aqui esconderia do usuário que
        pedir 4 variações multiplica o tempo por 4.
        """
        config = self._sdpixl_config
        collected: list[bytes] = []
        total = max(1, request.output.variations)

        for index in range(total):
            context.cancellation.raise_if_cancelled()
            context.report(index / total, "generating", engine_id=self.manifest().id)

            with tempfile.TemporaryDirectory(prefix="assetflow-sdpixl-") as tmp:
                output_dir = Path(config.output_dir or tmp)
                output_dir.mkdir(parents=True, exist_ok=True)
                values = {
                    "prompt": request.prompt.positive,
                    "negative": request.prompt.negative or "",
                    "width": request.output.width,
                    "height": request.output.height,
                    "logical_width": logical[0],
                    "logical_height": logical[1],
                    "max_colors": request.output.max_colors or "",
                    "seed": (seed + index) % (_MAX_SEED + 1),
                    "steps": steps,
                    "output_dir": str(output_dir),
                    "output": str(output_dir / f"{index:03d}.png"),
                    "workspace": self.config.workspace_dir or tmp,
                }
                command = render_command(config.command, values)
                result = await run_command(
                    command,
                    working_dir=config.working_dir,
                    output_dir=output_dir,
                    output_glob=config.output_glob,
                    timeout_s=config.process_timeout_s,
                    env=config.env,
                    cancellation=context.cancellation,
                )
                # Uma execução pode produzir mais de um arquivo; só o primeiro
                # corresponde a esta variação.
                collected.append(result.images[0])

        context.report(0.95, "generating", engine_id=self.manifest().id)
        return collected
